import pytest
from django.http import Http404

from core.media import serve_media


@pytest.fixture
def clip(settings, tmp_path, rf):
    settings.MEDIA_ROOT = tmp_path
    (tmp_path / "audio").mkdir()
    (tmp_path / "audio" / "clip.m4a").write_bytes(bytes(range(10)))

    def get(range_header=None, path="audio/clip.m4a"):
        headers = {"Range": range_header} if range_header else {}
        return serve_media(rf.get("/media/" + path, headers=headers), path)

    return get


def test_range_request_gets_partial_content(clip):
    response = clip("bytes=0-1")

    assert response.status_code == 206
    assert response.content == bytes([0, 1])
    assert response["Content-Range"] == "bytes 0-1/10"
    assert response["Content-Type"] == "audio/mp4"


@pytest.mark.parametrize(
    "header, content",
    [
        ("bytes=8-", bytes([8, 9])),
        ("bytes=-3", bytes([7, 8, 9])),
        ("bytes=8-99", bytes([8, 9])),
    ],
)
def test_open_ended_and_suffix_ranges(clip, header, content):
    assert clip(header).content == content


def test_unsatisfiable_range(clip):
    assert clip("bytes=20-").status_code == 416


def test_without_range_serves_the_whole_file(clip):
    response = clip()

    assert response.status_code == 200
    assert b"".join(response.streaming_content) == bytes(range(10))
    assert response["Accept-Ranges"] == "bytes"


def test_paths_outside_media_are_refused(clip):
    with pytest.raises(Http404):
        clip("bytes=0-1", path="../secret.txt")
