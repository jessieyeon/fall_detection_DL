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
