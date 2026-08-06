#!/usr/bin/env python3
"""연결 가능한 카메라를 훑어 인덱스와 해상도를 보여준다.

    python3 scripts/list_cameras.py
    python3 scripts/list_cameras.py --preview 1      # 1번 카메라 화면 확인

맥에서 아이폰을 '연속성 카메라'로 쓰면 내장 카메라와 별도 인덱스로 잡힌다.
어느 번호가 아이폰인지는 환경마다 달라서 직접 열어보는 수밖에 없다.
찾은 번호를 main.py 의 첫 인자로 넘기면 된다.

    python3 main.py 1 --no-serial --live-url http://localhost:8000
"""

import argparse
import sys


def probe(index):
    """카메라를 열어보고 (열림, 폭, 높이, fps). 실패하면 (False, ...)."""
    import cv2
    cap = cv2.VideoCapture(index)
    try:
        if not cap.isOpened():
            return False, 0, 0, 0.0
        ok, frame = cap.read()          # isOpened 만으로는 부족 — 실제로 읽혀야 한다
        if not ok or frame is None:
            return False, 0, 0, 0.0
        h, w = frame.shape[:2]
        return True, w, h, cap.get(cv2.CAP_PROP_FPS) or 0.0
    finally:
        cap.release()


def preview(index):
    import cv2
    cap = cv2.VideoCapture(index)
    if not cap.isOpened():
        sys.exit(f"카메라 {index} 를 열 수 없습니다.")
    print(f"카메라 {index} 미리보기 — 창을 클릭하고 ESC 를 누르면 종료합니다.")
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            cv2.putText(frame, f"camera {index}", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)
            cv2.imshow(f"camera {index}", frame)
            if (cv2.waitKey(1) & 0xFF) == 27:
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=6, help="확인할 최대 인덱스 (기본 6)")
    ap.add_argument("--preview", type=int, default=None, metavar="N",
                    help="해당 인덱스의 화면을 띄워 확인한다")
    args = ap.parse_args()

    if args.preview is not None:
        preview(args.preview)
        return

    print("카메라를 찾는 중… (macOS 는 첫 실행 시 카메라 권한을 물어봅니다)\n")
    found = []
    for i in range(args.max):
        ok, w, h, fps = probe(i)
        if ok:
            found.append(i)
            print(f"  [{i}]  {w}x{h}  {fps:.0f}fps")
        else:
            print(f"  [{i}]  —")

    if not found:
        print("\n사용 가능한 카메라가 없습니다.")
        print("  · macOS: 시스템 설정 → 개인정보 보호 및 보안 → 카메라에서 터미널 허용")
        print("  · 아이폰 연속성 카메라: 같은 Apple 계정, Wi-Fi·Bluetooth 켜짐,")
        print("    아이폰을 세로로 세워 잠금 해제 상태로 맥 근처에 두세요")
        return

    print(f"\n찾은 카메라: {found}")
    print("어느 것이 아이폰인지 화면으로 확인하세요:")
    for i in found:
        print(f"  python3 scripts/list_cameras.py --preview {i}")
    print("\n확인한 번호로 실행:")
    print(f"  python3 main.py {found[-1]} --no-serial --live-url http://localhost:8000")


if __name__ == "__main__":
    main()
