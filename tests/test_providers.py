from unittest.mock import Mock

import pytest
import requests
from PySide6.QtCore import QBuffer, QByteArray, QIODevice
from PySide6.QtGui import QImage

from album_journal.providers import (
    ImportError,
    YouTubeMusicProvider,
    download_cover,
    parse_album_link,
)


@pytest.fixture
def metadata():
    return {
        "title": "Test album",
        "artists": [{"name": "Artist"}],
        "tracks": [
            {"title": "First", "artists": [{"name": "Artist"}], "duration_seconds": 123},
            {"title": "Second", "duration_seconds": None},
        ],
        "thumbnails": [
            {"url": "https://example.com/small.jpg", "width": 100, "height": 100},
            {"url": "https://example.com/big.jpg", "width": 600, "height": 600},
        ],
    }


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://music.youtube.com/browse/MPREb_test?si=x", ("browse", "MPREb_test")),
        ("https://music.youtube.com/playlist?list=OLAK5uy_test&si=x", ("playlist", "OLAK5uy_test")),
        ("https://www.youtube.com/watch?v=abc&list=OLAK5uy_test", ("playlist", "OLAK5uy_test")),
    ],
)
def test_parse_supported_links(url, expected):
    assert parse_album_link(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "https://music.youtube.com/playlist?list=PL_personal",
        "https://music.youtube.com/watch?v=song",
        "https://music.youtube.com/browse/UCartist",
        "https://evil.test/browse/MPREb_test",
        "http://music.youtube.com/browse/MPREb_test",
        "https://music.youtube.com.evil.test/browse/MPREb_test",
        "https://user@music.youtube.com/browse/MPREb_test",
    ],
)
def test_rejects_non_album_links(url):
    with pytest.raises(ImportError):
        parse_album_link(url)


def test_album_playlist_resolution_and_largest_cover(metadata, monkeypatch):
    client = Mock()
    client.get_album_browse_id.return_value = "MPREb_test"
    client.get_album.return_value = metadata
    download = Mock(return_value=b"art")
    monkeypatch.setattr("album_journal.providers.download_cover", download)
    session = Mock()
    result = YouTubeMusicProvider(client, session).fetch(
        "https://music.youtube.com/playlist?list=OLAK5uy_test"
    )
    client.get_album_browse_id.assert_called_once_with("OLAK5uy_test")
    client.get_album.assert_called_once_with("MPREb_test")
    download.assert_called_once_with("https://example.com/big.jpg", session)
    assert [t.title for t in result.album.tracks] == ["First", "Second"]
    assert result.cover == b"art"
    assert result.album.provider_id == "MPREb_test"


def test_failed_cover_does_not_discard_metadata(metadata, monkeypatch):
    client = Mock()
    client.get_album.return_value = metadata
    monkeypatch.setattr(
        "album_journal.providers.download_cover", Mock(side_effect=requests.Timeout())
    )
    result = YouTubeMusicProvider(client, Mock()).fetch(
        "https://music.youtube.com/browse/MPREb_test"
    )
    assert result.album.title == "Test album"
    assert result.cover is None
    assert "failed" in result.cover_error


def test_network_error_and_unavailable_album():
    client = Mock()
    client.get_album.side_effect = requests.ConnectionError()
    with pytest.raises(ImportError, match="connection"):
        YouTubeMusicProvider(client, Mock()).fetch("https://music.youtube.com/browse/MPREb_test")
    client.get_album.side_effect = None
    client.get_album.return_value = {"title": "Unavailable", "tracks": []}
    with pytest.raises(ImportError, match="unavailable"):
        YouTubeMusicProvider(client, Mock()).fetch("https://music.youtube.com/browse/MPREb_test")


def test_missing_cover_and_unresolved_playlist(metadata):
    client = Mock()
    client.get_album_browse_id.return_value = None
    with pytest.raises(ImportError, match="resolved"):
        YouTubeMusicProvider(client, Mock()).fetch(
            "https://music.youtube.com/playlist?list=OLAK5uy_test"
        )
    client.get_album.return_value = {**metadata, "thumbnails": []}
    result = YouTubeMusicProvider(client, Mock()).fetch(
        "https://music.youtube.com/browse/MPREb_test"
    )
    assert result.cover is None
    assert result.album.tracks


def image_bytes():
    image = QImage(10, 10, QImage.Format.Format_RGB32)
    image.fill(0xFF556677)
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(data)


def mock_session(data):
    response = Mock()
    response.iter_content.return_value = [data]
    context = Mock()
    context.__enter__ = Mock(return_value=response)
    context.__exit__ = Mock(return_value=False)
    session = Mock()
    session.get.return_value = context
    return session


def test_cover_is_decoded_and_encoded_as_jpeg():
    result = download_cover("https://example.com/cover", mock_session(image_bytes()))
    assert result[:2] == b"\xff\xd8"
    assert not QImage.fromData(result).isNull()


@pytest.mark.parametrize("data", [b"not an image", b"x" * (15 * 1024 * 1024 + 1)])
def test_rejects_corrupt_and_oversized_covers(data):
    with pytest.raises(ImportError):
        download_cover("https://example.com/cover", mock_session(data))
