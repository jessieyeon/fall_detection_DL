"""컨설팅 분석 라우트: 업로드→백그라운드 분석→리포트 저장/조회."""

import json
import os
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from webservice import db
from webservice.consulting import heatmap, jobs, rules
from webservice.routes_auth import current_user

router = APIRouter(prefix="/api/consulting")

_BASE = os.path.dirname(os.path.abspath(__file__))
_UPLOAD_DIR = os.path.join(_BASE, "consulting", "uploads")
_REPORT_DIR = os.path.join(_BASE, "consulting", "reports")


def _safe_upload_path(filename):
    # file.filename is attacker-controlled; strip any directory components so
    # the upload can never escape _UPLOAD_DIR.
    name = f"{uuid.uuid4().hex}_{os.path.basename(filename)}"
    return os.path.join(_UPLOAD_DIR, name)


def _analyze(video_path):
    # 테스트가 monkeypatch하는 훅 — 실제 경로는 지연 임포트한 YOLO를 쓴다.
    from webservice.consulting.analyze import analyze_video
    return analyze_video(video_path)


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
async def analyze(user=Depends(current_user), file: UploadFile = File(...)):
    os.makedirs(_UPLOAD_DIR, exist_ok=True)
    os.makedirs(_REPORT_DIR, exist_ok=True)
    video_path = _safe_upload_path(file.filename)
    with open(video_path, "wb") as f:
        f.write(await file.read())

    user_id = user["id"]

    def job():
        hm, first = _analyze(video_path)
        report = rules.analyze_report(hm)
        rid_name = uuid.uuid4().hex
        png_path = os.path.join(_REPORT_DIR, f"{rid_name}.png")
        heatmap.render_heatmap_png(hm, png_path, background=first)
        conn = db.connect()
        try:
            cur = conn.execute(
                "INSERT INTO reports (user_id, video_ref, heatmap_path, findings_json) "
                "VALUES (?, ?, ?, ?)",
                (user_id, file.filename, png_path,
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
                "SELECT r.id, r.user_id, r.created_at, r.findings_json "
                "FROM reports r JOIN guardian_links gl ON gl.senior_id = r.user_id "
                "WHERE gl.guardian_id = ? ORDER BY r.id DESC", (user["id"],)).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, user_id, created_at, findings_json FROM reports "
                "WHERE user_id = ? ORDER BY id DESC", (user["id"],)).fetchall()
    finally:
        conn.close()
    out = []
    for row in rows:
        out.append({"id": row["id"], "user_id": row["user_id"],
                    "created_at": row["created_at"],
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
    return {"id": row["id"], "summary": data["summary"],
            "findings": data["findings"], "created_at": row["created_at"]}


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
