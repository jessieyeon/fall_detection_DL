import asyncio
from webservice import live


def test_pose_message_normalizes():
    msg = live.pose_message([(50, 100, 0.9), (150, 50, 0.8)], (200, 300),
                            0.42, 2, 3)
    assert msg["type"] == "pose"
    assert msg["landmarks"] == [[round(50/300, 4), round(100/200, 4)],
                                [round(150/300, 4), round(50/200, 4)]]
    assert msg["risk"] == 0.42 and msg["prog"] == [2, 3]


def test_pose_message_none_landmarks():
    msg = live.pose_message(None, (200, 300), 0.1, 0, 3)
    assert msg["landmarks"] is None


def test_fall_and_reset_messages():
    f = live.fall_message([1, 3], 2, 2, 178.5)
    assert f == {"type": "fall", "tiles": [1, 3], "rows": 2, "cols": 2,
                 "direction": 178.5}
    assert live.reset_message() == {"type": "reset"}


class _FakeWS:
    def __init__(self, fail=False):
        self.sent = []
        self.fail = fail
    async def send_json(self, data):
        if self.fail:
            raise RuntimeError("dead")
        self.sent.append(data)


def test_manager_broadcast_and_prune_dead():
    mgr = live.ConnectionManager()
    good, dead = _FakeWS(), _FakeWS(fail=True)

    async def scenario():
        await mgr.connect(good)
        await mgr.connect(dead)
        await mgr.broadcast({"type": "reset"})

    asyncio.run(scenario())
    assert good.sent == [{"type": "reset"}]
    assert dead not in mgr._clients          # 죽은 연결 제거됨
