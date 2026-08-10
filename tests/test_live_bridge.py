import time
import json

import httpx

from webservice import live_bridge


def _bridge(handler, token="daon-live"):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return live_bridge.LiveBridge("http://platform/", token=token, client=client)


def test_start_true_on_health_200():
    def handler(req):
        assert req.url.path == "/api/health"
        return httpx.Response(200, json={"status": "ok"})
    assert _bridge(handler).start() is True


def test_start_false_when_unreachable():
    def handler(req):
        raise httpx.ConnectError("nope")
    assert _bridge(handler).start() is False


def test_push_fall_posts_message_with_token():
    seen = {}

    def handler(req):
        seen["path"] = req.url.path
        seen["token"] = req.headers.get("X-Live-Token")
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json={"delivered": 1})

    _bridge(handler).push_fall([1, 3], 2, 2, 178.9)
    assert seen["path"] == "/api/live/event"
    assert seen["token"] == "daon-live"
    assert seen["body"] == {"type": "fall", "tiles": [1, 3], "rows": 2,
                            "cols": 2, "direction": 178.9}


def test_push_pose_normalizes_and_throttles():
    calls = []

    def handler(req):
        calls.append(json.loads(req.content))
        return httpx.Response(200, json={"delivered": 1})

    b = _bridge(handler)
    b.push_pose([(150, 100, 0.9)], (200, 300), 0.42, 2, 3)
    b.push_pose([(150, 100, 0.9)], (200, 300), 0.42, 2, 3)   # 즉시 두 번째 → throttle
    assert len(calls) == 1                                    # 한 번만 전송
    assert calls[0]["type"] == "pose"
    assert calls[0]["landmarks"] == [[round(150 / 300, 4), round(100 / 200, 4)]]


def test_push_reset_never_raises_on_failure():
    def handler(req):
        raise httpx.ConnectError("down")
    _bridge(handler).push_reset()          # 예외가 밖으로 새면 테스트 실패


# --- 전송 스레드: 영상 루프를 막지 않는다 ---

def _slow_bridge(delay, seen):
    """요청 하나에 delay 초가 걸리는 느린 서버(=원격 배포)를 흉내낸다."""
    def handler(req):
        time.sleep(delay)
        seen.append(req.url.path)
        return httpx.Response(200, json={"delivered": 1})
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return live_bridge.LiveBridge("http://platform/", client=client)


def test_push_pose_does_not_block_on_a_slow_server():
    """회귀 테스트: 예전에는 영상 루프 안에서 직접 POST 해서, 배포 서버로 바꾸면
    왕복 지연만큼 카메라를 못 읽고 화면이 뚝뚝 끊겼다."""
    seen = []
    b = _slow_bridge(0.3, seen)
    assert b.start() is True          # /api/health 한 번은 느려도 감수한다
    try:
        started = time.monotonic()
        for _ in range(5):
            b._last_pose = 0.0        # throttle 을 우회해 5번 다 밀어넣는다
            b.push_pose([(150, 100, 0.9)], (200, 300), 0.42, 2, 3)
        elapsed = time.monotonic() - started
    finally:
        b.stop()
    # 5번 × 0.3초 = 1.5초가 걸리면 예전 동작이다. 큐에 놓기만 하니 즉시 끝나야 한다.
    assert elapsed < 0.2


def test_should_pause_does_not_block_on_a_slow_server():
    seen = []
    b = _slow_bridge(0.3, seen)
    assert b.start() is True
    try:
        started = time.monotonic()
        for _ in range(20):
            b.should_pause()
        assert time.monotonic() - started < 0.2
    finally:
        b.stop()


def test_queued_events_are_eventually_delivered():
    seen = []
    b = _slow_bridge(0.01, seen)
    assert b.start() is True
    try:
        b.push_fall([1], 2, 2, 90.0)
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and "/api/live/event" not in seen:
            time.sleep(0.02)
    finally:
        b.stop()
    assert "/api/live/event" in seen


def test_stale_poses_are_dropped_rather_than_queued():
    """밀린 포즈는 최신 것만 남는다 - 따라 보내봐야 이미 지난 장면이다.

    느린 서버에 포즈 20개를 몰아넣고, 전송된 개수가 훨씬 적은지 본다. 전부
    전송된다면 큐가 쌓이고 있다는 뜻이고, 그러면 화면이 실시간에서 점점
    뒤처진다.
    """
    seen = []
    b = _slow_bridge(0.2, seen)
    assert b.start() is True
    try:
        for i in range(20):
            b._last_pose = 0.0                 # throttle 우회
            b.push_pose([(150, 100, 0.9)], (200, 300), 0.42, i, 3)
        time.sleep(0.9)
    finally:
        b.stop()
    poses = [p for p in seen if p == "/api/live/event"]
    assert len(poses) < 10, f"큐가 쌓였다: {len(poses)}건 전송"


def test_push_pose_without_start_still_sends_inline():
    """start() 를 안 부르면(테스트·합성 푸셔) 예전처럼 그 자리에서 보낸다."""
    calls = []

    def handler(req):
        calls.append(json.loads(req.content))
        return httpx.Response(200, json={"delivered": 1})

    _bridge(handler).push_pose([(150, 100, 0.9)], (200, 300), 0.42, 2, 3)
    assert len(calls) == 1
