"""컨설팅 분석 라우트: 업로드→백그라운드 분석→리포트 저장/조회."""

import json
import os
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
    if user["id"] == owner_id:
        return True
    if user["role"] == "guardian":
        row = conn.execute(
            "SELECT 1 FROM guardian_links WHERE guardian_id=? AND senior_id=?",
            (user["id"], owner_id)).fetchone()
        return row is not None
    return False


@router.post("/analyze")
async def analyze(user=Depends(current_user), file: UploadFile = File(...),
                  location: str = Form("")):
    os.makedirs(_UPLOAD_DIR, exist_ok=True)
    os.makedirs(_REPORT_DIR, exist_ok=True)

    video_path = _safe_upload_path(file.filename)
    await _save_upload(file, video_path)

    user_id = user["id"]
    video_ref = location or file.filename   # 촬영 위치(거실 등)를 저장, 없으면 파일명

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
        rid_name = uuid.uuid4().hex
        png_path = os.path.join(_REPORT_DIR, f"{rid_name}.png")
        # 방 위에 이동 경로를 선으로 그리고, 가장 위험한 구역만 빨간 박스로
        # 덮는다. 경로가 함께 보여야 '왜 이 구역인가'가 설명된다.
        heatmap.render_hazard_boxes(first, report["findings"][:1], 3, 3, png_path,
                                    segments=segments)
        conn = db.connect()
        try:
            cur = conn.execute(
                "INSERT INTO reports (user_id, video_ref, heatmap_path, findings_json) "
                "VALUES (?, ?, ?, ?)",
                (user_id, video_ref, png_path,
                 json.dumps(report, ensure_ascii=False)))
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()

    job_id = jobs.create_job()
    jobs.run_in_background(job_id, job)
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
        if user["role"] == "guardian":
            rows = conn.execute(
                "SELECT r.id, r.user_id, r.created_at, r.video_ref, r.findings_json "
                "FROM reports r JOIN guardian_links gl ON gl.senior_id = r.user_id "
                "WHERE gl.guardian_id = ? ORDER BY r.id DESC", (user["id"],)).fetchall()
        else:
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
            "location": row["video_ref"], "created_at": row["created_at"]}


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
