import json
import shutil
from dataclasses import replace
from uuid import uuid4

import pytest

from album_journal.storage import Album, Library, LibraryError


def test_portable_folder_roundtrip(library, album, tmp_path):
    edited = replace(album, added_on="2021-07-04", rating=4.5, notes="日本語\nNotes 🎵")
    saved = library.save_cover(edited, b"cover-fixture")
    root = library.root
    library.close()
    shutil.copytree(root, tmp_path / "moved")
    moved = Library(tmp_path / "moved")
    try:
        loaded = moved.albums[album.id]
        assert loaded == saved
        assert moved.cover_file(loaded).read_bytes() == b"cover-fixture"
        assert not loaded.cover_path.startswith("/")
        assert moved.search("BJÖRK", "2021") == [loaded]
        assert moved.search("example björk", "2021") == [loaded]
        assert moved.search("example", "2022") == []
    finally:
        moved.close()


def test_duplicate_never_overwrites_original(library, album):
    library.save(replace(album, notes="Keep me", rating=3))
    with pytest.raises(LibraryError, match="already"):
        library.save(replace(album, id=str(uuid4()), notes="Overwrite"))
    library.reload()
    assert library.find(album.provider, album.provider_id).notes == "Keep me"


def test_damaged_record_does_not_prevent_loading(library, album):
    library.save(album)
    damaged = library.root / "albums" / "damaged.json"
    damaged.write_text("{", encoding="utf-8")
    library.reload()
    assert list(library.albums) == [album.id]
    assert len(library.warnings) == 1
    assert damaged.read_text() == "{"


def test_interrupted_atomic_save_preserves_original(library, album, monkeypatch):
    library.save(album)
    original = (library.root / "albums" / f"{album.id}.json").read_bytes()

    def fail_replace(*args):
        raise OSError("simulated disk error")

    monkeypatch.setattr("album_journal.storage.os.replace", fail_replace)
    with pytest.raises(LibraryError, match="disk error"):
        library.save(replace(album, notes="must not replace original"))
    assert (library.root / "albums" / f"{album.id}.json").read_bytes() == original
    assert not list((library.root / "albums").glob("*.tmp"))
    assert library.albums[album.id].notes == ""


def test_failed_cover_update_keeps_previous_cover(library, album, monkeypatch):
    saved = library.save_cover(album, b"old-cover")

    def fail_save(*args):
        raise LibraryError("simulated metadata error")

    monkeypatch.setattr(library, "save", fail_save)
    with pytest.raises(LibraryError):
        library.save_cover(saved, b"new-cover")
    assert library.cover_file(saved).read_bytes() == b"old-cover"
    assert len(list((library.root / "covers").iterdir())) == 1


@pytest.mark.parametrize("rating", [0, 5.5, 3.2, True, "4", float("nan")])
def test_rejects_invalid_rating(album, rating):
    data = replace(album, rating=rating).to_dict()
    with pytest.raises(ValueError):
        Album.from_dict(data)


@pytest.mark.parametrize(
    "path", ["../cover.jpg", "/tmp/cover.jpg", "covers/../../bad", "covers\\bad.jpg"]
)
def test_rejects_nonportable_cover_paths(album, path):
    with pytest.raises(ValueError):
        Album.from_dict(replace(album, cover_path=path).to_dict())


def test_rating_can_be_cleared_and_album_removed(library, album):
    saved = library.save_cover(replace(album, rating=4), b"art")
    library.save(replace(saved, rating=None))
    library.reload()
    assert library.albums[album.id].rating is None
    library.remove(library.albums[album.id])
    assert not library.albums
    assert not list((library.root / "covers").iterdir())
    assert not list((library.root / "albums").iterdir())


def test_library_lock_and_reopening(library):
    with pytest.raises(LibraryError, match="already open"):
        Library(library.root)
    library.close()
    reopened = Library(library.root)
    reopened.close()


def test_does_not_initialize_unrelated_folder(tmp_path):
    (tmp_path / "important.txt").write_text("keep me")
    with pytest.raises(LibraryError, match="empty folder"):
        Library(tmp_path)
    assert not (tmp_path / "library.json").exists()
    assert (tmp_path / "important.txt").read_text() == "keep me"


def test_unsupported_manifest_is_preserved(tmp_path):
    manifest = tmp_path / "library.json"
    manifest.write_text(json.dumps({"schema_version": 99}))
    with pytest.raises(LibraryError, match="unsupported"):
        Library(tmp_path)
    assert json.loads(manifest.read_text())["schema_version"] == 99


def test_sort_by_added_date(library, album):
    newer = replace(album, added_on="2025-01-01")
    older = replace(album, id=str(uuid4()), provider_id="MPREb_older", added_on="2020-12-31")
    library.save(older)
    library.save(newer)
    assert library.search() == [newer, older]
