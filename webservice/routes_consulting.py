"""컨설팅 분석 라우트: 업로드→백그라운드 분석→리포트 저장/조회."""

import json
import os
import sqlite3
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from webservice import db
from webservice.consulting import heatmap, jobs, rules
from webservice.routes_auth import current_user

router = APIRouter(prefix="/api/consulting")

_BASE = os.path.dirname(os.path.abspath(__file__))
_UPLOAD_DIR = os.path.join(_BASE, "consulting", "uploads")
_REPORT_DIR = os.path.join(_BASE, "consulting", "reports")

# 온라인 전시에서는 아무 파일이나 올라올 수 있다. 디스크와 변환 시간을 지킨다.
# 200MB 인 이유: 아이폰으로 1분 남짓 찍으면 1080p 기준 100~150MB 가 예사다.
# 80MB 로 잡았더니 실제 촬영 영상이 그냥 막혔다. 업로드는 청크로 디스크에 흘려
# 쓰므로 이 값이 커져도 메모리 사용량은 늘지 않는다(디스크와 변환 시간만 는다).
MAX_UPLOAD_BYTES = int(os.environ.get("DAON_MAX_UPLOAD_MB", "200")) * 1024 * 1024


def _safe_upload_path(filename):
    # file.filename is attacker-controlled; strip any directory components so
    # the upload can never escape _UPLOAD_DIR.
    name = f"{uuid.uuid4().hex}_{os.path.basename(filename)}"
    return os.path.join(_UPLOAD_DIR, name)


def _analyze(video_path):
    # 테스트가 monkeypatch하는 훅 — 실제 경로는 지연 임포트한 YOLO를 쓴다.
    from webservice.consulting.analyze import analyze_video
    return analyze_video(video_path)


async def _save_upload(file, dest, max_bytes=None, chunk=1024 * 1024):
    """업로드를 청크 단위로 디스크에 흘려 쓰고, 한도를 넘으면 즉시 끊는다.

    `await file.read()` 로 통째로 읽으면 두 가지가 문제다.
    - 영상은 수백 MB라 그만큼이 그대로 메모리에 올라간다. torch 까지 올라가 있는
      1~2GB 인스턴스에서는 이것만으로 OOM 이 난다.
    - 한도 초과를 다 받은 뒤에야 알 수 있어, 거부할 파일을 끝까지 받는다.
    """
    limit = MAX_UPLOAD_BYTES if max_bytes is None else max_bytes
    written = 0
    try:
        with open(dest, "wb") as f:
            while True:
                block = await file.read(chunk)
                if not block:
                    break
                written += len(block)
                if written > limit:
                    raise HTTPException(
                        status_code=413,
                        detail=f"영상이 너무 큽니다. {limit // (1024*1024)}MB 이하로 "
                               "줄여서 올려주세요. (영상 길이를 줄이거나 화질을 "
                               "낮추면 됩니다)")
                f.write(block)
    except HTTPException:
        if os.path.exists(dest):
            os.remove(dest)          # 잘린 파일을 남기지 않는다
        raise
    if written == 0:
        if os.path.exists(dest):
            os.remove(dest)
        raise HTTPException(status_code=400, detail="빈 파일입니다.")
    return written


def _ensure_readable(video_path):
    # 테스트가 monkeypatch 하는 훅 — 실제 경로는 ffmpeg 를 쓴다.
    from webservice.consulting.transcode import ensure_readable
    return ensure_readable(video_path)


def _lookup_cache(video_path):
    """체험용 샘플이면 사전 계산 결과, 아니면 None. (테스트 monkeypatch 훅)"""
    from webservice.consulting import cache
    return cache.lookup(video_path)


def _insert_report(user_id, video_ref, image_path, report):
    """리포트 행을 만들고 id 를 돌려준다. 실제 분석과 캐시 적중이 공유한다."""
    conn = db.connect()
    try:
        cur = conn.execute(
            "INSERT INTO reports (user_id, video_ref, heatmap_path, findings_json) "
            "VALUES (?, ?, ?, ?)",
            (user_id, video_ref, image_path,
             json.dumps(report, ensure_ascii=False)))
        conn.commit()
        return cur.lastrowid
    except sqlite3.IntegrityError as exc:
        # user_id 가 users 에 없을 때 나는 'FOREIGN KEY constraint failed'.
        # 이 잡은 백그라운드 스레드라 예외 문구가 그대로 화면 콘솔에 찍힌다 —
        # 원인을 알아볼 수 있는 문장으로 바꿔 둔다. (routes_auth.current_user 가
        # 매 요청 세션을 검증하므로 정상 경로에서는 더 이상 발생하지 않는다.)
        raise RuntimeError(
            "로그인 정보가 만료되어 리포트를 저장하지 못했습니다. "
            "다시 로그인한 뒤 시도해 주세요.") from exc
    finally:
        conn.close()


def _unpack(result):
    """분석 결과를 (지도, 첫 프레임, 동선 구간들)로 편다.

    analyze_video 는 동선 구간까지 3개를 돌려주지만, 예전 2-튜플
    (지도, 첫 프레임)을 돌려주는 구현이나 테스트 대역도 그대로 받아준다.
    구간이 없으면 경로 선 없이 위험 구역 박스만 그린다.
    """
    if len(result) == 3:
        return result
    hm, first = result
    return hm, first, None


def _can_access(conn, user, owner_id):
    # 역할이 admin 하나뿐이라 리포트는 만든 사람만 본다. 예전에는 보호자가
    # 연결된 어르신의 리포트를 볼 수 있었으나, 어르신 계정 자체가 없어졌다.
    return user["id"] == owner_id


@router.post("/analyze")
async def analyze(user=Depends(current_user), file: UploadFile = File(...),
                  location: str = Form("")):
    os.makedirs(_UPLOAD_DIR, exist_ok=True)
    os.makedirs(_REPORT_DIR, exist_ok=True)

    video_path = _safe_upload_path(file.filename)
    await _save_upload(file, video_path)

    user_id = user["id"]
    video_ref = location or file.filename   # 촬영 위치(공용 라운지 등)를 저장, 없으면 파일명

    # 체험용 샘플이면 사전 계산된 결과를 바로 돌려준다. 분석은 건너뛰지만
    # DB 행은 똑같이 만들어서 리포트 조회·목록·이미지 서빙이 그대로 동작한다.
    cached = _lookup_cache(video_path)
    if cached is not None:
        rid = _insert_report(user_id, video_ref or cached["location"],
                             cached["image"], cached["findings"])
        os.remove(video_path)               # 샘플 원본을 중복 보관할 이유가 없다
        return {"job_id": jobs.complete(jobs.create_job(), rid)}

    def job():
        # 아이폰 .mov(HEVC) 등 OpenCV 가 못 읽는 형식을 먼저 H.264 로 맞춘다.
        # 이미 읽을 수 있으면 그대로 통과한다.
        path, converted = _ensure_readable(video_path)
        try:
            hm, first, segments = _unpack(_analyze(path))
        finally:
            if converted and os.path.isfile(path):
                os.remove(path)
        report = rules.analyze_report(hm)          # 기본 3×3 격자
        png_path = os.path.join(_REPORT_DIR, f"{uuid.uuid4().hex}.png")
        # 방 사진 위에 이동 경로를 그린다. 구역 박스는 경로를 가려서 기본 off.
        heatmap.render_hazard_boxes(first, report["findings"][:1], 3, 3, png_path,
                                    segments=segments)
        return _insert_report(user_id, video_ref, png_path, report)

    job_id = jobs.create_job()
    try:
        jobs.run_in_background(job_id, job)
    except jobs.TooBusy as exc:
        if os.path.exists(video_path):
            os.remove(video_path)
        raise HTTPException(status_code=503, detail=str(exc))
    return {"job_id": job_id}


@router.get("/status/{job_id}")
def status(job_id: str, user=Depends(current_user)):
    j = jobs.get_job(job_id)
    if j is None:
        raise HTTPException(status_code=404, detail="잡을 찾을 수 없습니다")
    return j


@router.get("/reports")
def reports(user=Depends(current_user)):
    conn = db.connect()
    try:
        rows = conn.execute(
            "SELECT id, user_id, created_at, video_ref, findings_json FROM reports "
            "WHERE user_id = ? ORDER BY id DESC", (user["id"],)).fetchall()
    finally:
        conn.close()
    out = []
    for row in rows:
        out.append({"id": row["id"], "user_id": row["user_id"],
                    "created_at": row["created_at"], "location": row["video_ref"],
                    "summary": json.loads(row["findings_json"])["summary"]})
    return out


def _load_report(conn, rid, user):
    row = conn.execute("SELECT * FROM reports WHERE id = ?", (rid,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="리포트를 찾을 수 없습니다")
    if not _can_access(conn, user, row["user_id"]):
        raise HTTPException(status_code=403, detail="열람 권한이 없습니다")
    return row


@router.get("/report/{rid}")
def get_report(rid: int, user=Depends(current_user)):
    conn = db.connect()
    try:
        row = _load_report(conn, rid, user)
    finally:
        conn.close()
    data = json.loads(row["findings_json"])
    return {"id": row["id"], "summary": data["summary"], "findings": data["findings"],
            "location": row["video_ref"], "created_at": row["created_at"],
            # 예전에 저장된 리포트에는 evidence 가 없다(키 추가 이전). 없으면 생략.
            "evidence": data.get("evidence")}


@router.get("/report/{rid}/image")
def report_image(rid: int, user=Depends(current_user)):
    conn = db.connect()
    try:
        row = _load_report(conn, rid, user)
        path = row["heatmap_path"]
    finally:
        conn.close()
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="이미지 파일이 없습니다")
    return FileResponse(path)
