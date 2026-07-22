"""낙상 직전 감지 -> 방향 판정 -> 멀티 타일 작동.

사용법:
    python main.py                                    웹캠
    python main.py test_videos/S01T13R01_.mp4         녹화 영상
    python main.py --port /dev/cu.usbmodemXXXX        아두이노 연결
    python main.py --profile doll                     인형 프로파일
    python main.py --no-serial                        임계값 튜닝용 (서보 안 움직임)
"""

import argparse
import csv
import os
import sys
from collections import deque
from datetime import datetime

import cv2

import calibration
import config
import pose_source
import tile_protocol
import tiles

RISK_COOLDOWN = 3.0    # 같은 낙상에 대해 다시 발사하기까지 기다리는 시간(초)
RESET_DELAY = 2.0      # 발사 후 원위치 신호를 보내기까지의 시간(초)
LOG_FILE = "fall_risk_log.csv"

LOG_HEADER = ["timestamp", "person", "risk_score", "direction_deg",
              "lean_ratio", "R", "tier", "fired_tiles", "ack", "profile"]


def parse_args():
    parser = argparse.ArgumentParser(description="낙상 직전 감지 및 멀티 타일 작동")
    parser.add_argument("video_source", nargs="?", default="0",
                        help="웹캠 인덱스(기본 0) 또는 영상 파일 경로")
    parser.add_argument("--port", default=None,
                        help="아두이노 시리얼 포트. 생략하면 시뮬레이션 모드")
    parser.add_argument("--profile", default=config.DEFAULT_PROFILE,
                        help="profiles.json 의 프로파일 이름 (human / doll)")
    parser.add_argument("--no-serial", action="store_true",
                        help="시리얼을 쓰지 않는다. 임계값 튜닝용")
    parser.add_argument("--face-every", type=int, default=0,
                        help="N프레임마다 얼굴 인식. 0이면 비활성(기본). "
                             "얼굴 인식은 느려서 fps 를 크게 떨어뜨린다")
    return parser.parse_args()


def log_event(profile_name, person, risk_score, direction_deg, lean_ratio,
              R, fired_tiles, ack):
    is_new = not os.path.isfile(LOG_FILE)
    with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(LOG_HEADER)
        writer.writerow([
            datetime.now().isoformat(timespec="seconds"),
            person,
            f"{risk_score:.3f}",
            f"{direction_deg:.1f}",
            f"{lean_ratio:.3f}",
            f"{R:.3f}",
            len(fired_tiles),
            "|".join(str(t) for t in sorted(fired_tiles)),
            int(bool(ack)),
            profile_name,
        ])


def build_face_recognizer(face_every):
    if face_every <= 0:
        return None
    import facial_recognition as fr

    recognizer = fr.FaceRecognition()
    recognizer.encode_faces()
    return recognizer


def main():
    args = parse_args()

    try:
        profile = config.load_profile(args.profile)
    except ValueError as exc:
        print(f"오류: {exc}")
        return 1
    print(f"프로파일 '{profile.name}' - persistence={profile.persistence}, "
          f"tau_R={profile.tau_R}, tau_R_strict={profile.tau_R_strict}, "
          f"tau_lean={profile.tau_lean}, window={profile.window}")

    video_source = int(args.video_source) if args.video_source.isdigit() else args.video_source

    tile_grid = calibration.load_tile_grid()
    rows = tile_grid["rows"] if tile_grid else 2
    cols = tile_grid["cols"] if tile_grid else 2

    controller = tile_protocol.TileController()
    if not args.no_serial:
        servo_count = controller.connect(args.port)
        if servo_count and servo_count != rows * cols:
            print(f"경고: 펌웨어 서보 {servo_count}개 vs 캘리브레이션 "
                  f"{rows}x{cols}={rows * cols}개 - 설정이 어긋났습니다.")
    else:
        print("--no-serial: 서보를 움직이지 않고 로그만 남깁니다.")

    model_bundle = pose_source.load_risk_model()
    prob_threshold = profile.prob_threshold
    persistence = profile.persistence

    source = pose_source.PoseSource(
        video_source=video_source,
        model_bundle=model_bundle,
        prob_threshold=prob_threshold,
        tile_grid=tile_grid,
        face_every=args.face_every,
        face_recognizer=build_face_recognizer(args.face_every),
    )

    window = deque(maxlen=profile.window)
    consecutive_risk_frames = 0
    last_risk_time = -RISK_COOLDOWN
    reset_pending = False
    active_tiles = set()

    try:
        for frame in source.frames():
            now = frame.timestamp

            if frame.landmarks is None:
                # 추적 상실 - 오래된 방향이 다음 낙상 판정에 섞이면 안 된다
                window.clear()
                consecutive_risk_frames = 0
            else:
                window.append((frame.direction_deg, frame.lean_ratio))
                consecutive_risk_frames = consecutive_risk_frames + 1 if frame.is_risky else 0

            if (consecutive_risk_frames >= persistence
                    and (now - last_risk_time) > RISK_COOLDOWN):
                direction_deg, R, lean_ratio = tiles.resolve_direction(window)
                fired = tiles.select_tiles(
                    direction_deg, R, lean_ratio, rows, cols,
                    profile.tau_R, profile.tau_R_strict, profile.tau_lean)

                ack = False if args.no_serial else controller.fire(fired)
                print(f"[낙상 위험] score={frame.risk_score:.2f} "
                      f"dir={direction_deg:.1f}도 R={R:.2f} lean={lean_ratio:.2f} "
                      f"-> 타일 {sorted(fired)} ({len(fired)}장) ack={ack}")
                log_event(profile.name, frame.face_name, frame.risk_score,
                          direction_deg, lean_ratio, R, fired, ack)

                active_tiles = fired
                last_risk_time = now
                consecutive_risk_frames = 0
                reset_pending = True

            if reset_pending and (now - last_risk_time) > RESET_DELAY:
                if not args.no_serial:
                    controller.reset()
                reset_pending = False
                active_tiles = set()

            image = frame.image
            if tile_grid is not None:
                calibration.draw_tile_grid(image, tile_grid, active_tiles)

            cv2.putText(image,
                        f"risk {frame.risk_score:.2f} "
                        f"({consecutive_risk_frames}/{persistence})",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
            if frame.direction_deg is not None:
                cv2.putText(image,
                            f"dir {frame.direction_deg:.0f} lean {frame.lean_ratio:.2f}",
                            (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 200, 255), 2)
            if controller.simulated and not args.no_serial:
                cv2.putText(image, "NO ARDUINO (simulated)", (10, 90),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

            cv2.imshow("Fall Detection", image)
            if (cv2.waitKey(1) & 0xFF) == 27:
                break
    except KeyboardInterrupt:
        print("종료...")

    # 미송된 reset 신호 처리
    if reset_pending and not args.no_serial:
        controller.reset()
    source.release()
    cv2.destroyAllWindows()
    controller.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
