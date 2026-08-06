#!/usr/bin/env python3
"""컨설팅 분석 속도 벤치마크 — 최적화 전/후를 같은 영상으로 비교한다.

사용법:

    python3 scripts/bench_consulting.py test_videos/S01T13R01_.mp4
    python3 scripts/bench_consulting.py my.mp4 --old        # 예전 설정도 함께 측정
    python3 scripts/bench_consulting.py my.mp4 --out bench/ # 리포트 이미지 저장

'예전 설정'은 최적화 전 코드와 같은 조건(모든 프레임 + yolo11m + track + imgsz 640)이다.
느리므로 짧은 영상에만 --old 를 붙일 것. 30초 영상에서 몇 분 걸린다.
"""

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from webservice.consulting import analyze, heatmap, rules  # noqa: E402


def _video_info(path):
    import cv2
    if not os.path.exists(path):
        raise SystemExit(
            f"파일이 없습니다: {path}\n"
            f"  현재 위치: {os.getcwd()}\n"
            "  터미널 창에 영상 파일을 드래그해서 놓으면 전체 경로가 입력됩니다.")
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise SystemExit(
            f"영상을 열 수 없습니다: {path}\n"
            "  파일은 있는데 디코딩에 실패했습니다. 아이폰 .mov 는 보통\n"
            "  HEVC(H.265)라 OpenCV 빌드에 따라 못 읽습니다. H.264 로 변환하세요:\n\n"
            f"    ffmpeg -i {path} -vcodec libx264 -acodec aac converted.mp4\n\n"
            "  ffmpeg 가 없으면:  brew install ffmpeg")
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 0
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    return n, fps, w, h


def _all_frames(path):
    """예전 방식: 프레임을 하나도 건너뛰지 않는다."""
    import cv2
    cap = cv2.VideoCapture(path)
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            yield frame
    finally:
        cap.release()


def _old_detector():
    """최적화 전 설정: yolo11m + track() + imgsz 기본(640)."""
    from ultralytics import YOLO
    model = YOLO("yolo11m.pt")

    def detect(frame):
        results = model.track(frame, persist=True, classes=[0],
                              conf=0.15, iou=0.45, verbose=False)
        boxes = []
        if results and results[0].boxes is not None:
            for b in results[0].boxes.xyxy.cpu().numpy():
                boxes.append(tuple(float(v) for v in b))
        return boxes

    return detect


def _count_frames(path, target_fps):
    return sum(1 for _ in analyze._iter_frames(path, target_fps=target_fps))


def run_new(path):
    """로딩·추론·후처리를 각각 잰다.

    총 시간만 보면 짧은 영상에서는 모델 로딩이 대부분을 차지해 추론 성능을
    오판하게 된다. 서버에서는 로딩이 기동 시 한 번뿐이므로 사용자가 실제로
    기다리는 건 '추론 + 후처리'다.
    """
    t0 = time.perf_counter()
    analyze.warmup()                    # 가중치 로딩 + 최초 추론
    load_t = time.perf_counter() - t0

    detect = analyze._yolo_detector()
    frames = list(analyze._iter_frames(path))

    per_frame = []
    boxes_per_frame = []
    t1 = time.perf_counter()
    for frame in frames:
        f0 = time.perf_counter()
        boxes = detect(frame)
        per_frame.append(time.perf_counter() - f0)
        boxes_per_frame.append(boxes)
    infer_t = time.perf_counter() - t1

    t2 = time.perf_counter()
    h, w = frames[0].shape[:2]
    segments = heatmap.extract_path(boxes_per_frame, h, w)
    pmap = heatmap.accumulate_passage_map(segments, h, w)
    post_t = time.perf_counter() - t2

    detected = sum(1 for b in boxes_per_frame if b)
    stats = {
        "load": load_t, "infer": infer_t, "post": post_t,
        "frames": len(frames), "detected": detected,
        "per_frame": per_frame,
        "raw_points": len(heatmap.split_segments(
            heatmap.foot_points(boxes_per_frame))),
    }
    return stats, pmap, frames[0], segments, boxes_per_frame


def run_old(path):
    t0 = time.perf_counter()
    hm, first = analyze.frames_to_heatmap(_all_frames(path), _old_detector())
    return time.perf_counter() - t0, hm, first


def sweep(path):
    """샘플링 fps × 입력 크기 조합을 훑어 속도와 동선 밀도를 함께 본다.

    속도만 보고 고르면 동선 점이 너무 적어져 리포트가 무의미해지고, 밀도만
    보고 고르면 느려진다. 둘을 같이 봐야 고를 수 있다.
    """
    analyze.warmup()
    combos = [(fps, imgsz) for fps in (2, 3, 5) for imgsz in (384, 512, 640, 960)]
    print(f"\n{'fps':>4} {'imgsz':>6} {'프레임':>6} {'검출률':>7} {'구간':>5} "
          f"{'동선점':>7} {'추론(초)':>9} {'ms/프레임':>10}")
    print("  " + "-" * 68)
    rows = []
    for target_fps, imgsz in combos:
        detect = analyze._yolo_detector(imgsz=imgsz)
        frames = list(analyze._iter_frames(path, target_fps=target_fps))
        t0 = time.perf_counter()
        boxes = [detect(f) for f in frames]
        infer_t = time.perf_counter() - t0
        h, w = frames[0].shape[:2]
        segs = heatmap.extract_path(boxes, h, w)
        pts = sum(len(s) for s in segs)
        rate = sum(1 for b in boxes if b) / max(len(frames), 1)
        rows.append((target_fps, imgsz, len(frames), rate, len(segs), pts, infer_t))
        print(f"{target_fps:>4} {imgsz:>6} {len(frames):>6} {rate:>6.0%} "
              f"{len(segs):>5} {pts:>7} {infer_t:>9.2f} "
              f"{infer_t/max(len(frames),1)*1000:>10.0f}")

    # 검출률이 낮으면 동선 점이 많아도 경로가 조각나 신뢰할 수 없다.
    # 속도(4초) → 검출률(80%) → 동선 밀도 순으로 거른다.
    ok = [r for r in rows if r[6] <= 4.0 and r[3] >= 0.8 and r[5] >= 15]
    print()
    if ok:
        best = min(ok, key=lambda r: r[4])       # 조건 통과 중 구간이 가장 안 쪼개진 것
        print(f"추천: DAON_ANALYZE_FPS={best[0]} DAON_YOLO_IMGSZ={best[1]}")
        print(f"      검출률 {best[3]:.0%}, 구간 {best[4]}개, 동선 {best[5]}점, "
              f"추론 {best[6]:.2f}초")
    else:
        best_rate = max(rows, key=lambda r: r[3])
        print("모든 조건(4초 이내 · 검출률 80% · 동선 15점)을 만족하는 조합이 없습니다.")
        print(f"  최고 검출률: {best_rate[3]:.0%} "
              f"(fps={best_rate[0]}, imgsz={best_rate[1]}, {best_rate[6]:.2f}초)")
        if best_rate[3] < 0.8:
            print("\n  검출률이 어디서도 80%를 못 넘으면 설정 문제가 아니라 영상 문제입니다:")
            print("   · 카메라가 움직이는 영상인가? (핸드헬드 촬영)")
            print("   · 사람이 프레임 밖으로 자주 나가는가?")
            print("   · 너무 어둡거나 역광인가?")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--old", action="store_true",
                    help="최적화 전 설정도 함께 측정 (느림)")
    ap.add_argument("--out", default=None, help="리포트 이미지를 저장할 폴더")
    ap.add_argument("--sweep", action="store_true",
                    help="fps × imgsz 조합을 훑어 최적 설정을 찾는다")
    args = ap.parse_args()

    if args.sweep:
        n, fps, w, h = _video_info(args.video)
        print(f"영상: {args.video}  ({n}프레임 / {fps:.1f}fps / {w}x{h} / "
              f"{n/fps if fps else 0:.1f}초)")
        sweep(args.video)
        return

    n, fps, w, h = _video_info(args.video)
    duration = n / fps if fps else 0
    print(f"영상: {args.video}")
    print(f"  {n} 프레임 / {fps:.1f} fps / {w}x{h} / {duration:.1f}초\n")

    print("현재 설정 (환경변수로 덮어쓸 수 있음)")
    print(f"  모델      DAON_YOLO_MODEL          = {analyze.MODEL_NAME}")
    print(f"  샘플링    DAON_ANALYZE_FPS         = {analyze.TARGET_FPS}")
    print(f"  입력크기  DAON_YOLO_IMGSZ          = {analyze.IMGSZ}")
    print(f"  최대길이  DAON_ANALYZE_MAX_SECONDS = {analyze.MAX_SECONDS}초")
    sampled = _count_frames(args.video, analyze.TARGET_FPS)
    print(f"  → 실제 추론 프레임 수: {sampled} (전체 {n} 중)\n")

    print("측정 중…")
    stats, pmap, first, segments, boxes_per_frame = run_new(args.video)
    report = rules.analyze_report(pmap)
    new_t = stats["infer"] + stats["post"]

    pf = sorted(stats["per_frame"])
    print(f"\n[최적화 후]")
    print(f"  모델 로딩   {stats['load']:6.2f}초  ← 서버에서는 기동 시 1회뿐")
    print(f"  추론        {stats['infer']:6.2f}초  ({stats['frames']}프레임, "
          f"중앙값 {pf[len(pf)//2]*1000:.0f}ms/프레임)")
    print(f"  후처리      {stats['post']:6.2f}초")
    print(f"  ── 사용자 체감 대기: {new_t:.2f}초 (로딩 제외)")

    rate = stats["detected"] / max(stats["frames"], 1)
    print(f"\n  사람 검출: {stats['detected']}/{stats['frames']} 프레임 ({rate:.0%})")
    print(f"  검출 구간 수: {stats['raw_points']}  →  동선 점: "
          f"{[len(s) for s in segments]} (총 {sum(len(s) for s in segments)}점)")

    # 동선 점이 적을 때 '정말 안 움직인 것' 과 '로직이 삼킨 것' 을 구분하기 위한
    # 원시 발끝 좌표 진단. 이동 범위가 min_step 보다 작으면 전자가 맞다.
    raw = [p for p in heatmap.foot_points(boxes_per_frame) if p is not None]
    if raw:
        xs = [p[0] for p in raw]
        ys = [p[1] for p in raw]
        travel = sum(((raw[i + 1][0] - raw[i][0]) ** 2 +
                      (raw[i + 1][1] - raw[i][1]) ** 2) ** 0.5
                     for i in range(len(raw) - 1))
        diag = (h ** 2 + w ** 2) ** 0.5
        min_step = diag * heatmap.DEFAULT_MIN_STEP_FRAC
        print(f"\n  [진단] 발끝 이동 범위  x: {max(xs)-min(xs):.0f}px  "
              f"y: {max(ys)-min(ys):.0f}px  (프레임 대각선 {diag:.0f}px)")
        print(f"         누적 이동거리   {travel:.0f}px, "
              f"재샘플링 문턱 {min_step:.0f}px")
        if max(max(xs) - min(xs), max(ys) - min(ys)) < min_step:
            print("         → 발끝이 문턱보다 좁은 범위에만 있었습니다. "
                  "영상 자체에 이동이 없는 게 맞습니다.")
        else:
            print("         → 이동 범위는 문턱보다 넓습니다. 동선 점이 적다면 "
                  "재샘플링/스무딩을 확인해야 합니다.")
    if rate < 0.5:
        print("  ⚠️  검출률이 낮습니다. DAON_YOLO_CONF 를 낮추거나 "
              "DAON_YOLO_IMGSZ 를 키워보세요.")
    if sum(len(s) for s in segments) < 5:
        print("  ⚠️  동선 점이 너무 적습니다. 사람이 실제로 거의 안 움직였거나,")
        print("      샘플링(DAON_ANALYZE_FPS)이 낮아 이동이 뭉개졌습니다.")

    print(f"\n  요약: {report['summary']}")
    for f in report["findings"]:
        print(f"    {f['zone']:14} cell={f['cell']} score={f['score']:.2f} [{f['level']}]")

    if args.out:
        os.makedirs(args.out, exist_ok=True)
        png = os.path.join(args.out, "report_new.png")
        heatmap.render_hazard_boxes(first, report["findings"][:1], 3, 3, png,
                                    segments=segments)
        with open(os.path.join(args.out, "report_new.json"), "w",
                  encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"  저장: {png}")

    if args.old:
        print("\n[최적화 전] 측정 중… 몇 분 걸릴 수 있습니다")
        old_t, hm, old_first = run_old(args.video)
        old_report = rules.analyze_report(hm)
        print(f"[최적화 전] {old_t:.2f}초  ({n}프레임, {old_t/max(n,1)*1000:.0f}ms/프레임)")
        print(f"  요약: {old_report['summary']}")
        for f in old_report["findings"]:
            print(f"    {f['zone']:14} cell={f['cell']} score={f['score']:.2f} [{f['level']}]")
        print(f"\n>>> 배속: {old_t / max(new_t, 1e-9):.1f}x 빨라짐 "
              f"({old_t:.1f}초 → {new_t:.1f}초, 모델 로딩 제외)")
        if args.out:
            png = os.path.join(args.out, "report_old.png")
            heatmap.render_hazard_boxes(old_first, old_report["findings"][:1],
                                        3, 3, png)
            print(f"  저장: {png}")
        print("\n두 리포트가 짚는 구역이 다르면 정상입니다 — 최적화 전은 '오래 머문 곳',")
        print("후는 '자주 지나는 동선'을 보므로 판정 기준 자체가 다릅니다.")

    if new_t > 5:
        print("\n⚠️  체감 대기가 5초를 넘었습니다. 조합을 훑어보세요:")
        print(f"    python3 scripts/bench_consulting.py {args.video} --sweep")


if __name__ == "__main__":
    main()
