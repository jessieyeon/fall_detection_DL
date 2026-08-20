"""Sentry 초기화. 환경변수가 없으면 아무 일도 하지 않는다.

**왜 별도 모듈인가.** app.py 는 이미 세션·임베드·SPA 서빙으로 붐빈다.
그리고 Sentry 는 `FastAPI()` 를 만들기 *전에* 초기화해야 통합이 제대로 붙으므로
임포트 순서가 중요한 코드다 — 한 곳에 모아두는 편이 실수를 줄인다.

**끄는 방법.** `SENTRY_DSN` 을 지우면 된다. 로컬 개발에서는 설정하지 않는 것을
전제로 만들었다. 내 노트북에서 낸 에러가 전시 대시보드를 더럽히면
"진짜 관람객이 겪은 에러"를 골라낼 수 없게 된다.
"""

import os


def init_sentry() -> bool:
    """설정돼 있으면 Sentry 를 켠다. 켰으면 True.

    실패해도 예외를 올리지 않는다. 모니터링이 안 붙는 것보다
    서버가 안 뜨는 게 훨씬 나쁘다.
    """
    dsn = os.environ.get("SENTRY_DSN", "").strip()
    if not dsn:
        return False

    try:
        import sentry_sdk
    except Exception as exc:                  # noqa: BLE001
        print(f"[sentry] 건너뜀 (임포트 실패): {exc}")
        return False

    try:
        sentry_sdk.init(
            dsn=dsn,
            environment=os.environ.get("SENTRY_ENV", "production"),
            # 배포한 커밋을 알면 "언제부터 터지기 시작했는지"를 볼 수 있다.
            # Railway/Render 가 커밋 SHA 를 환경변수로 넣어준다.
            release=(os.environ.get("RAILWAY_GIT_COMMIT_SHA")
                     or os.environ.get("RENDER_GIT_COMMIT")
                     or None),

            # 성능 추적 샘플링. 무료 티어는 이벤트 수에 한도가 있고, 전시 중
            # 트래픽이 몰리면 하루 만에 다 쓸 수 있다. 에러는 100% 받고
            # (그게 이걸 붙인 이유다) 성능 트레이스만 표본으로 받는다.
            traces_sample_rate=float(os.environ.get("SENTRY_TRACES_RATE", "0.1")),

            # 관람객 IP·쿠키를 Sentry 로 보내지 않는다. 전시 앱이고 개인정보를
            # 밖으로 내보낼 이유가 없다. 기본값이 False 지만 명시해 둔다 —
            # 나중에 누가 켜려 할 때 이 주석을 읽게 하려고.
            send_default_pii=False,

            # 업로드된 영상 경로 같은 지역 변수는 남겨도 무해하지만,
            # 스택 프레임의 로컬 변수를 통째로 보내면 이벤트가 커진다.
            max_request_body_size="small",

            before_send=_scrub,
        )
    except Exception as exc:                  # noqa: BLE001
        print(f"[sentry] 건너뜀 (초기화 실패): {exc}")
        return False

    print("[sentry] 활성화됨")
    return True


# 이 에러들은 '고장'이 아니라 정상 동작이라 알림을 받을 이유가 없다.
#   - 503: 동시 분석 상한에 걸려 우리가 의도적으로 거절한 것 (DEPLOY.md §7)
#   - 401: 세션 만료 → 로그인 화면으로 보내는 정상 흐름 (routes_auth 참고)
#   - 404: SPA 라우팅과 봇 스캔이 상시 만들어낸다
_IGNORED_STATUS = {401, 403, 404, 405, 503}


def _scrub(event, hint):
    """노이즈를 걸러낸다. None 을 돌려주면 전송하지 않는다.

    이 필터가 없으면 전시 첫날 봇 스캔 404 와 혼잡 시 503 이 대시보드를 덮어
    정작 봐야 할 진짜 에러가 묻힌다.
    """
    exc = (hint or {}).get("exc_info")
    if exc:
        err = exc[1]
        status = getattr(err, "status_code", None)
        if status in _IGNORED_STATUS:
            return None
        # 관람객이 탭을 닫거나 폰이 절전으로 들어가면 스트리밍·웹소켓이
        # 끊긴다. 하루에도 수백 번 나지만 우리가 고칠 것은 없다.
        if isinstance(err, (ConnectionResetError, BrokenPipeError)):
            return None
        if err.__class__.__name__ in {
            "ClientDisconnect", "WebSocketDisconnect", "CancelledError",
        }:
            return None
    return event
