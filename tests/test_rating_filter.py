from dataclasses import replace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QFileDialog

from album_journal.app import MainWindow
from album_journal.rating_filter import RatingFilterPopup, RatingRangeSlider
from album_journal.storage import Library


@pytest.fixture
def rated_library(library, album):
    for index, rating in enumerate((None, 0.5, 3, 3.5, 5)):
        library.save(
            replace(
                album,
                id=str(uuid4()),
                provider_id=f"MPREb_rating_{index}",
                rating=rating,
                title="Night Example" if rating == 3.5 else "Álbum Example",
                added_on="2023-01-01" if rating == 5 else "2022-01-01",
            )
        )
    return library


def test_rating_range_includes_endpoints_and_excludes_unrated(rated_library):
    assert {a.rating for a in rated_library.search(min_rating=3, max_rating=3.5)} == {3, 3.5}
    assert [a.rating for a in rated_library.search(min_rating=3.5, max_rating=3.5)] == [3.5]
    assert len(rated_library.search(min_rating=0.5, max_rating=5)) == 4
    assert len(rated_library.search()) == 5


def test_rating_combines_with_text_and_year(rated_library):
    assert {
        a.rating for a in rated_library.search("BJÖRK", "2022", min_rating=3, max_rating=5)
    } == {3, 3.5}
    assert [
        a.rating for a in rated_library.search("night", "2022", min_rating=3, max_rating=5)
    ] == [3.5]
    assert rated_library.search("night", "2023", min_rating=3, max_rating=5) == []
    assert {a.rating for a in rated_library.search(min_rating=3.5)} == {3.5, 5}
    assert {a.rating for a in rated_library.search(max_rating=0.5)} == {0.5}


@pytest.mark.parametrize(
    "bounds",
    [
        {"min_rating": 4, "max_rating": 3},
        {"min_rating": 0},
        {"max_rating": 5.5},
        {"min_rating": 3.2},
        {"max_rating": True},
        {"min_rating": float("nan")},
    ],
)
def test_invalid_bounds_are_rejected(rated_library, bounds):
    with pytest.raises(ValueError):
        rated_library.search(**bounds)


def make_window(qtbot, library):
    window = MainWindow(library)
    qtbot.addWidget(window)
    window.show()
    window.activateWindow()
    qtbot.waitUntil(window.isActiveWindow)
    return window


def test_panel_draft_apply_and_clear_combine_filters(qtbot, rated_library):
    window = make_window(qtbot, rated_library)
    window.search.setText("björk")
    window.year.setCurrentIndex(window.year.findData("2022"))
    window.open_rating_filter()
    panel = window.rating_popup
    assert panel.slider.values == (0.5, 5)
    panel.minimum.setValue(3)
    panel.maximum.setValue(3.5)
    assert window.grid.count() == 4  # Editing is a draft until Apply.
    qtbot.mouseClick(panel.apply_button, Qt.MouseButton.LeftButton)
    assert window.rating_range == (3, 3.5)
    assert window.grid.count() == 2
    assert window.rating_button.text() == "★ 3–3.5"
    assert not panel.isVisible()
    window.open_rating_filter()
    assert panel.slider.values == (3, 3.5)
    qtbot.mouseClick(panel.clear_button, Qt.MouseButton.LeftButton)
    assert window.rating_range is None
    assert window.grid.count() == 4
    assert window.search.text() == "björk"
    assert window.year.currentData() == "2022"
    assert window.rating_button.text() == "Rating"


def test_escape_discards_draft_and_reopening_restores_range(qtbot, rated_library):
    window = make_window(qtbot, rated_library)
    window.apply_rating_filter(3, 5)
    window.open_rating_filter()
    panel = window.rating_popup
    panel.maximum.setValue(3.5)
    qtbot.keyClick(panel.maximum, Qt.Key.Key_Escape)
    assert not panel.isVisible()
    assert window.rating_range == (3, 5)
    window.open_rating_filter()
    assert panel.maximum.value() == 5
    panel.hide()


def test_click_outside_dismisses_without_applying(qtbot, rated_library):
    window = make_window(qtbot, rated_library)
    window.open_rating_filter()
    panel = window.rating_popup
    panel.minimum.setValue(4)
    # Route the outside click through the popup's window, as the platform does.
    QTest.mouseClick(panel.windowHandle(), Qt.MouseButton.LeftButton, pos=QPoint(-20, -20))
    qtbot.waitUntil(lambda: not panel.isVisible())
    assert window.rating_range is None
    assert window.grid.count() == 5


def test_slider_drag_syncs_controls_and_handles_cannot_cross(qtbot):
    panel = RatingFilterPopup()
    qtbot.addWidget(panel)
    panel.show()
    slider = panel.slider
    slider.set_values(2, 4)
    low_x = round(slider._x(4))
    high_x = round(slider._x(8))
    qtbot.mousePress(slider, Qt.MouseButton.LeftButton, pos=QPoint(low_x, 36))
    qtbot.mouseMove(slider, QPoint(slider.width(), 36))
    qtbot.mouseRelease(slider, Qt.MouseButton.LeftButton, pos=QPoint(slider.width(), 36))
    assert slider.values == (4, 4)
    assert panel.minimum.value() == panel.maximum.value() == 4
    # Split overlapping handles by dragging the right side outward.
    qtbot.mousePress(slider, Qt.MouseButton.LeftButton, pos=QPoint(high_x + 2, 36))
    qtbot.mouseRelease(slider, Qt.MouseButton.LeftButton, pos=QPoint(round(slider._x(10)), 36))
    assert slider.values == (4, 5)
    assert panel.maximum.value() == 5
    panel.hide()


def test_slider_keyboard_half_steps_and_switching_handles(qtbot):
    slider = RatingRangeSlider()
    qtbot.addWidget(slider)
    slider.show()
    slider.set_values(2, 4)
    qtbot.keyClick(slider, Qt.Key.Key_Right)
    assert slider.values == (2.5, 4)
    qtbot.keyClick(slider, Qt.Key.Key_Space)
    qtbot.keyClick(slider, Qt.Key.Key_Left)
    assert slider.values == (2.5, 3.5)
    qtbot.keyClick(slider, Qt.Key.Key_Home)
    assert slider.values == (2.5, 2.5)
    qtbot.keyClick(slider, Qt.Key.Key_End)
    assert slider.values == (2.5, 5)


def test_native_number_typing_is_half_star_and_synchronized(qtbot, rated_library):
    window = make_window(qtbot, rated_library)
    window.open_rating_filter()
    panel = window.rating_popup
    panel.minimum.selectAll()
    qtbot.keyClicks(panel.minimum, "3.2")
    qtbot.keyClick(panel.minimum, Qt.Key.Key_Tab)
    assert panel.minimum.value() == 3
    assert panel.slider.values == (3, 5)
    panel.maximum.setValue(3)
    panel.minimum.stepUp()
    assert panel.slider.values == (3, 3)
    panel.apply_filter()
    assert window.grid.count() == 1
    assert window.rating_button.text() == "★ 3"


def test_detail_rating_edit_reevaluates_range(qtbot, qapp, rated_library):
    window = make_window(qtbot, rated_library)
    window.apply_rating_filter(3, 3)
    assert window.grid.count() == 1

    def change_rating():
        dialog = qapp.activeModalWidget()
        dialog.rating.setCurrentIndex(dialog.rating.findData(5))
        dialog.close()

    QTimer.singleShot(20, change_rating)
    window.open_album(window.grid.item(0))
    assert window.rating_range == (3, 3)
    assert window.grid.count() == 0
    assert "No albums" in window.empty.text()


def test_switching_library_resets_rating_and_draft(qtbot, rated_library, tmp_path, monkeypatch):
    destination = tmp_path / "other"
    other = Library(destination)
    other.close()
    window = make_window(qtbot, rated_library)
    window.apply_rating_filter(3, 4)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", Mock(return_value=str(destination)))
    window.open_library()
    try:
        assert window.rating_range is None
        assert window.rating_button.text() == "Rating"
        window.open_rating_filter()
        assert window.rating_popup.slider.values == (0.5, 5)
        window.rating_popup.hide()
    finally:
        window.library.close()


def test_rating_button_and_popup_fit_narrow_window(qtbot, rated_library):
    window = make_window(qtbot, rated_library)
    window.resize(450, 400)
    window.apply_rating_filter(0.5, 4.5)
    window.open_rating_filter()
    panel = window.rating_popup
    assert window.width() == 450
    assert window.rating_button.isVisible()
    assert panel.screen().availableGeometry().contains(panel.frameGeometry())
    assert panel.windowType() == Qt.WindowType.Popup
    panel.hide()
