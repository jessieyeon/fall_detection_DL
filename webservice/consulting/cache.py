"""사전 계산된 샘플 리포트 캐시.

온라인 전시에서 관람객이 올리는 영상은 대부분 우리가 준비한 체험용 샘플 3개다.
결과를 미리 계산해두고 해시로 맞춰 즉시 돌려주면 두 가지가 해결된다.

  · 대기 시간이 0이 된다 (분석 3~5초도 체험에서는 길다)
  · 서버가 YOLO 를 돌리지 않으므로 동시 접속이 몰려도 버틴다

**분석 파이프라인은 그대로 둔다.** 이건 앞단에 얹은 캐시 한 겹일 뿐이고,
처음 보는 파일은 지금까지처럼 실제 분석을 탄다. 부스에서 관람객이 찍어온
영상을 분석해주는 것도 그대로 된다.

매니페스트는 `scripts/build_samples.py` 가 만든다.
"""

import hashlib
import json
import os

_BASE = os.path.dirname(os.path.abspath(__file__))
SAMPLE_DIR = os.path.join(_BASE, "samples")
MANIFEST_PATH = os.path.join(SAMPLE_DIR, "manifest.json")


def file_sha256(path, chunk=1024 * 1024):
    """파일 내용 해시. 파일명이 아니라 내용으로 맞춘다 — 관람객이 이름을 바꿔
    올려도 같은 영상이면 캐시가 걸려야 한다."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def load_manifest(path=None):
    """{sha256: {"location", "findings", "image"}} 형태. 없으면 빈 dict."""
    p = path or MANIFEST_PATH
    if not os.path.isfile(p):
        return {}
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        # 매니페스트가 깨져도 서비스는 살아 있어야 한다 — 실제 분석으로 넘어간다.
        return {}
    return data if isinstance(data, dict) else {}


def lookup(video_path, manifest=None):
    """이 영상의 사전 계산 결과. 없으면 None.

    반환값의 image 는 절대 경로로 바꿔서 준다(매니페스트에는 상대 경로로 저장).
    """
    man = load_manifest() if manifest is None else manifest
    if not man:
        return None
    entry = man.get(file_sha256(video_path))
    if not entry:
        return None

    image = entry.get("image")
    if image and not os.path.isabs(image):
        image = os.path.join(SAMPLE_DIR, image)
    if not image or not os.path.isfile(image):
        # 이미지가 없으면 리포트를 열었을 때 깨진다. 캐시를 포기하고 실제 분석.
        return None
    return {
        "location": entry.get("location", ""),
        "findings": entry.get("findings"),
        "image": image,
    }


def save_manifest(entries, path=None):
    p = path or MANIFEST_PATH
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)
    return p
