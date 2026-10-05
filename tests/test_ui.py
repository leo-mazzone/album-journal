from dataclasses import replace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from PySide6.QtCore import QDate, Qt, QTimer
from PySide6.QtWidgets import QMessageBox, QWidget

from album_journal.app import AddAlbumDialog, AlbumDialog, MainWindow, configure_style
from album_journal.providers import ImportResult
from album_journal.storage import LibraryError


def test_grid_combines_search_and_year(qtbot, qapp, library, album):
    configure_style(qapp)
    library.save(replace(album, added_on="2022-07-01"))
    library.save(replace(album, id=str(uuid4()), provider_id="MPREb_second", added_on="2023-01-01"))
    window = MainWindow(library)
    qtbot.addWidget(window)
    window.show()
    window.search.setText("BJÖRK example")
    assert window.grid.count() == 2
    window.year.setCurrentIndex(window.year.findData("2022"))
    assert window.grid.count() == 1
    window.search.setText("missing")
    assert window.grid.count() == 0
    assert window.empty.isVisible()


def test_details_save_on_escape_and_persist(qtbot, library, album):
    library.save(album)
    dialog = AlbumDialog(library, album, Mock())
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.notes.setPlainText("日本語\nRemember this 🎵")
    dialog.rating.setCurrentIndex(dialog.rating.findData(4.5))
    dialog.added_on.setDate(QDate(2020, 1, 2))
    qtbot.keyClick(dialog, Qt.Key.Key_Escape)
    assert not dialog.isVisible()
    library.reload()
    saved = library.albums[album.id]
    assert saved.notes == "日本語\nRemember this 🎵"
    assert saved.rating == 4.5
    assert saved.added_on == "2020-01-02"


def test_save_failure_retains_notes_and_blocks_close(qtbot, library, album, monkeypatch):
    library.save(album)
    dialog = AlbumDialog(library, album, Mock())
    qtbot.addWidget(dialog)
    dialog.show()
    save = library.save
    monkeypatch.setattr(library, "save", Mock(side_effect=LibraryError("Disk is full")))
    dialog.notes.setPlainText("Unsaved note")
    dialog.close()
    assert dialog.isVisible()
    assert dialog.notes.toPlainText() == "Unsaved note"
    assert "Not saved" in dialog.save_status.text()
    monkeypatch.setattr(library, "save", save)
    dialog.close()
    assert library.albums[album.id].notes == "Unsaved note"


def test_async_import_and_duplicate_keeps_original(qtbot, library, album):
    library.save(replace(album, notes="Original", added_on="2001-01-01", rating=2.5))
    provider = Mock()
    provider.fetch.return_value = ImportResult(replace(album, id=str(uuid4())), None)
    dialog = AddAlbumDialog(library, provider)
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.link.setText(album.source_url)
    with qtbot.waitSignal(dialog.accepted, timeout=3000):
        dialog.fetch()
    assert dialog.selected_album.notes == "Original"
    assert dialog.selected_album.added_on == "2001-01-01"
    assert len(library.albums) == 1


def test_cover_failure_allows_adding_and_retry(qtbot, library, album):
    dialog = AddAlbumDialog(library, Mock())
    qtbot.addWidget(dialog)
    dialog.fetched(ImportResult(album, None, "Cover unavailable"))
    dialog.added_on.setDate(QDate(2021, 3, 4))
    dialog.save_album()
    saved = library.albums[album.id]
    assert saved.cover_path is None
    assert saved.added_on == "2021-03-04"
    detail = AlbumDialog(library, saved, Mock())
    qtbot.addWidget(detail)
    from .test_providers import image_bytes

    detail.cover_fetched(ImportResult(album, image_bytes()))
    assert library.cover_file(detail.album).is_file()
    assert detail.album.added_on == "2021-03-04"


def test_remove_requires_confirmation(qtbot, library, album, monkeypatch):
    library.save(album)
    dialog = AlbumDialog(library, album, Mock())
    qtbot.addWidget(dialog)
    monkeypatch.setattr(QMessageBox, "question", Mock(return_value=QMessageBox.StandardButton.No))
    dialog.remove_album()
    assert album.id in library.albums
    monkeypatch.setattr(QMessageBox, "question", Mock(return_value=QMessageBox.StandardButton.Yes))
    dialog.remove_album()
    assert album.id not in library.albums


def test_closing_details_restores_grid_position_and_filters(qtbot, qapp, library, album):
    for i in range(32):
        library.save(
            replace(album, id=str(uuid4()), provider_id=f"MPREb_{i}", added_on="2022-01-01")
        )
    window = MainWindow(library)
    qtbot.addWidget(window)
    window.show()
    window.search.setText("björk")
    window.year.setCurrentIndex(window.year.findData("2022"))
    window.grid.doItemsLayout()
    window.grid.verticalScrollBar().setValue(300)
    before = window.grid.verticalScrollBar().value()
    assert before > 0
    QTimer.singleShot(20, lambda: qapp.activeModalWidget().close())
    window.open_album(window.grid.item(0))
    assert window.grid.verticalScrollBar().value() == before
    assert window.search.text() == "björk"
    assert window.year.currentData() == "2022"


def test_keyboard_activation_emits_once(qtbot, library, album):
    library.save(album)
    window = MainWindow(library)
    qtbot.addWidget(window)
    # Test the grid signal without opening a modal window.
    window.grid.keyboard_activated.disconnect(window.open_album)
    activated = Mock()
    window.grid.keyboard_activated.connect(activated)
    window.grid.setCurrentRow(0)
    qtbot.keyClick(window.grid, Qt.Key.Key_Return)
    activated.assert_called_once()


@pytest.mark.parametrize("dialog_type", [AlbumDialog, AddAlbumDialog])
def test_mac_dialog_has_sheet_type_not_nonactivating_drawer(
    qtbot, library, album, monkeypatch, dialog_type
):
    monkeypatch.setattr("album_journal.app.sys.platform", "darwin")
    parent = QWidget()
    qtbot.addWidget(parent)
    if dialog_type is AlbumDialog:
        dialog = dialog_type(library, album, Mock(), parent)
    else:
        dialog = dialog_type(library, Mock(), parent)
    qtbot.addWidget(dialog)
    assert dialog.windowType() == Qt.WindowType.Sheet
    assert dialog.windowModality() == Qt.WindowModality.WindowModal


def test_click_notes_and_type_through_dialog_window(qtbot, qapp, library, album):
    from PySide6.QtTest import QTest

    library.save(album)
    parent = MainWindow(library)
    qtbot.addWidget(parent)
    parent.show()
    dialog = AlbumDialog(library, album, Mock(), parent)
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.activateWindow()
    qtbot.waitUntil(dialog.isActiveWindow)
    qtbot.mouseClick(dialog.notes.viewport(), Qt.MouseButton.LeftButton)
    assert qapp.focusWidget() is dialog.notes
    # QWindow events follow the actual focused widget; don't insert text directly.
    for key in (Qt.Key.Key_H, Qt.Key.Key_E, Qt.Key.Key_L, Qt.Key.Key_L, Qt.Key.Key_O):
        QTest.keyClick(dialog.windowHandle(), key)
    assert dialog.notes.toPlainText() == "hello"
    qtbot.waitUntil(lambda: library.albums[album.id].notes == "hello")
    dialog.close()
    library.reload()
    assert library.albums[album.id].notes == "hello"
