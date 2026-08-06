"""업로드 스트리밍·크기 제한 테스트.

영상은 수백 MB가 예사다. 통째로 메모리에 올리면 배포 인스턴스가 죽고, 한도
초과를 끝까지 받은 뒤에 거부하면 사용자는 한참 기다렸다 실패를 본다.
"""

import os

import pytest

from webservice import routes_consulting as rc


class FakeUpload:
    """UploadFile 의 read(size) 인터페이스만 흉내낸다."""

    def __init__(self, data, chunk_reads=None):
        self._data = data
        self._pos = 0
        self.reads = 0
        self.chunk_reads = chunk_reads

    async def read(self, size=-1):
        self.reads += 1
        if size is None or size < 0:
            block = self._data[self._pos:]
            self._pos = len(self._data)
            return block
        block = self._data[self._pos:self._pos + size]
        self._pos += len(block)
        return block


@pytest.mark.anyio
async def test_saves_file_contents(tmp_path):
    dest = os.path.join(tmp_path, "v.mp4")
    up = FakeUpload(b"abcdef" * 1000)
    n = await rc._save_upload(up, dest, max_bytes=10 ** 6, chunk=256)
    assert n == 6000
    with open(dest, "rb") as f:
        assert f.read() == b"abcdef" * 1000


@pytest.mark.anyio
async def test_reads_in_chunks_not_all_at_once(tmp_path):
    """메모리를 지키려면 여러 번 나눠 읽어야 한다."""
    dest = os.path.join(tmp_path, "v.mp4")
    up = FakeUpload(b"x" * 10000)
    await rc._save_upload(up, dest, max_bytes=10 ** 6, chunk=1000)
    assert up.reads > 5, "한 번에 다 읽었다 — 스트리밍이 아니다"


@pytest.mark.anyio
async def test_oversize_rejected_before_reading_everything(tmp_path):
    """한도를 넘는 순간 끊어야지, 끝까지 받고 거부하면 의미가 없다."""
    from fastapi import HTTPException
    dest = os.path.join(tmp_path, "big.mp4")
    up = FakeUpload(b"x" * 100_000)

    with pytest.raises(HTTPException) as exc:
        await rc._save_upload(up, dest, max_bytes=5000, chunk=1000)
    assert exc.value.status_code == 413
    assert up.reads < 20, "한도를 넘긴 뒤에도 계속 읽었다"


@pytest.mark.anyio
async def test_oversize_leaves_no_partial_file(tmp_path):
    from fastapi import HTTPException
    dest = os.path.join(tmp_path, "big.mp4")
    with pytest.raises(HTTPException):
        await rc._save_upload(FakeUpload(b"x" * 100_000), dest,
                              max_bytes=5000, chunk=1000)
    assert not os.path.exists(dest), "거부한 업로드의 잘린 파일이 남았다"


@pytest.mark.anyio
async def test_empty_upload_rejected(tmp_path):
    from fastapi import HTTPException
    dest = os.path.join(tmp_path, "empty.mp4")
    with pytest.raises(HTTPException) as exc:
        await rc._save_upload(FakeUpload(b""), dest, max_bytes=5000)
    assert exc.value.status_code == 400
    assert not os.path.exists(dest)


@pytest.mark.anyio
async def test_error_message_mentions_the_limit(tmp_path):
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        await rc._save_upload(FakeUpload(b"x" * 10 ** 7),
                              os.path.join(tmp_path, "b.mp4"),
                              max_bytes=3 * 1024 * 1024, chunk=1024 * 1024)
    assert "3MB" in exc.value.detail


@pytest.fixture
def anyio_backend():
    return "asyncio"
