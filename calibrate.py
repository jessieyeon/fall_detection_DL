import sys
import json
import cv2
import numpy as np

CALIBRATION_FILE = "calibration.json"

points = []


def on_mouse(event, x, y, flags, param):
    if event == cv2.EVENT_LBUTTONDOWN and len(points) < 4:
        points.append([x, y])
        print(f"point {len(points)}: ({x}, {y})")


def main():
    if len(sys.argv) < 3:
        print("usage: python3 calibrate.py <rows> <cols> [video_source]")
        sys.exit(1)

    rows = int(sys.argv[1])
    cols = int(sys.argv[2])
    video_source = 0
    if len(sys.argv) > 3:
        video_source = int(sys.argv[3]) if sys.argv[3].isdigit() else sys.argv[3]

    video = cv2.VideoCapture(video_source)
    ret, frame = video.read()
    video.release()
    if not ret:
        print("Could not read a frame from the video source.")
        sys.exit(1)

    cv2.namedWindow("Calibration")
    cv2.setMouseCallback("Calibration", on_mouse)

    print("Click the 4 corners of the tile-covered floor area, in order:")
    print("1) top-left  2) top-right  3) bottom-right  4) bottom-left")
    print("Tiles are numbered 0..N-1 in row-major order (row 0 left-to-right, then row 1, ...).")
    print("Press 'r' to reset, ESC to cancel.")

    while True:
        display = frame.copy()
        for i, p in enumerate(points):
            cv2.circle(display, (p[0], p[1]), 6, (0, 0, 255), -1)
            cv2.putText(display, str(i + 1), (p[0] + 8, p[1]), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
        if len(points) == 4:
            pts = np.array(points, dtype=np.int32).reshape(-1, 1, 2)
            cv2.polylines(display, [pts], True, (0, 255, 0), 2)
            cv2.putText(display, "press any key to save, 'r' to reset", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        cv2.imshow("Calibration", display)

        k = cv2.waitKey(30) & 0xFF
        if k == 27:
            cv2.destroyAllWindows()
            sys.exit(0)
        if k == ord('r'):
            points.clear()
            continue
        if len(points) == 4 and k != 255:
            break

    cv2.destroyAllWindows()

    with open(CALIBRATION_FILE, "w") as f:
        json.dump({"rows": rows, "cols": cols, "floor_corners_px": points}, f, indent=2)
    print(f"Saved calibration ({rows}x{cols} grid, {rows * cols} tiles) to {CALIBRATION_FILE}")


if __name__ == "__main__":
    main()
