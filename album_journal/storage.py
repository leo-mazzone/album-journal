"""Versioned JSON storage. No network access or platform-specific paths in records."""

from __future__ import annotations

import json
import math
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path, PurePosixPath
from uuid import UUID, uuid4

from filelock import FileLock, Timeout


class LibraryError(Exception):
    pass


@dataclass
class Track:
    title: str
    artists: list[str] = field(default_factory=list)
    duration_seconds: int | None = None


@dataclass
class Album:
    id: str
    provider: str
    provider_id: str
    source_url: str
    title: str
    artists: list[str]
    tracks: list[Track]
    added_on: str
    rating: float | None = None
    notes: str = ""
    cover_path: str | None = None

    @classmethod
    def from_dict(cls, data: dict) -> Album:
        if not isinstance(data, dict):
            raise ValueError("Album record must be an object")
        if data.get("schema_version") != 1:
            raise ValueError("Unsupported album schema version")
        values = {key: data[key] for key in cls.__dataclass_fields__}
        if str(UUID(values["id"])) != values["id"]:
            raise ValueError("Invalid album ID")
        for key in ("provider", "provider_id", "source_url", "title", "added_on", "notes"):
            if not isinstance(values[key], str):
                raise ValueError(f"Invalid {key}")
        if not values["title"].strip() or not values["provider_id"]:
            raise ValueError("Missing album title or provider ID")
        if date.fromisoformat(values["added_on"]).isoformat() != values["added_on"]:
            raise ValueError("Invalid date added")
        if not _strings(values["artists"]):
            raise ValueError("Invalid artists")
        rating = values["rating"]
        if rating is not None and (
            isinstance(rating, bool)
            or not isinstance(rating, (float, int))
            or not math.isfinite(rating)
            or not 0.5 <= rating <= 5
            or rating * 2 != int(rating * 2)
        ):
            raise ValueError("Rating must be a half-star value between 0.5 and 5")
        cover = values["cover_path"]
        if cover is not None:
            if not isinstance(cover, str) or "\\" in cover:
                raise ValueError("Invalid cover path")
            path = PurePosixPath(cover)
            if path.is_absolute() or len(path.parts) != 2 or path.parts[0] != "covers":
                raise ValueError("Cover path must be relative to covers/")
            if path.parts[1] in (".", ".."):
                raise ValueError("Invalid cover filename")
        if not isinstance(values["tracks"], list):
            raise ValueError("Invalid tracklist")
        tracks = []
        for track in values["tracks"]:
            if not isinstance(track, dict) or not isinstance(track.get("title"), str):
                raise ValueError("Invalid track title")
            if not _strings(track.get("artists")):
                raise ValueError("Invalid track artists")
            duration = track.get("duration_seconds")
            if duration is not None and (
                isinstance(duration, bool) or not isinstance(duration, int) or duration < 0
            ):
                raise ValueError("Invalid track duration")
            tracks.append(Track(track["title"], track["artists"], duration))
        values["tracks"] = tracks
        return cls(**values)

    def to_dict(self) -> dict:
        return {"schema_version": 1, **asdict(self)}


def _strings(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def atomic_write(path: Path, data: bytes) -> None:
    """Flush a sibling temporary file before replacing the destination atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


class Library:
    def __init__(self, root: Path):
        self.root = root.expanduser().resolve()
        self.albums: dict[str, Album] = {}
        self.warnings: list[str] = []
        self._lock: FileLock | None = None
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            lock = FileLock(str(self.root / ".album-journal.lock"))
            lock.acquire(timeout=0)
            self._lock = lock
            manifest = self.root / "library.json"
            if manifest.exists():
                data = json.loads(manifest.read_text(encoding="utf-8"))
                if not isinstance(data, dict) or data.get("schema_version") != 1:
                    raise LibraryError("This library uses an unsupported format.")
            else:
                existing = [p for p in self.root.iterdir() if p.name != ".album-journal.lock"]
                if existing:
                    raise LibraryError(
                        "Choose an empty folder or an existing Album Journal library."
                    )
                atomic_write(manifest, b'{"schema_version": 1, "name": "Album Journal"}\n')
            (self.root / "albums").mkdir(exist_ok=True)
            (self.root / "covers").mkdir(exist_ok=True)
            self.reload()
        except Timeout as exc:
            self.close()
            raise LibraryError(
                "This library is already open in another Album Journal window."
            ) from exc
        except (OSError, ValueError, LibraryError) as exc:
            self.close()
            raise LibraryError(str(exc)) from exc

    def close(self) -> None:
        if self._lock:
            self._lock.release()
            self._lock = None

    def reload(self) -> None:
        self.albums.clear()
        self.warnings.clear()
        identities: set[tuple[str, str]] = set()
        for path in sorted((self.root / "albums").glob("*.json")):
            try:
                album = Album.from_dict(json.loads(path.read_text(encoding="utf-8")))
                if path.stem != album.id:
                    raise ValueError("Filename does not match album ID")
                identity = album.provider, album.provider_id
                if identity in identities:
                    raise ValueError("Duplicate provider ID")
                self.albums[album.id] = album
                identities.add(identity)
                if album.cover_path and not self.cover_file(album).is_file():
                    self.warnings.append(f"{album.title}: cover file is missing; use Retry Cover.")
            except (OSError, ValueError, KeyError, TypeError) as exc:
                self.warnings.append(f"{path.name}: {exc}")

    def find(self, provider: str, provider_id: str) -> Album | None:
        return next(
            (
                a
                for a in self.albums.values()
                if (a.provider, a.provider_id) == (provider, provider_id)
            ),
            None,
        )

    def cover_file(self, album: Album) -> Path:
        if not album.cover_path:
            return self.root / "covers" / "__missing__"
        path = (self.root / album.cover_path).resolve()
        covers = (self.root / "covers").resolve()
        if not covers.is_relative_to(self.root) or not path.is_relative_to(covers):
            raise LibraryError("Cover path points outside the library.")
        return path

    def save(self, album: Album) -> None:
        # Validate every write as well as every read.
        Album.from_dict(album.to_dict())
        other = self.find(album.provider, album.provider_id)
        if other and other.id != album.id:
            raise LibraryError("This album is already in your library.")
        try:
            encoded = (json.dumps(album.to_dict(), ensure_ascii=False, indent=2) + "\n").encode()
            atomic_write(self.root / "albums" / f"{album.id}.json", encoded)
            self.albums[album.id] = album
        except OSError as exc:
            raise LibraryError(f"Could not save album: {exc}") from exc

    def save_cover(self, album: Album, data: bytes) -> Album:
        from dataclasses import replace

        # A new filename ensures a failed metadata write never damages an existing cover.
        relative = f"covers/{album.id}-{uuid4().hex}.jpg"
        path = self.root / relative
        updated = replace(album, cover_path=relative)
        try:
            atomic_write(path, data)
            self.save(updated)
        except (OSError, LibraryError) as exc:
            path.unlink(missing_ok=True)
            raise LibraryError(f"Could not save cover: {exc}") from exc
        if album.cover_path and album.cover_path != relative:
            try:
                self.cover_file(album).unlink(missing_ok=True)
            except OSError:
                pass
        return updated

    def remove(self, album: Album) -> None:
        try:
            (self.root / "albums" / f"{album.id}.json").unlink()
        except OSError as exc:
            raise LibraryError(f"Could not remove album: {exc}") from exc
        self.albums.pop(album.id, None)
        if album.cover_path:
            try:
                self.cover_file(album).unlink(missing_ok=True)
            except OSError:
                pass

    def search(
        self,
        text: str = "",
        year: str | None = None,
        *,
        min_rating: float | None = None,
        max_rating: float | None = None,
    ) -> list[Album]:
        for bound in (min_rating, max_rating):
            if bound is not None and (
                isinstance(bound, bool)
                or not isinstance(bound, (int, float))
                or not math.isfinite(bound)
                or not 0.5 <= bound <= 5
                or bound * 2 != int(bound * 2)
            ):
                raise ValueError("Rating bounds must be half-star values between 0.5 and 5")
        if min_rating is not None and max_rating is not None and min_rating > max_rating:
            raise ValueError("Minimum rating cannot exceed maximum rating")
        filtering_rating = min_rating is not None or max_rating is not None
        terms = text.casefold().split()
        return sorted(
            (
                a
                for a in self.albums.values()
                if all(term in (a.title + " " + " ".join(a.artists)).casefold() for term in terms)
                and (year is None or a.added_on[:4] == year)
                and (
                    not filtering_rating
                    or (
                        a.rating is not None
                        and (min_rating is None or a.rating >= min_rating)
                        and (max_rating is None or a.rating <= max_rating)
                    )
                )
            ),
            key=lambda a: (a.added_on, a.title.casefold(), a.id),
            reverse=True,
        )
