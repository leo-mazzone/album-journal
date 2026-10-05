"""Qt desktop interface. Network calls run in workers; library writes stay on the UI thread."""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import (
    QDate,
    QObject,
    QRectF,
    QRunnable,
    QSettings,
    QSize,
    Qt,
    QThreadPool,
    QTimer,
    QUrl,
    Signal,
)
from PySide6.QtGui import (
    QAction,
    QColor,
    QDesktopServices,
    QFont,
    QIcon,
    QKeySequence,
    QPainter,
    QPainterPath,
    QPixmap,
    QShortcut,
)
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDateEdit,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTextEdit,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .providers import ImportResult, YouTubeMusicProvider
from .rating_filter import RatingFilterPopup
from .storage import Album, Library, LibraryError
from .theme import configure_style, quiet_button, secondary


def cover_pixmap(library: Library | None = None, album: Album | None = None) -> QPixmap:
    if library and album and album.cover_path:
        try:
            pixmap = QPixmap(str(library.cover_file(album)))
            if not pixmap.isNull():
                return pixmap
        except LibraryError:
            pass
    pixmap = QPixmap(400, 400)
    pixmap.fill(QColor("#2c2c30"))
    painter = QPainter(pixmap)
    painter.setPen(QColor("#777780"))
    font = QFont(QApplication.font())
    font.setPointSize(72)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "♫")
    painter.end()
    return pixmap


def set_cover(label: QLabel, pixmap: QPixmap, size: int = 200) -> None:
    label.setFixedSize(size, size)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    ratio = label.devicePixelRatioF()
    rounded = QPixmap(round(size * ratio), round(size * ratio))
    rounded.setDevicePixelRatio(ratio)
    rounded.fill(Qt.GlobalColor.transparent)
    painter = QPainter(rounded)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, size, size), 8, 8)
    painter.setClipPath(path)
    scaled = pixmap.scaled(
        round(size * ratio),
        round(size * ratio),
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    scaled.setDevicePixelRatio(ratio)
    width, height = scaled.width() / ratio, scaled.height() / ratio
    painter.drawPixmap(
        QRectF((size - width) / 2, (size - height) / 2, width, height),
        scaled,
        QRectF(scaled.rect()),
    )
    painter.end()
    label.setPixmap(rounded)


class WorkerSignals(QObject):
    result = Signal(object)
    error = Signal(str)


class FetchWorker(QRunnable):
    def __init__(self, provider, url: str):
        super().__init__()
        self.provider = provider
        self.url = url
        self.signals = WorkerSignals()

    def run(self):
        try:
            self.signals.result.emit(self.provider.fetch(self.url))
        except Exception as exc:
            self.signals.error.emit(str(exc) or "The album could not be fetched. Please retry.")


class AlbumDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index):
        return QSize(214, 286)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        rect = option.rect.adjusted(6, 4, -6, -4)
        if option.state & (QStyle.StateFlag.State_Selected | QStyle.StateFlag.State_MouseOver):
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#2c2c32"))
            if option.state & QStyle.StateFlag.State_Selected:
                painter.setPen(QColor("#0a84ff"))
            painter.drawRoundedRect(rect, 12, 12)
        album = index.data(Qt.ItemDataRole.UserRole)
        icon = index.data(Qt.ItemDataRole.DecorationRole)
        image_rect = rect.adjusted(6, 6, -6, 0)
        image_rect.setHeight(190)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 65))
        painter.drawRoundedRect(image_rect.adjusted(-1, 1, 1, 3), 8, 8)
        path = QPainterPath()
        path.addRoundedRect(image_rect, 7, 7)
        painter.save()
        painter.setClipPath(path)
        icon.paint(painter, image_rect, Qt.AlignmentFlag.AlignCenter)
        painter.restore()
        text_rect = rect.adjusted(6, 203, -6, 0)
        text_rect.setHeight(20)
        font = QFont(option.font)
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)
        painter.setPen(QColor("#f5f5f7"))
        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            painter.fontMetrics().elidedText(
                album.title, Qt.TextElideMode.ElideRight, text_rect.width()
            ),
        )
        font.setBold(False)
        font.setPointSizeF(max(9, option.font.pointSizeF() - 1))
        painter.setFont(font)
        painter.setPen(QColor("#b1b1ba"))
        text_rect.translate(0, 22)
        artist = ", ".join(album.artists) or "Unknown artist"
        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            painter.fontMetrics().elidedText(
                artist, Qt.TextElideMode.ElideRight, text_rect.width()
            ),
        )
        text_rect.translate(0, 21)
        painter.setPen(QColor("#898991"))
        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            QDate.fromString(album.added_on, "yyyy-MM-dd").toString("d MMM yyyy"),
        )
        painter.restore()


class AlbumGrid(QListWidget):
    keyboard_activated = Signal(object)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self.currentItem():
            self.keyboard_activated.emit(self.currentItem())
            event.accept()
        else:
            super().keyPressEvent(event)


class AddAlbumDialog(QDialog):
    def __init__(self, library: Library, provider, parent=None):
        super().__init__(parent)
        self.library = library
        self.provider = provider
        self.result_data: ImportResult | None = None
        self.selected_album: Album | None = None
        self._worker = None
        self.setWindowTitle("Add album")
        configure_dialog(self)
        self.setMinimumWidth(460)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)
        intro = QLabel("Paste a YouTube Music album link")
        layout.addWidget(intro)
        row = QHBoxLayout()
        self.link = QLineEdit()
        self.link.setPlaceholderText("https://music.youtube.com/playlist?list=…")
        self.link.setClearButtonEnabled(True)
        self.link.setAccessibleName("Album link")
        self.fetch_button = QPushButton("Fetch")
        self.fetch_button.clicked.connect(self.fetch)
        self.link.returnPressed.connect(self.fetch)
        self.link.textChanged.connect(self.invalidate_preview)
        row.addWidget(self.link, 1)
        row.addWidget(self.fetch_button)
        layout.addLayout(row)
        self.message = QLabel()
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        self.preview = QWidget()
        preview_layout = QVBoxLayout(self.preview)
        self.cover = QLabel()
        preview_layout.addWidget(self.cover, alignment=Qt.AlignmentFlag.AlignHCenter)
        self.title = QLabel()
        self.title.setTextFormat(Qt.TextFormat.PlainText)
        self.title.setWordWrap(True)
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title.setStyleSheet("font-size: 17px; font-weight: 600;")
        preview_layout.addWidget(self.title)
        self.artist = QLabel()
        secondary(self.artist)
        self.artist.setTextFormat(Qt.TextFormat.PlainText)
        self.artist.setWordWrap(True)
        self.artist.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_layout.addWidget(self.artist)
        form = QFormLayout()
        self.added_on = QDateEdit(QDate.currentDate())
        self.added_on.setCalendarPopup(True)
        self.added_on.setDisplayFormat("d MMM yyyy")
        self.added_on.setAccessibleName("Date added")
        form.addRow("Date added", self.added_on)
        preview_layout.addLayout(form)
        layout.addWidget(self.preview)
        self.preview.hide()
        actions = QHBoxLayout()
        actions.addStretch()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        self.save_button = QPushButton("Add album")
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self.save_album)
        self.save_button.setDefault(False)
        actions.addWidget(cancel)
        actions.addWidget(self.save_button)
        layout.addLayout(actions)

    def invalidate_preview(self):
        self.result_data = None
        self.preview.hide()
        self.save_button.setEnabled(False)
        self.message.clear()

    def fetch(self):
        if not self.fetch_button.isEnabled():
            return
        self.invalidate_preview()
        self.link.setEnabled(False)
        self.fetch_button.setEnabled(False)
        self.message.setText("Fetching album and cover…")
        self._worker = FetchWorker(self.provider, self.link.text().strip())
        self._worker.signals.result.connect(self.fetched)
        self._worker.signals.error.connect(self.failed)
        QThreadPool.globalInstance().start(self._worker)

    def fetched(self, result: ImportResult):
        self.link.setEnabled(True)
        self.fetch_button.setEnabled(True)
        existing = self.library.find(result.album.provider, result.album.provider_id)
        if existing:
            self.selected_album = existing
            self.accept()
            return
        self.result_data = result
        pixmap = QPixmap()
        if result.cover:
            pixmap.loadFromData(result.cover)
        set_cover(self.cover, pixmap if not pixmap.isNull() else cover_pixmap())
        self.title.setText(result.album.title)
        self.artist.setText(
            ", ".join(result.album.artists) + f" · {len(result.album.tracks)} tracks"
        )
        self.added_on.setDate(QDate.currentDate())
        self.message.setText(result.cover_error or "Ready to add.")
        self.preview.show()
        self.save_button.setEnabled(True)

    def failed(self, message: str):
        self.link.setEnabled(True)
        self.fetch_button.setEnabled(True)
        self.message.setText(message)

    def save_album(self):
        if not self.result_data:
            return
        album = replace(
            self.result_data.album, added_on=self.added_on.date().toString("yyyy-MM-dd")
        )
        try:
            if self.result_data.cover:
                album = self.library.save_cover(album, self.result_data.cover)
            else:
                self.library.save(album)
        except (LibraryError, OSError, ValueError) as exc:
            self.message.setText(str(exc))
            return
        self.selected_album = album
        self.accept()


class AlbumDialog(QDialog):
    def __init__(self, library: Library, album: Album, provider, parent=None):
        super().__init__(parent)
        self.library = library
        self.album = album
        self.provider = provider
        self._dirty = False
        self._worker = None
        self._removed = False
        self.setWindowTitle(album.title)
        configure_dialog(self)
        self.resize(640, 720)
        self.setMinimumSize(430, 450)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 16, 20, 20)
        top = QHBoxLayout()
        self.menu_button = QToolButton()
        quiet_button(self.menu_button)
        self.menu_button.setText("⋯")
        self.menu_button.setAccessibleName("Album actions")
        menu = QMenu(self)
        menu.addAction("Retry cover", self.retry_cover)
        menu.addAction("Remove album…", self.remove_album)
        self.menu_button.setMenu(menu)
        self.menu_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        top.addWidget(self.menu_button)
        top.addStretch()
        close = QToolButton()
        quiet_button(close)
        close.setText("×")
        close.setAccessibleName("Close album")
        close.setToolTip("Close (Escape)")
        close.clicked.connect(self.close)
        top.addWidget(close)
        outer.addLayout(top)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSpacing(16)
        album_header = QHBoxLayout()
        album_header.setSpacing(20)
        self.cover = QLabel()
        set_cover(self.cover, cover_pixmap(library, album), 170)
        album_header.addWidget(self.cover, alignment=Qt.AlignmentFlag.AlignTop)
        metadata = QVBoxLayout()
        metadata.setSpacing(10)
        title = QLabel(album.title)
        title.setTextFormat(Qt.TextFormat.PlainText)
        title.setWordWrap(True)
        title.setStyleSheet("font-size: 23px; font-weight: 600;")
        metadata.addWidget(title)
        artist = QLabel(", ".join(album.artists) or "Unknown artist")
        secondary(artist)
        artist.setTextFormat(Qt.TextFormat.PlainText)
        artist.setWordWrap(True)
        metadata.addWidget(artist)
        source = QPushButton("Open in YouTube Music")
        source.setObjectName("sourceLink")
        source.setFlat(True)
        source.clicked.connect(self.open_source)
        metadata.addWidget(source, alignment=Qt.AlignmentFlag.AlignLeft)
        form = QFormLayout()
        self.added_on = QDateEdit(QDate.fromString(album.added_on, "yyyy-MM-dd"))
        self.added_on.setCalendarPopup(True)
        self.added_on.setDisplayFormat("d MMM yyyy")
        form.addRow("Date added", self.added_on)
        self.rating = QComboBox()
        self.rating.addItem("Not rated", None)
        for step in range(1, 11):
            score = step / 2
            self.rating.addItem(f"{'★' * (step // 2)}{'½' if step % 2 else ''}", score)
        self.rating.setCurrentIndex(self.rating.findData(album.rating))
        form.addRow("Your rating", self.rating)
        metadata.addLayout(form)
        metadata.addStretch()
        album_header.addLayout(metadata, 1)
        layout.addLayout(album_header)
        self.notes = QTextEdit()
        self.notes.setAcceptRichText(False)
        self.notes.setPlainText(album.notes)
        self.notes.setPlaceholderText("Your notes (optional)")
        self.notes.setAccessibleName("Album notes")
        self.notes.setFixedHeight(130)
        layout.addWidget(self.notes)
        self.save_status = QLabel("Saved")
        secondary(self.save_status, muted=True)
        self.save_status.setWordWrap(True)
        layout.addWidget(self.save_status)
        self.retry_save = QPushButton("Retry saving")
        self.retry_save.hide()
        self.retry_save.clicked.connect(self.save_edits)
        layout.addWidget(self.retry_save)
        track_heading = QLabel(f"Tracklist · {len(album.tracks)} tracks")
        track_heading.setStyleSheet("font-weight: 600;")
        layout.addWidget(track_heading)
        tracks = QVBoxLayout()
        tracks.setSpacing(8)
        for index, track in enumerate(album.tracks, 1):
            row = QHBoxLayout()
            number = QLabel(str(index))
            number.setFixedWidth(26)
            secondary(number, muted=True)
            name = QLabel(track.title)
            name.setTextFormat(Qt.TextFormat.PlainText)
            name.setWordWrap(True)
            row.addWidget(number)
            row.addWidget(name, 1)
            if track.duration_seconds is not None:
                seconds = track.duration_seconds
                duration = QLabel(f"{seconds // 60}:{seconds % 60:02}")
                secondary(duration, muted=True)
                row.addWidget(duration)
            tracks.addLayout(row)
        layout.addLayout(tracks)
        layout.addStretch()
        scroll.setWidget(content)
        outer.addWidget(scroll)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(600)
        self.timer.timeout.connect(self.save_edits)
        self.notes.textChanged.connect(self.schedule_save)
        self.added_on.dateChanged.connect(self.schedule_save)
        self.rating.currentIndexChanged.connect(self.schedule_save)

    def schedule_save(self):
        self._dirty = True
        self.save_status.setText("Saving…")
        self.timer.start()

    def save_edits(self) -> bool:
        self.timer.stop()
        if not self._dirty or self._removed:
            return True
        updated = replace(
            self.album,
            added_on=self.added_on.date().toString("yyyy-MM-dd"),
            rating=self.rating.currentData(),
            notes=self.notes.toPlainText(),
        )
        try:
            self.library.save(updated)
        except (LibraryError, ValueError, OSError) as exc:
            self.save_status.setText(f"Not saved: {exc}")
            self.retry_save.show()
            return False
        self.album = updated
        self._dirty = False
        self.save_status.setText("Saved")
        self.retry_save.hide()
        return True

    def closeEvent(self, event):
        if self.save_edits():
            event.accept()
        else:
            event.ignore()

    def reject(self):
        if self.save_edits():
            super().reject()

    def open_source(self):
        url = QUrl(self.album.source_url)
        if url.scheme() == "https" and url.host() == "music.youtube.com":
            QDesktopServices.openUrl(url)

    def retry_cover(self):
        if not self.menu_button.isEnabled():
            return
        self.save_status.setText("Fetching cover…")
        self.menu_button.setEnabled(False)
        self._worker = FetchWorker(self.provider, self.album.source_url)
        self._worker.signals.result.connect(self.cover_fetched)
        self._worker.signals.error.connect(self.cover_failed)
        QThreadPool.globalInstance().start(self._worker)

    def cover_fetched(self, result: ImportResult):
        self.menu_button.setEnabled(True)
        if not result.cover:
            self.cover_failed(result.cover_error or "No cover was returned.")
            return
        if self._removed:
            return
        try:
            self.album = self.library.save_cover(self.album, result.cover)
            set_cover(self.cover, cover_pixmap(self.library, self.album), 170)
            if self._dirty:
                self.save_edits()
            else:
                self.save_status.setText("Cover saved")
        except LibraryError as exc:
            self.cover_failed(str(exc))

    def cover_failed(self, message: str):
        self.menu_button.setEnabled(True)
        self.save_status.setText(message)

    def remove_album(self):
        answer = QMessageBox.question(
            self,
            "Remove album?",
            f"Remove “{self.album.title}” and its notes from this library?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.library.remove(self.album)
        except LibraryError as exc:
            QMessageBox.warning(self, "Could not remove album", str(exc))
            return
        self._removed = True
        self.timer.stop()
        self.accept()


class MainWindow(QMainWindow):
    def __init__(self, library: Library, settings: QSettings | None = None, provider=None):
        super().__init__()
        self.library = library
        self.settings = settings or QSettings()
        self.provider = provider or YouTubeMusicProvider()
        self.rating_range: tuple[float, float] | None = None
        self.setWindowTitle("Album Journal")
        self.resize(940, 760)
        self.setMinimumSize(450, 400)
        central = QWidget()
        central.setObjectName("libraryBody")
        layout = QVBoxLayout(central)
        layout.setContentsMargins(24, 24, 24, 12)
        layout.setSpacing(18)
        toolbar = QToolBar("Library", self)
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        toolbar.setAllowedAreas(Qt.ToolBarArea.TopToolBarArea)
        toolbar.setContextMenuPolicy(Qt.ContextMenuPolicy.PreventContextMenu)
        header_widget = QWidget()
        header_widget.setObjectName("libraryHeader")
        header = QHBoxLayout(header_widget)
        header.setContentsMargins(0, 4, 0, 4)
        header.setSpacing(12)
        heading = QLabel("Albums")
        heading.setObjectName("libraryTitle")
        header.addWidget(heading)
        header.addStretch()
        add = QPushButton("+ Add album")
        add.clicked.connect(self.add_album)
        header.addWidget(add)
        more = QToolButton()
        quiet_button(more)
        more.setText("⋯")
        more.setAccessibleName("Library menu")
        menu = QMenu(self)
        menu.addAction("Open another library…", self.open_library)
        menu.addAction("Show library folder", self.show_folder)
        self.warnings_action = menu.addAction("Library warnings…", self.show_warnings)
        more.setMenu(menu)
        more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        header.addWidget(more)
        toolbar.addWidget(header_widget)
        self.addToolBar(toolbar)
        if sys.platform == "darwin":
            self.setUnifiedTitleAndToolBarOnMac(True)
        filters = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setObjectName("albumSearch")
        self.search.setPlaceholderText("Search albums or artists")
        self.search.setClearButtonEnabled(True)
        self.search.setAccessibleName("Search albums or artists")
        self.search.textChanged.connect(self.refresh)
        filters.addWidget(self.search, 1)
        self.year = QComboBox()
        self.year.setAccessibleName("Year added")
        self.year.currentIndexChanged.connect(self.refresh)
        filters.addWidget(self.year)
        self.rating_button = QToolButton()
        self.rating_button.setObjectName("ratingFilter")
        self.rating_button.setText("Rating")
        self.rating_button.setAccessibleName("Filter by rating")
        self.rating_button.setToolTip("Select a minimum and maximum rating")
        self.rating_button.clicked.connect(self.open_rating_filter)
        filters.addWidget(self.rating_button)
        self.rating_popup = RatingFilterPopup(self)
        self.rating_popup.applied.connect(self.apply_rating_filter)
        self.rating_popup.cleared.connect(self.clear_rating_filter)
        layout.addLayout(filters)
        self.grid = AlbumGrid()
        self.grid.setObjectName("albumGrid")
        self.grid.setViewMode(QListView.ViewMode.IconMode)
        self.grid.setResizeMode(QListView.ResizeMode.Adjust)
        self.grid.setMovement(QListView.Movement.Static)
        self.grid.setWrapping(True)
        self.grid.setSpacing(10)
        self.grid.setGridSize(QSize(214, 286))
        self.grid.setIconSize(QSize(190, 190))
        self.grid.setItemDelegate(AlbumDelegate(self.grid))
        self.grid.setMouseTracking(True)
        self.grid.setFrameShape(QListWidget.Shape.NoFrame)
        self.grid.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.grid.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.grid.setAccessibleName("Album covers")
        self.grid.itemClicked.connect(self.open_album)
        self.grid.keyboard_activated.connect(self.open_album)
        layout.addWidget(self.grid, 1)
        self.empty = QLabel()
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setWordWrap(True)
        layout.addWidget(self.empty)
        self.count = QLabel()
        secondary(self.count, muted=True)
        layout.addWidget(self.count)
        self.setCentralWidget(central)
        self.configure_menus()
        self.refresh()

    def configure_menus(self):
        file_menu = self.menuBar().addMenu("File")
        for label, shortcut, callback in (
            ("Add Album…", QKeySequence.StandardKey.New, self.add_album),
            ("Open Library…", QKeySequence.StandardKey.Open, self.open_library),
            (
                "Close Window",
                QKeySequence.StandardKey.Close,
                lambda: QApplication.activeWindow().close(),
            ),
        ):
            action = QAction(label, self)
            action.setShortcut(QKeySequence(shortcut))
            action.triggered.connect(callback)
            file_menu.addAction(action)
        view_menu = self.menuBar().addMenu("View")
        search = QAction("Search Albums", self)
        search.setShortcut(QKeySequence(QKeySequence.StandardKey.Find))
        search.triggered.connect(self.focus_search)
        view_menu.addAction(search)
        view_menu.addAction("Show Library Folder", self.show_folder)

    def focus_search(self):
        self.search.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.search.selectAll()

    def open_rating_filter(self):
        if self.rating_popup.isVisible():
            self.rating_popup.hide()
        else:
            self.rating_popup.open_for(self.rating_button, self.rating_range)

    def apply_rating_filter(self, lower, upper):
        self.rating_range = (lower, upper)
        summary = f"{lower:g}" if lower == upper else f"{lower:g}–{upper:g}"
        self.rating_button.setText(f"★ {summary}")
        self.rating_button.setAccessibleName(f"Rating filter: {lower:g} to {upper:g} stars")
        self.rating_button.setProperty("active", True)
        self.rating_button.style().unpolish(self.rating_button)
        self.rating_button.style().polish(self.rating_button)
        self.refresh()

    def clear_rating_filter(self):
        self.rating_range = None
        self.rating_button.setText("Rating")
        self.rating_button.setAccessibleName("Filter by rating")
        self.rating_button.setProperty("active", False)
        self.rating_button.style().unpolish(self.rating_button)
        self.rating_button.style().polish(self.rating_button)
        self.refresh()

    def refresh(self):
        scroll = self.grid.verticalScrollBar().value()
        current = self.year.currentData()
        years = {a.added_on[:4] for a in self.library.albums.values()}
        if current:
            years.add(current)
        self.year.blockSignals(True)
        self.year.clear()
        self.year.addItem("All years added", None)
        for year in sorted(years, reverse=True):
            self.year.addItem(year, year)
        self.year.setCurrentIndex(max(0, self.year.findData(current)))
        self.year.blockSignals(False)
        self.grid.clear()
        lower, upper = self.rating_range or (None, None)
        albums = self.library.search(
            self.search.text(), current, min_rating=lower, max_rating=upper
        )
        for album in albums:
            icon = QIcon(
                cover_pixmap(self.library, album).scaled(
                    344,
                    344,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
            item = QListWidgetItem(icon, album.title)
            item.setData(Qt.ItemDataRole.UserRole, album)
            item.setToolTip(f"{album.title}\n{', '.join(album.artists)}\nAdded {album.added_on}")
            item.setSizeHint(QSize(214, 286))
            self.grid.addItem(item)
        self.grid.doItemsLayout()
        self.grid.verticalScrollBar().setValue(scroll)
        self.grid.setVisible(bool(albums))
        self.empty.setVisible(not albums)
        self.empty.setText(
            "No albums match your search."
            if self.library.albums
            else "Your journal starts here.\nAdd an album using a YouTube Music link."
        )
        self.count.setText(
            f"{len(albums)} of {len(self.library.albums)} albums"
            + (
                f" · {len(self.library.warnings)} library warnings (see menu)"
                if self.library.warnings
                else ""
            )
        )
        self.warnings_action.setEnabled(bool(self.library.warnings))

    def open_album(self, item):
        album = self.library.albums.get(item.data(Qt.ItemDataRole.UserRole).id)
        if album:
            dialog = AlbumDialog(self.library, album, self.provider, self)
            dialog.exec()
            self.refresh()
            dialog.deleteLater()

    def add_album(self):
        dialog = AddAlbumDialog(self.library, self.provider, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh()
            if dialog.selected_album:
                detail = AlbumDialog(self.library, dialog.selected_album, self.provider, self)
                detail.exec()
                self.refresh()
                detail.deleteLater()
        dialog.deleteLater()

    def open_library(self):
        root = QFileDialog.getExistingDirectory(
            self, "Open or create a library folder", str(self.library.root.parent)
        )
        if not root or Path(root).resolve() == self.library.root:
            return
        try:
            new_library = Library(Path(root))
        except LibraryError as exc:
            QMessageBox.warning(self, "Could not open library", str(exc))
            return
        self.library.close()
        self.library = new_library
        self.settings.setValue("library_path", str(new_library.root))
        self.clear_rating_filter()
        self.search.clear()
        self.year.setCurrentIndex(0)
        self.grid.verticalScrollBar().setValue(0)
        self.refresh()

    def show_folder(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.library.root)))

    def show_warnings(self):
        box = QMessageBox(self)
        box.setWindowTitle("Library warnings")
        box.setText("Some library files need attention. Valid albums are still available.")
        box.setDetailedText("\n".join(self.library.warnings))
        box.exec()

    def closeEvent(self, event):
        self.library.close()
        super().closeEvent(event)


def configure_dialog(dialog: QDialog):
    if sys.platform == "darwin" and dialog.parentWidget():
        dialog.setWindowModality(Qt.WindowModality.WindowModal)
        # Sheet is a window type, not an additive hint. OR-ing Dialog (3) with
        # Sheet (5) creates Drawer (7), which cannot receive native keyboard focus.
        dialog.setWindowFlags(
            (dialog.windowFlags() & ~Qt.WindowType.WindowType_Mask) | Qt.WindowType.Sheet
        )
    shortcut = QShortcut(QKeySequence(QKeySequence.StandardKey.Close), dialog)
    shortcut.activated.connect(dialog.close)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="A portable desktop album journal")
    parser.add_argument(
        "--smoke-test", action="store_true", help="Run an offline packaging check and exit"
    )
    parser.add_argument(
        "--screenshots", type=Path, help="Save smoke-test screenshots to this folder"
    )
    args = parser.parse_args()
    if args.screenshots and not args.smoke_test:
        parser.error("--screenshots requires --smoke-test")
    app = QApplication(sys.argv)
    app.setOrganizationName("AlbumJournal")
    app.setApplicationName("Album Journal")
    app.setWindowIcon(QIcon(str(Path(__file__).parent / "assets" / "app-icon.png")))
    configure_style(app)
    if args.smoke_test:
        from .diagnostics import smoke_test

        smoke_test(app, args.screenshots)
        return 0
    settings = QSettings()
    library = None
    saved = settings.value("library_path", "")
    if saved:
        try:
            if not Path(saved).is_dir():
                raise LibraryError(
                    "The remembered library folder has moved or is unavailable. Choose its new location."
                )
            library = Library(Path(saved))
        except LibraryError as exc:
            QMessageBox.warning(None, "Could not open library", str(exc))
    while library is None:
        root = QFileDialog.getExistingDirectory(
            None,
            "Choose an empty folder or an existing Album Journal library",
            str(Path.home()),
        )
        if not root:
            return 0
        try:
            library = Library(Path(root))
        except LibraryError as exc:
            QMessageBox.warning(None, "Could not open library", str(exc))
    settings.setValue("library_path", str(library.root))
    window = MainWindow(library, settings)
    window.show()
    try:
        return app.exec()
    finally:
        window.library.close()


if __name__ == "__main__":
    sys.exit(main())
