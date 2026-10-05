"""Offline packaging smoke check; does not touch the user's library or settings."""

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QImage

from .app import AlbumDialog, MainWindow
from .storage import Album, Library, Track


def smoke_test(app, screenshot_dir: Path | None = None) -> None:
    from ytmusicapi import YTMusic

    # Constructing the real client exercises its packaged resources without networking.
    YTMusic()
    assert not app.windowIcon().isNull(), "Packaged app icon is missing"
    with TemporaryDirectory(prefix="album-journal-smoke-") as temp:
        library = Library(Path(temp) / "library")
        try:
            samples = [
                ("Quiet mornings", "The Sunday Trio", "#b6b39c"),
                ("Blue hour", "Mira", "#9daebb"),
                ("The long way home", "Good Company", "#bba38e"),
                ("Field recordings", "Northbound", "#a7b1a0"),
                ("Late summer", "June", "#d0ba96"),
                ("After the rain", "The Sunday Trio", "#a7a1b6"),
                ("Small hours", "Mira", "#a6b7b5"),
                ("Soft landing", "Good Company", "#c3aba1"),
            ]
            for i, (title, artist, color) in enumerate(samples):
                album = Album(
                    id=str(uuid4()),
                    provider="youtube_music",
                    provider_id=f"MPREb_sample_{i}",
                    source_url=f"https://music.youtube.com/browse/MPREb_sample_{i}",
                    title=title,
                    artists=[artist],
                    tracks=[Track(f"Track {n}", [artist], 170 + n * 10) for n in range(1, 7)],
                    added_on=f"2025-08-{20 - i:02}",
                    rating=4.5 if i == 0 else None,
                    notes="An album to come back to.\nA quiet afternoon, a cup of coffee.",
                )
                image = QImage(400, 400, QImage.Format.Format_RGB32)
                image.fill(color)
                cover = Path(temp) / "cover.jpg"
                assert image.save(str(cover), "JPEG")
                library.save_cover(album, cover.read_bytes())
            library.reload()
            assert len(library.albums) == 8
            assert len(library.search("sunday", "2025")) == 2
            window = MainWindow(library)
            window.show()
            app.processEvents()
            assert window.grid.count() == 8
            pixmap = window.grab()
            assert not pixmap.isNull()
            from PySide6.QtTest import QTest

            window.open_rating_filter()
            panel = window.rating_popup
            app.processEvents()
            QTest.mouseClick(panel.minimum, Qt.MouseButton.LeftButton)
            panel.minimum.selectAll()
            QTest.keyClick(panel.windowHandle(), Qt.Key.Key_3)
            QTest.keyClick(panel.windowHandle(), Qt.Key.Key_Tab)
            assert panel.slider.values == (3, 5), "Rating minimum did not receive keyboard input"
            panel.maximum.setValue(4.5)
            app.processEvents()
            rating_panel = panel.grab()
            QTest.mouseClick(panel.apply_button, Qt.MouseButton.LeftButton)
            assert window.rating_range == (3, 4.5)
            assert window.grid.count() == 1
            window.open_rating_filter()
            panel.maximum.setValue(3)
            QTest.keyClick(panel.windowHandle(), Qt.Key.Key_Escape)
            assert not panel.isVisible(), "Escape did not dismiss the rating panel"
            assert window.rating_range == (3, 4.5), "Dismissal committed a draft filter"
            window.open_rating_filter()
            QTest.mouseClick(panel.clear_button, Qt.MouseButton.LeftButton)
            assert window.rating_range is None and window.grid.count() == 8
            window.resize(450, 400)
            app.processEvents()
            window.open_rating_filter()
            assert window.width() == 450, "Filters forced the window beyond its minimum width"
            assert panel.screen().availableGeometry().contains(panel.frameGeometry())
            panel.hide()
            window.resize(940, 760)
            first = library.search()[0]
            dialog = AlbumDialog(library, first, window.provider, window)
            dialog.show()
            dialog.activateWindow()
            app.processEvents()
            assert QTest.qWaitForWindowActive(dialog, 3000), (
                "Album window did not gain keyboard focus"
            )
            dialog.notes.clear()
            QTest.mouseClick(dialog.notes.viewport(), Qt.MouseButton.LeftButton)
            assert app.focusWidget() is dialog.notes, "Notes did not receive focus after clicking"
            for key in (Qt.Key.Key_H, Qt.Key.Key_E, Qt.Key.Key_L, Qt.Key.Key_L, Qt.Key.Key_O):
                QTest.keyClick(dialog.windowHandle(), key)
            assert dialog.notes.toPlainText() == "hello", (
                "Notes did not receive window keyboard events"
            )
            dialog.rating.setCurrentIndex(dialog.rating.findData(3.5))
            dialog.added_on.setDate(QDate(2020, 1, 2))
            app.processEvents()
            detail = dialog.grab()
            if screenshot_dir:
                screenshot_dir.mkdir(parents=True, exist_ok=True)
                assert pixmap.save(str(screenshot_dir / "grid.png"))
                assert detail.save(str(screenshot_dir / "detail.png"))
                assert rating_panel.save(str(screenshot_dir / "rating-filter.png"))
            dialog.close()
            assert library.albums[first.id] == replace(
                first,
                notes="hello",
                rating=3.5,
                added_on="2020-01-02",
            )
            library.reload()
            assert library.albums[first.id].notes == "hello"
            window.close()
        finally:
            library.close()
    print(
        "Smoke test passed: provider resources, grid, rating filter, native input, and saved edits."
    )
