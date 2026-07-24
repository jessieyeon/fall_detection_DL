"""카메라·아두이노 없이 앱을 테스트하기 위한 가짜 피드.

실행:
    python webapp_mock.py            # 포트 8000
    python webapp_mock.py --port 8080

맥에서 이걸 켠 뒤 같은 WiFi 의 폰에서 http://<맥_IP>:8000 을 열면,
서 있다가 주기적으로 한 방향으로 쓰러지는 가상 인물과, 그때 솟아오르는
타일·배너를 실제 파이프라인 없이 미리 확인할 수 있다.

낙상 감지 로직과는 무관하다. 앱(스켈레톤·타일·배너) 표시만 검증하는 용도다.
"""

import argparse
import math
import time

from webapp_server import WebAppServer

ROWS, COLS = 2, 2   # 2x2 = 타일 4개

# MediaPipe Pose 인덱스 기준의 대략적인 "서 있는 사람" 정규화 좌표(0~1).
# 앱이 실제로 그리는 관절만 채운다.
BASE = {
    0:  (0.50, 0.16),   # nose
    11: (0.44, 0.30), 12: (0.56, 0.30),   # shoulders
    13: (0.40, 0.45), 14: (0.60, 0.45),   # elbows
    15: (0.38, 0.58), 16: (0.62, 0.58),   # wrists
    23: (0.46, 0.55), 24: (0.54, 0.55),   # hips
    25: (0.45, 0.72), 26: (0.55, 0.72),   # knees
    27: (0.45, 0.88), 28: (0.55, 0.88),   # ankles
}


def make_landmarks(lean, sway):
    """lean: 0=직립, 1=완전히 누움. sway: 좌우 흔들림. 발은 고정하고 상체를 기울인다."""
    pts = [[0.0, 0.0] for _ in range(33)]
    pivot_y = 0.55
    for i, (x, y) in BASE.items():
        # 발목 아래는 고정, 위로 올라갈수록 기울기 영향을 크게.
        height_factor = max(0.0, (pivot_y - y)) if y < pivot_y else 0.0
        dx = lean * height_factor * 1.6 + math.sin(sway) * 0.02 * height_factor * 6
        dy = lean * height_factor * height_factor * 1.2   # 쓰러지며 상체가 내려앉음
        pts[i] = [min(0.98, max(0.02, x + dx)), min(0.98, max(0.02, y + dy))]
    return pts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()

    server = WebAppServer(port=args.port)
    if not server.start():
        return
    time.sleep(1.0)
    print("[목업] 서 있음 → 주기적으로 낙상 시뮬레이션. Ctrl+C 로 종료.")

    persistence = 3
    fps = 20.0
    tile_cycle = [1, COLS - 1, ROWS * COLS - 1, (ROWS - 1) * COLS]  # 여러 위치 번갈아
    cycle_i = 0
    t = 0.0
    try:
        while True:
            # 6초 주기: 4초 서 있기(흔들), 1.2초 쓰러짐, 발사, 0.8초 유지 후 리셋
            phase = t % 6.0
            if phase < 4.0:
                lean = 0.0
                risk = 0.05 + 0.05 * abs(math.sin(t * 2))
                consec = 0
            elif phase < 5.2:
                p = (phase - 4.0) / 1.2
                lean = min(1.0, p * 1.1)
                risk = 0.4 + 0.55 * p
                consec = min(persistence, int(p * (persistence + 1)))
            else:
                lean = 1.0
                risk = 0.9
                consec = persistence

            server.push_pose(make_landmarks(lean, t * 3), (720, 1280),
                             risk, consec, persistence)

            # 쓰러짐이 완료되는 순간 한 번 발사, 다음 주기 시작에 리셋
            if abs(phase - 5.2) < (1.0 / fps):
                fired = [tile_cycle[cycle_i % len(tile_cycle)]]
                cycle_i += 1
                server.push_fall(fired, ROWS, COLS, 90.0 * (cycle_i % 4))
                print(f"[목업] 낙상! 타일 {fired}")
            if abs(phase - 0.0) < (1.0 / fps) and t > 1.0:
                server.push_reset()

            t += 1.0 / fps
            time.sleep(1.0 / fps)
    except KeyboardInterrupt:
        print("\n[목업] 종료")
        server.stop()


if __name__ == "__main__":
    main()
