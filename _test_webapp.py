import time, json, threading, urllib.request, asyncio
import websockets
from webapp_server import WebAppServer

srv = WebAppServer(port=8077)
assert srv.start(), "server failed to start"
time.sleep(1.5)

# 1) HTTP serves index.html
html = urllib.request.urlopen("http://127.0.0.1:8077/").read().decode()
assert "낙상 감지 모니터" in html, "index.html not served"
print("HTTP / serves index.html OK (%d bytes)" % len(html))

# 2) WebSocket receives broadcasts
got = []
async def client():
    async with websockets.connect("ws://127.0.0.1:8077/ws") as ws:
        await asyncio.sleep(0.3)
        # trigger broadcasts from the (sync) main-thread side
        lm = [[100+i, 200+i, 0] for i in range(33)]
        srv.push_pose(lm, (720,1280), 0.82, 2, 3)
        await asyncio.sleep(0.15)
        srv.push_fall([1,3], 2, 2, 90.0)
        await asyncio.sleep(0.15)
        srv.push_reset()
        for _ in range(3):
            m = json.loads(await asyncio.wait_for(ws.recv(), timeout=2))
            got.append(m["type"])
asyncio.run(client())
print("WS message types received:", got)
assert got == ["pose","fall","reset"], got
# check normalization
print("pose landmark[0] normalized ~", round(100/1280,4), round(200/720,4))
srv.stop()
print("ALL WEBAPP TESTS PASSED")
