"""다온 웹 서비스 FastAPI 진입점."""

import mimetypes
import os
import threading
import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from webservice import db, metrics
from webservice.routes_auth import router as auth_router
from webservice.routes_admin import router as admin_router
from webservice.routes_home import router as home_router
from webservice.routes_consulting import router as consulting_router
from webservice.routes_live import router as live_router

app = FastAPI(title="다온 낙상 케어")

# 온라인 전시 사이트가 이 앱을 iframe 으로 임베드한다. 그러면 우리 쿠키는
# '서드파티 쿠키'가 되어, 기본값(SameSite=lax)에서는 브라우저가 보내지 않는다.
# → URL 을 직접 열면 로그인이 되는데 iframe 안에서만 안 되는 상황이 생긴다.
# SameSite=None 으로 풀어야 하고, 그러려면 Secure(=HTTPS)가 필수다.
# 로컬 개발은 HTTP 라 Secure 쿠키를 못 쓰므로 DAON_EMBED=1 일 때만 켠다.
_EMBED = os.environ.get("DAON_EMBED", "0") == "1"

# 세션 쿠키 서명 키. 이 값이 공개 저장소에 적힌 기본값 그대로면 누구나 로그인
# 쿠키를 위조할 수 있다. 로컬 개발까지 막으면 불편하므로, 임베드 모드
# (=배포 환경. HTTPS 와 SameSite=None 이 필요한 그 모드다)일 때만 기동을
# 거부한다. 경고 로그는 아무도 안 읽으므로 기동 실패로 낸다 —
# 전시 서버가 기본 시크릿으로 뜨는 것보다 배포가 실패하는 편이 낫다.
DEFAULT_SECRET = "dev-demo-secret-change-me"
_SECRET = os.environ.get("DAON_SECRET") or DEFAULT_SECRET
if _EMBED and _SECRET == DEFAULT_SECRET:
    raise RuntimeError(
        "DAON_SECRET 이 기본값입니다. 배포(DAON_EMBED=1) 에서는 실제 값을 "
        "설정해야 합니다.  예: DAON_SECRET=$(python3 -c "
        "'import secrets;print(secrets.token_urlsafe(32))')")

app.add_middleware(
    SessionMiddleware,
    secret_key=_SECRET,
    same_site="none" if _EMBED else "lax",
    https_only=_EMBED,
)


@app.middleware("http")
async def _count_requests(request, call_next):
    """요청 수·상태코드·느린 요청을 센다. /api/metrics 가 이걸 보여준다.

    전시 중에 "서버가 버티고 있나"를 물으면 지금은 답할 방법이 없다. 카운터는
    메모리에만 있고 요청당 비용은 잠금 한 번이라 부하에 영향을 주지 않는다.
    """
    started = time.monotonic()
    response = await call_next(request)
    metrics.counter.record(response.status_code, time.monotonic() - started)
    return response


@app.middleware("http")
async def _allow_framing(request, call_next):
    """전시 사이트가 이 앱을 iframe 에 넣을 수 있게 한다.

    X-Frame-Options 는 값이 있으면 무조건 막히므로(ALLOW-FROM 은 폐기됐다)
    아예 설정하지 않고, 후속 프록시가 붙였을 경우를 대비해 지운다. 대신
    표준인 CSP frame-ancestors 를 쓴다.

    DAON_FRAME_ANCESTORS 로 특정 도메인만 허용할 수 있다. 기본은 전시 사이트
    도메인을 아직 모르므로 전체 허용이다.
    """
    response = await call_next(request)
    if "x-frame-options" in response.headers:
        del response.headers["x-frame-options"]   # MutableHeaders 에는 pop 이 없다
    response.headers["Content-Security-Policy"] = (
        "frame-ancestors " + os.environ.get("DAON_FRAME_ANCESTORS", "*"))
    return response


app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(home_router)
app.include_router(consulting_router)
app.include_router(live_router)


@app.on_event("startup")
def _startup():
    db.init_db()
    _seed()
    _warm_yolo()


def _seed():
    """시연 계정을 보장한다. 멱등이라 재시작마다 돌아도 안전하다.

    Dockerfile 의 CMD 에도 `python -m webservice.seed` 가 있지만, 배포 플랫폼에서
    시작 명령을 직접 지정하면(Railway/Render 의 Start Command) 그 CMD 가 통째로
    무시된다. 그러면 DB 는 비어 있는데 서명 키(DAON_SECRET)는 그대로라 예전
    세션 쿠키가 계속 유효하고, 결과적으로 '로그인은 되어 있는데 저장이 전부
    FOREIGN KEY 로 실패하는' 상태가 된다. 여기서 한 번 더 부르면 서버가 어떻게
    기동되든 계정이 존재한다.

    DAON_SKIP_SEED=1 로 끌 수 있다(빈 DB 로 시작하고 싶은 테스트용).
    """
    if os.environ.get("DAON_SKIP_SEED") == "1":
        return
    try:
        from webservice.seed import seed_demo
        seed_demo()
    except Exception as exc:                  # noqa: BLE001 - 시드 실패로 서버를 죽이지 않는다
        print(f"[seed] 건너뜀: {exc}")


def _warm_yolo():
    """YOLO 가중치를 미리 읽어둔다(백그라운드 스레드, 실패해도 서버는 뜬다).

    첫 컨설팅 요청이 모델 로딩까지 떠안으면 체감 대기가 몇 초 늘어난다. 서버가
    뜰 때 미리 해두면 사용자는 추론 시간만 기다린다. DAON_SKIP_WARMUP=1 이면
    건너뛴다(테스트·개발에서 torch 로딩을 강제하지 않기 위해).
    """
    if os.environ.get("DAON_SKIP_WARMUP") == "1":
        return

    def run():
        try:
            from webservice.consulting.analyze import warmup
            warmup()
            print("[warmup] YOLO 모델 준비 완료")
        except Exception as exc:                  # noqa: BLE001 - 워밍업 실패는 치명적이지 않다
            print(f"[warmup] 건너뜀: {exc}")

    threading.Thread(target=run, daemon=True).start()


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/metrics")
def get_metrics():
    """전시 중 부하 확인용. 개인정보는 없고 카운터만 있다.

    live 항목의 이름·값은 /api/live/status 와 같아야 한다 — 두 엔드포인트가 다른
    숫자를 말하면 어느 쪽도 믿을 수 없다.
    """
    from webservice import routes_live
    from webservice.consulting import jobs

    m = metrics.counter.snapshot()
    m["jobs"] = jobs.stats()
    m["live"] = {
        "self_sessions": routes_live.self_limiter.active,
        "self_max": routes_live.self_limiter.limit,
        "viewers": len(routes_live.manager._clients),
        "frames": routes_live.frames.seq,
    }
    return m


def _parse_range(header, size):
    """`Range: bytes=start-end` 를 (start, end) 로 판다. 못 다루면 None.

    다중 구간(`bytes=0-99,200-299`)은 지원하지 않는다 — 브라우저의 영상
    탐색은 항상 단일 구간이고, multipart/byteranges 응답을 만들 이유가 없다.
    """
    if not header or not header.strip().lower().startswith("bytes="):
        return None
    spec = header.split("=", 1)[1].strip()
    if "," in spec:
        return None
    start_s, _, end_s = spec.partition("-")
    try:
        if not start_s:                       # 'bytes=-500' → 마지막 500바이트
            length = int(end_s)
            if length <= 0:
                return None
            return max(0, size - length), size - 1
        start = int(start_s)
        end = int(end_s) if end_s else size - 1
    except ValueError:
        return None
    end = min(end, size - 1)
    if start > end or start >= size:
        return None
    return start, end


def ranged_file_response(request, path, chunk=64 * 1024):
    """Range 요청을 처리하는 파일 응답.

    **왜 직접 만드나.** starlette 0.37.2 의 FileResponse 는 Range 헤더를 아예
    무시하고 항상 200 + 파일 전체를 돌려준다(Range 지원은 0.45 에서 들어왔고,
    fastapi 0.111 이 그 이전 버전을 고정한다). 브라우저는 Accept-Ranges 가 없고
    206 도 못 받으면 아직 안 받은 지점으로 건너뛰지 못한다 — 영상 재생바를
    끌어도 되돌아오는, '가끔 스크롤이 안 되는' 증상의 정체다. 파일이 이미 캐시에
    다 들어와 있으면 잘 되기 때문에 새로고침 후에는 멀쩡해 보였다.

    응답 크기가 커도 메모리는 chunk 만큼만 쓴다(제너레이터로 흘려보낸다).
    """
    size = os.path.getsize(path)
    media_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
    headers = {"accept-ranges": "bytes"}

    rng = _parse_range(request.headers.get("range"), size)
    if rng is None:
        # 범위 요청이 아니거나 해석할 수 없는 범위 → 평소대로 전체를 준다.
        # (해석 못 한 범위에 416 을 주면 헤더가 조금만 특이해도 영상이 통째로
        #  안 나온다. 전체를 주면 최소한 재생은 된다.)
        return FileResponse(path, media_type=media_type, headers=headers)

    start, end = rng
    length = end - start + 1

    def stream():
        with open(path, "rb") as f:
            f.seek(start)
            left = length
            while left > 0:
                block = f.read(min(chunk, left))
                if not block:
                    break
                left -= len(block)
                yield block

    headers["content-range"] = f"bytes {start}-{end}/{size}"
    headers["content-length"] = str(length)
    return StreamingResponse(stream(), status_code=206, media_type=media_type,
                             headers=headers)


# 빌드된 React SPA 를 같은 서버에서 서빙한다(단일 서버 시연). dist 가 없으면
# (빌드 전/테스트) 이 블록은 건너뛰므로 API 전용으로 동작한다.
_DIST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend", "dist")
if os.path.isdir(_DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(_DIST, "assets")),
              name="assets")

    # GET 뿐 아니라 HEAD 도 받는다. 프런트가 샘플 영상 존재 여부를 HEAD 로
    # 확인하는데, GET 만 열어두면 405 가 돌아와 '영상을 준비 중입니다'로
    # 잘못 표시된다(파일은 멀쩡히 있는데 카드가 죽는다).
    @app.api_route("/{full_path:path}", methods=["GET", "HEAD"])
    def spa(full_path: str, request: Request):
        # /api·/ws 를 제외한 모든 경로는 index.html 로 돌려 클라이언트 라우팅을
        # 유지한다(/login, /mypage, /live 새로고침에도 안 깨지게).
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404)

        # dist 에 실제로 있는 파일(폰트·샘플 영상·데모 영상 등 public/ 산출물)은
        # 그대로 내보낸다. 이 분기가 없으면 /fonts/*.ttf 요청에 index.html 이
        # 돌아가 폰트·영상이 배포에서 전부 깨진다. realpath 검사는 ../ 로 dist
        # 밖을 읽어가는 경로 탈출을 막는다.
        if full_path:
            candidate = os.path.realpath(os.path.join(_DIST, full_path))
            if candidate.startswith(os.path.realpath(_DIST) + os.sep) \
                    and os.path.isfile(candidate):
                return ranged_file_response(request, candidate)

        # index.html 은 캐시 금지. 번들 파일명(assets/index-XXXX.js)은 빌드마다
        # 바뀌는 해시라 마음껏 캐시해도 되지만, 그 파일명을 담고 있는 index.html
        # 이 캐시되면 배포 후에도 브라우저가 옛 번들을 계속 연다 — 새 버전을
        # 올렸는데 관람객에게 옛 화면이 보이는 사고의 원인이다.
        return FileResponse(os.path.join(_DIST, "index.html"),
                            headers={"Cache-Control": "no-cache"})
