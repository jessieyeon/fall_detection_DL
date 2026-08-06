"""샘플 결과 캐시 테스트.

캐시가 잘못 걸리면 엉뚱한 리포트를 보여주게 되므로, 특히 '적중하면 안 될 때
적중하지 않는지'를 확인한다.
"""

import json
import os

from webservice.consulting import cache


def _write(path, data=b"video-bytes"):
    with open(path, "wb") as f:
        f.write(data)
    return path


def test_hash_is_content_based_not_name(tmp_path):
    """관람객이 파일명을 바꿔 올려도 같은 영상이면 캐시가 걸려야 한다."""
    a = _write(os.path.join(tmp_path, "a.mp4"))
    b = _write(os.path.join(tmp_path, "완전히-다른-이름.mov"))
    assert cache.file_sha256(a) == cache.file_sha256(b)


def test_different_content_different_hash(tmp_path):
    a = _write(os.path.join(tmp_path, "a.mp4"), b"one")
    b = _write(os.path.join(tmp_path, "b.mp4"), b"two")
    assert cache.file_sha256(a) != cache.file_sha256(b)


def test_missing_manifest_is_not_an_error(tmp_path):
    """매니페스트가 없어도(샘플 준비 전) 서비스는 살아 있어야 한다."""
    assert cache.load_manifest(os.path.join(tmp_path, "nope.json")) == {}


def test_corrupt_manifest_falls_back_to_empty(tmp_path):
    """깨진 매니페스트 때문에 분석 전체가 죽으면 안 된다."""
    p = os.path.join(tmp_path, "manifest.json")
    with open(p, "w") as f:
        f.write("{ this is not json")
    assert cache.load_manifest(p) == {}


def test_lookup_hit_returns_entry(tmp_path, monkeypatch):
    video = _write(os.path.join(tmp_path, "sample.mp4"))
    image = os.path.join(tmp_path, "sample.png")
    _write(image, b"png-bytes")
    monkeypatch.setattr(cache, "SAMPLE_DIR", str(tmp_path))

    manifest = {cache.file_sha256(video): {
        "location": "안방", "findings": {"summary": "s"}, "image": "sample.png",
    }}
    hit = cache.lookup(video, manifest=manifest)
    assert hit is not None
    assert hit["location"] == "안방"
    assert hit["image"] == image


def test_lookup_miss_returns_none(tmp_path):
    video = _write(os.path.join(tmp_path, "unknown.mp4"), b"never-seen")
    assert cache.lookup(video, manifest={"deadbeef": {"image": "x.png"}}) is None


def test_lookup_ignores_entry_whose_image_is_gone(tmp_path, monkeypatch):
    """이미지가 사라진 캐시를 쓰면 리포트가 깨진 그림으로 뜬다 — 실제 분석으로 넘긴다."""
    video = _write(os.path.join(tmp_path, "sample.mp4"))
    monkeypatch.setattr(cache, "SAMPLE_DIR", str(tmp_path))
    manifest = {cache.file_sha256(video): {
        "location": "거실", "findings": {}, "image": "does-not-exist.png",
    }}
    assert cache.lookup(video, manifest=manifest) is None


def test_save_and_load_roundtrip(tmp_path):
    p = os.path.join(tmp_path, "sub", "manifest.json")
    entries = {"abc": {"location": "부엌", "findings": {"summary": "요약"}, "image": "k.png"}}
    cache.save_manifest(entries, p)

    with open(p, encoding="utf-8") as f:
        raw = f.read()
    assert "부엌" in raw          # 한글이 이스케이프되지 않고 저장돼 사람이 읽을 수 있다
    assert json.loads(raw) == entries
    assert cache.load_manifest(p) == entries
