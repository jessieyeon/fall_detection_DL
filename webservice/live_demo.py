"""카메라 없이 /live 를 시연·검증하기 위한 합성 이벤트 푸셔.

    python -m webservice.live_demo [--host http://localhost:8000] [--token daon-live]

움직이는 스켈레톤을 몇 초간 흘려보내고, 한 번 낙상(타일 발사) 후 리셋한다.
"""

import argparse
import math
import time

import httpx

from webservice import live


def _fake_landmarks(t):
    # 33개 관절을 대충 사람 형태로 배치하고 좌우로 흔든다(픽셀 좌표, 640x480 가정).
    sway = 40 * math.sin(t * 2)
    cx = 320 + sway
    pts = []
    for i in range(33):
        y = 60 + i * 12                       # 위에서 아래로 늘어놓기
        x = cx + (20 if i % 2 else -20)
        pts.append((x, y, 0.9))
    return pts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="http://localhost:8000")
    ap.add_argument("--token", default="daon-live")
    args = ap.parse_args()
    headers = {"X-Live-Token": args.token}

    def post(msg):
        try:
            httpx.post(f"{args.host}/api/live/event", json=msg,
                       headers=headers, timeout=2)
        except Exception as exc:
            print("push 실패:", exc)

    print("[live_demo] 합성 스켈레톤 전송 중… Ctrl+C 로 종료")
    t = 0.0
    try:
        while True:
            post(live.pose_message(_fake_landmarks(t), (480, 640),
                                   risk=min(0.95, 0.1 + t * 0.05),
                                   consec=min(3, int(t)), persistence=3))
            if 4.0 < t < 4.2:
                post(live.fall_message([2, 3], 2, 2, 178.9))
            if 6.0 < t < 6.2:
                post(live.reset_message())
                t = 0.0
            time.sleep(0.1)
            t += 0.1
    except KeyboardInterrupt:
        print("\n종료")


if __name__ == "__main__":
    main()
