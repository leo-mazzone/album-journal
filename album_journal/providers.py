"""Service adapter: fetching never writes to the library."""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from datetime import date
from typing import Protocol
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import requests
from PySide6.QtCore import QBuffer, QByteArray, QIODevice
from PySide6.QtGui import QImage

from .storage import Album, Track


class ImportError(Exception):
    pass


@dataclass
class ImportResult:
    album: Album
    cover: bytes | None
    cover_error: str | None = None


class AlbumProvider(Protocol):
    def fetch(self, url: str) -> ImportResult: ...


class TimedSession(requests.Session):
    def request(self, method, url, **kwargs):
        kwargs.setdefault("timeout", (8, 25))
        return super().request(method, url, **kwargs)


def parse_album_link(url: str) -> tuple[str, str]:
    parsed = urlparse(url.strip())
    if (
        parsed.scheme != "https"
        or parsed.hostname
        not in {
            "music.youtube.com",
            "youtube.com",
            "www.youtube.com",
        }
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
    ):
        raise ImportError("Paste a full https://music.youtube.com/ album link.")
    path = parsed.path.rstrip("/")
    if path.startswith("/browse/"):
        album_id = path.removeprefix("/browse/")
        if re.fullmatch(r"MPRE[A-Za-z0-9_-]+", album_id):
            return "browse", album_id
    if path in {"/playlist", "/watch"}:
        playlist_id = parse_qs(parsed.query).get("list", [""])[0]
        if re.fullmatch(r"OLAK5uy_[A-Za-z0-9_-]+", playlist_id):
            return "playlist", playlist_id
    raise ImportError("Use an album link, rather than a song, artist, or personal playlist link.")


def download_cover(url: str, session: requests.Session) -> bytes:
    """Bound the download and decode it before returning a consistently encoded JPEG."""
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ImportError("The service returned an invalid cover URL.")
    with session.get(url, stream=True, timeout=(8, 25)) as response:
        response.raise_for_status()
        data = io.BytesIO()
        for chunk in response.iter_content(65536):
            data.write(chunk)
            if data.tell() > 15 * 1024 * 1024:
                raise ImportError("The cover image is too large.")
    image = QImage.fromData(data.getvalue())
    if image.isNull():
        raise ImportError("The cover could not be decoded as an image.")
    encoded = QByteArray()
    buffer = QBuffer(encoded)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(buffer, "JPEG", 95):
        raise ImportError("The cover could not be saved as an image.")
    return bytes(encoded)


class YouTubeMusicProvider:
    def __init__(self, client=None, session=None):
        self.client = client
        self.session = session

    def fetch(self, url: str) -> ImportResult:
        kind, identifier = parse_album_link(url)
        session = self.session or TimedSession()
        try:
            if self.client is None:
                from ytmusicapi import YTMusic

                client = YTMusic(requests_session=session)
            else:
                client = self.client
            browse_id = identifier if kind == "browse" else client.get_album_browse_id(identifier)
            if not browse_id:
                raise ImportError("This link could not be resolved to a public album.")
            metadata = client.get_album(browse_id)
            title = metadata.get("title")
            source_tracks = metadata.get("tracks")
            if not title or not isinstance(source_tracks, list) or not source_tracks:
                raise ImportError(
                    "The album is unavailable or its tracklist could not be retrieved."
                )
            tracks = []
            for raw in source_tracks:
                duration = raw.get("duration_seconds")
                tracks.append(
                    Track(
                        title=raw.get("title") or "Unavailable track",
                        artists=[a["name"] for a in raw.get("artists", []) if a.get("name")],
                        duration_seconds=duration
                        if isinstance(duration, int) and duration >= 0
                        else None,
                    )
                )
            album = Album(
                id=str(uuid4()),
                provider="youtube_music",
                provider_id=browse_id,
                source_url=f"https://music.youtube.com/browse/{browse_id}",
                title=title,
                artists=[a["name"] for a in metadata.get("artists", []) if a.get("name")],
                tracks=tracks,
                added_on=date.today().isoformat(),
            )
            thumbnails = metadata.get("thumbnails") or []
            if not thumbnails:
                return ImportResult(album, None, "No cover was returned. You can retry later.")
            largest = max(thumbnails, key=lambda t: (t.get("width") or 0) * (t.get("height") or 0))
            try:
                return ImportResult(album, download_cover(largest["url"], session))
            except (requests.RequestException, ImportError, KeyError) as exc:
                return ImportResult(album, None, f"Cover download failed: {exc}")
        except ImportError:
            raise
        except requests.RequestException as exc:
            raise ImportError(
                "Could not reach YouTube Music. Check your connection and retry."
            ) from exc
        except Exception as exc:
            raise ImportError(
                "YouTube Music could not return this album. Retry, or check for an app update."
            ) from exc
        finally:
            if self.session is None:
                session.close()
