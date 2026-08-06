#!/usr/bin/env python3
"""체험용 샘플 영상을 미리 분석해 캐시를 만든다.

    python3 scripts/build_samples.py 안방=samples/bedroom.mp4 \
                                     거실=samples/living.mp4 \
                                     부엌=samples/kitchen.mp4

또는 프런트 public 폴더의 표준 위치에서 자동으로 찾기:

    python3 scripts/build_samples.py --auto

하는 일
  1. 각 영상을 실제 파이프라인으로 분석한다 (실전과 같은 결과가 나오도록)
  2. 리포트 JSON 과 경로 이미지를 webservice/consulting/samples/ 에 저장
  3. 영상 SHA-256 → 결과 매니페스트를 쓴다

이후 서버는 같은 영상이 업로드되면 분석 없이 즉시 응답한다.
영상을 다시 만들면 해시가 바뀌므로 이 스크립트를 다시 돌려야 한다.
"""

import argparse
import json
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from webservice.consulting import cache, heatmap, rules  # noqa: E402

# 프런트가 참조하는 표준 위치 (Consulting.tsx 의 SAMPLES 와 맞춘다)
PUBLIC_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "webservice", "frontend", "public", "samples")
AUTO = [("안방", "bedroom.mp4"), ("거실", "living.mp4"), ("부엌", "kitchen.mp4")]


def analyze_one(label, video_path):
    from webservice.consulting.analyze import analyze_video
    from webservice.consulting.transcode import ensure_readable

    path, converted = ensure_readable(video_path)
    try:
        t0 = time.perf_counter()
        pmap, first, segments = analyze_video(path)
        elapsed = time.perf_counter() - t0
    finally:
        if converted and os.path.isfile(path):
            os.remove(path)

    report = rules.analyze_report(pmap)
    stem = os.path.splitext(os.path.basename(video_path))[0]
    image_name = f"{stem}.png"
    image_path = os.path.join(cache.SAMPLE_DIR, image_name)
    os.makedirs(cache.SAMPLE_DIR, exist_ok=True)
    heatmap.render_hazard_boxes(first, report["findings"][:1], 3, 3, image_path,
                                segments=segments)

    points = sum(len(s) for s in segments)
    turns = sum(1 for s in segments
                for a in heatmap.heading_changes(s)
                if a >= heatmap.TURN_ANGLE_THRESHOLD_DEG)
    print(f"  분석 {elapsed:.1f}초 · 동선 {points}점 · 회전 {turns}곳")
    print(f"  {report['summary']}")
    if points < 8:
        print("  ⚠️  동선 점이 적습니다. 카메라가 움직였거나 이동이 거의 없는 영상일 수 있습니다.")

    return {
        "location": label,
        "findings": report,
        "image": image_name,     # 매니페스트에는 상대 경로로 둔다
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pairs", nargs="*", metavar="라벨=경로",
                    help="예: 안방=samples/bedroom.mp4")
    ap.add_argument("--auto", action="store_true",
                    help=f"{PUBLIC_DIR} 에서 표준 파일명을 찾는다")
    ap.add_argument("--clean", action="store_true", help="기존 캐시를 지우고 다시 만든다")
    args = ap.parse_args()

    items = []
    if args.auto:
        for label, name in AUTO:
            p = os.path.join(PUBLIC_DIR, name)
            if os.path.isfile(p):
                items.append((label, p))
            else:
                print(f"건너뜀 — 파일 없음: {p}")
    for pair in args.pairs:
        if "=" not in pair:
            sys.exit(f"'라벨=경로' 형식이어야 합니다: {pair}")
        label, path = pair.split("=", 1)
        if not os.path.isfile(path):
            sys.exit(f"파일이 없습니다: {path}")
        items.append((label, path))

    if not items:
        sys.exit("분석할 영상이 없습니다. --auto 를 쓰거나 라벨=경로 를 넘기세요.")

    if args.clean and os.path.isdir(cache.SAMPLE_DIR):
        shutil.rmtree(cache.SAMPLE_DIR)

    manifest = {} if args.clean else cache.load_manifest()
    print(f"샘플 {len(items)}개를 분석합니다. (모델 로딩에 몇 초 걸립니다)\n")

    for label, path in items:
        print(f"[{label}] {path}")
        digest = cache.file_sha256(path)
        manifest[digest] = analyze_one(label, path)
        print(f"  sha256 {digest[:16]}…\n")

    out = cache.save_manifest(manifest)
    print(f"매니페스트: {out}")
    print(f"등록된 샘플: {len(manifest)}개")
    print("\n이제 같은 영상을 업로드하면 분석 없이 즉시 결과가 나옵니다.")
    print("영상을 다시 만들면 해시가 바뀌므로 이 스크립트를 다시 실행하세요.")


if __name__ == "__main__":
    main()
