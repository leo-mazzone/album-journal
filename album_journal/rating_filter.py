"""An anchored rating panel with a discrete, keyboard-operable range slider."""

from PySide6.QtCore import QPoint, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QKeySequence, QPainter, QPen, QShortcut
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .theme import secondary


class RatingRangeSlider(QWidget):
    range_changed = Signal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lower, self._upper = 1, 10
        self._active = 0
        self._dragging = False
        self._hover = None
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setAccessibleName("Rating range")
        self.setAccessibleDescription(
            "Left and right adjust the selected bound by half a star. "
            "Space switches between minimum and maximum. Min and Max fields provide precise entry."
        )
        self.setToolTip("Drag either handle · Arrow keys adjust · Space switches handles")
        self.setFixedHeight(76)

    def sizeHint(self):
        return QSize(280, 76)

    @property
    def values(self):
        return self._lower / 2, self._upper / 2

    def set_values(self, lower: float, upper: float):
        low, high = round(lower * 2), round(upper * 2)
        if not 1 <= low <= high <= 10:
            raise ValueError("Rating bounds must be between 0.5 and 5, in ascending order")
        changed = (low, high) != (self._lower, self._upper)
        self._lower, self._upper = low, high
        self.update()
        if changed:
            self.range_changed.emit(*self.values)

    def _x(self, step):
        return 14 + (step - 1) / 9 * max(1, self.width() - 28)

    def _step(self, x):
        return max(1, min(10, round(1 + (x - 14) / max(1, self.width() - 28) * 9)))

    def _move_active(self, step):
        if self._active == 0:
            self.set_values(max(1, min(step, self._upper)) / 2, self._upper / 2)
        else:
            self.set_values(self._lower / 2, max(self._lower, min(step, 10)) / 2)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        left, right = self._x(self._lower), self._x(self._upper)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#45454c"))
        painter.drawRoundedRect(QRectF(14, 34, self.width() - 28, 4), 2, 2)
        painter.setBrush(QColor("#0a84ff"))
        painter.drawRoundedRect(QRectF(left, 34, max(2, right - left), 4), 2, 2)
        for handle, x in enumerate((left, right)):
            if (self.hasFocus() and handle == self._active) or handle == self._hover:
                painter.setBrush(QColor("#0a84ff"))
                painter.drawEllipse(QPoint(round(x), 36), 11, 11)
            painter.setBrush(QColor(0, 0, 0, 65))
            painter.drawEllipse(QPoint(round(x), 38), 8, 8)
            painter.setPen(QPen(QColor("#e8e8ed"), 1))
            painter.setBrush(QColor("#f5f5f7"))
            painter.drawEllipse(QPoint(round(x), 36), 7, 7)
            painter.setPen(Qt.PenStyle.NoPen)
        painter.setPen(QColor("#a1a1a9"))
        painter.drawText(QRectF(4, 56, 60, 18), Qt.AlignmentFlag.AlignLeft, "0.5 ★")
        painter.drawText(QRectF(self.width() - 64, 56, 60, 18), Qt.AlignmentFlag.AlignRight, "5 ★")
        if self._dragging or self.hasFocus():
            value = self.values[self._active]
            x = left if self._active == 0 else right
            x = max(22, min(x, self.width() - 22))
            painter.setPen(QColor("#f5f5f7"))
            painter.drawText(QRectF(x - 22, 2, 44, 20), Qt.AlignmentFlag.AlignCenter, f"{value:g}")

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or abs(event.position().y() - 36) > 18:
            event.ignore()
            return
        x = event.position().x()
        left, right = self._x(self._lower), self._x(self._upper)
        # When handles overlap, clicking either side lets that bound move outward.
        if self._lower == self._upper:
            self._active = 0 if x <= left else 1
        else:
            self._active = 0 if abs(x - left) <= abs(x - right) else 1
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        self._dragging = True
        self._move_active(self._step(x))
        event.accept()

    def mouseMoveEvent(self, event):
        if self._dragging:
            self._move_active(self._step(event.position().x()))
        else:
            distances = [abs(event.position().x() - self._x(v)) for v in (self._lower, self._upper)]
            nearest = 0 if distances[0] <= distances[1] else 1
            self._hover = (
                nearest if min(distances) <= 14 and abs(event.position().y() - 36) <= 16 else None
            )
            self.update()
        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._dragging:
            self._move_active(self._step(event.position().x()))
            self._dragging = False
            self.update()
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def leaveEvent(self, event):
        self._hover = None
        self.update()
        super().leaveEvent(event)

    def focusInEvent(self, event):
        self.update()
        super().focusInEvent(event)

    def focusOutEvent(self, event):
        self.update()
        super().focusOutEvent(event)

    def keyPressEvent(self, event):
        key = event.key()
        current = self._lower if self._active == 0 else self._upper
        if key in (Qt.Key.Key_Left, Qt.Key.Key_Down):
            self._move_active(current - 1)
        elif key in (Qt.Key.Key_Right, Qt.Key.Key_Up):
            self._move_active(current + 1)
        elif key == Qt.Key.Key_Space:
            self._active = 1 - self._active
            self.update()
        elif key == Qt.Key.Key_Home:
            self._move_active(1)
        elif key == Qt.Key.Key_End:
            self._move_active(10)
        else:
            super().keyPressEvent(event)
            return
        event.accept()


class HalfStarSpinBox(QDoubleSpinBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRange(0.5, 5)
        self.setDecimals(1)
        self.setSingleStep(0.5)
        self.setSuffix(" ★")
        self.setKeyboardTracking(False)
        self.setCorrectionMode(QAbstractSpinBox.CorrectionMode.CorrectToNearestValue)

    def valueFromText(self, text):
        return round(super().valueFromText(text) * 2) / 2


class RatingFilterPopup(QFrame):
    applied = Signal(float, float)
    cleared = Signal()

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setObjectName("ratingPanel")
        self.setAccessibleName("Rating filter")
        self.setAttribute(Qt.WidgetAttribute.WA_NoMouseReplay, True)
        self.setFixedWidth(320)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)
        title = QLabel("Rating range")
        title.setStyleSheet("font-size: 15px; font-weight: 600;")
        layout.addWidget(title)
        self.slider = RatingRangeSlider()
        layout.addWidget(self.slider)
        bounds = QHBoxLayout()
        bounds.setSpacing(14)
        self.minimum = HalfStarSpinBox()
        self.maximum = HalfStarSpinBox()
        for caption, control in (("Min", self.minimum), ("Max", self.maximum)):
            column = QVBoxLayout()
            column.setSpacing(5)
            label = QLabel(caption)
            label.setBuddy(control)
            secondary(label)
            control.setAccessibleName(f"{caption}imum rating")
            column.addWidget(label)
            column.addWidget(control)
            bounds.addLayout(column)
        layout.addLayout(bounds)
        hint = QLabel("Unrated albums aren’t included in a range.")
        hint.setWordWrap(True)
        secondary(hint, muted=True)
        layout.addWidget(hint)
        actions = QHBoxLayout()
        self.clear_button = QPushButton("Clear")
        self.apply_button = QPushButton("Apply")
        actions.addWidget(self.clear_button)
        actions.addStretch()
        actions.addWidget(self.apply_button)
        layout.addLayout(actions)
        self.slider.range_changed.connect(self._sync_controls)
        self.minimum.valueChanged.connect(self._minimum_changed)
        self.maximum.valueChanged.connect(self._maximum_changed)
        self.clear_button.clicked.connect(self.clear_filter)
        self.apply_button.clicked.connect(self.apply_filter)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self).activated.connect(self.hide)
        self._sync_controls(*self.slider.values)

    def _minimum_changed(self, value):
        self.slider.set_values(value, self.slider.values[1])
        self._sync_controls(*self.slider.values)

    def _maximum_changed(self, value):
        self.slider.set_values(self.slider.values[0], value)
        self._sync_controls(*self.slider.values)

    def _sync_controls(self, lower, upper):
        for control in (self.minimum, self.maximum):
            control.blockSignals(True)
        try:
            self.minimum.setRange(0.5, upper)
            self.minimum.setValue(lower)
            self.maximum.setRange(lower, 5)
            self.maximum.setValue(upper)
        finally:
            for control in (self.minimum, self.maximum):
                control.blockSignals(False)

    def open_for(self, anchor: QWidget, bounds: tuple[float, float] | None):
        self.slider.set_values(*(bounds or (0.5, 5)))
        self._sync_controls(*self.slider.values)
        self.adjustSize()
        area = anchor.screen().availableGeometry()
        below = anchor.mapToGlobal(QPoint(anchor.width(), anchor.height() + 8))
        x = max(area.left(), min(below.x() - self.width(), area.right() - self.width() + 1))
        y = below.y()
        if y + self.height() > area.bottom() + 1:
            y = anchor.mapToGlobal(QPoint(0, -8)).y() - self.height()
        y = max(area.top(), min(y, area.bottom() - self.height() + 1))
        self.move(x, y)
        self.show()
        self.minimum.setFocus(Qt.FocusReason.PopupFocusReason)
        self.minimum.selectAll()

    def apply_filter(self):
        self.minimum.interpretText()
        self.maximum.interpretText()
        bounds = self.slider.values
        self.hide()
        self.applied.emit(*bounds)

    def clear_filter(self):
        self.hide()
        self.cleared.emit()
