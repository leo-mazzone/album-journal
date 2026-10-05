"""Always-dark appearance, with macOS-native controls when available."""

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication, QStyleFactory


def configure_style(app: QApplication) -> None:
    app.styleHints().setColorScheme(Qt.ColorScheme.Dark)
    native_mac = (
        sys.platform == "darwin"
        and app.platformName() == "cocoa"
        and "macos" in {key.casefold() for key in QStyleFactory.keys()}
    )
    app.setStyle("macOS" if native_mac else "Fusion")
    app.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont))
    palette = QPalette()
    colors = {
        QPalette.ColorRole.Window: "#1c1c1e",
        QPalette.ColorRole.WindowText: "#f5f5f7",
        QPalette.ColorRole.Base: "#232325",
        QPalette.ColorRole.AlternateBase: "#2c2c2e",
        QPalette.ColorRole.Text: "#f5f5f7",
        QPalette.ColorRole.Button: "#343436",
        QPalette.ColorRole.ButtonText: "#f5f5f7",
        QPalette.ColorRole.Highlight: "#0a84ff",
        QPalette.ColorRole.HighlightedText: "#ffffff",
        QPalette.ColorRole.PlaceholderText: "#98989f",
        QPalette.ColorRole.ToolTipBase: "#343436",
        QPalette.ColorRole.ToolTipText: "#f5f5f7",
        QPalette.ColorRole.Light: "#454548",
        QPalette.ColorRole.Midlight: "#3a3a3c",
        QPalette.ColorRole.Mid: "#303032",
        QPalette.ColorRole.Dark: "#141416",
        QPalette.ColorRole.Shadow: "#000000",
        QPalette.ColorRole.Link: "#64aaff",
        QPalette.ColorRole.LinkVisited: "#b599ff",
        QPalette.ColorRole.Accent: "#0a84ff",
    }
    for role, color in colors.items():
        palette.setColor(role, QColor(color))
    for role in (
        QPalette.ColorRole.Text,
        QPalette.ColorRole.ButtonText,
        QPalette.ColorRole.WindowText,
    ):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor("#77777d"))
    app.setPalette(palette)
    # Leave native buttons, popup menus, calendars and combo arrows to the macOS style.
    stylesheet = """
        QToolBar { border: none; background: #242426; spacing: 8px; padding: 8px 20px; }
        QWidget#libraryHeader { background: transparent; }
        QWidget#libraryBody { background: #1c1c1e; }
        QLabel#libraryTitle { font-size: 23px; font-weight: 600; }
        QLabel[secondary="true"] { color: #a1a1a9; }
        QLabel[muted="true"] { color: #898991; }
        QListWidget#albumGrid { background: transparent; border: none; outline: none; }
        QScrollArea { background: transparent; border: none; }
        QScrollArea > QWidget > QWidget { background: #1c1c1e; }
        QLineEdit#albumSearch, QTextEdit {
            background: #2c2c2e; color: #f5f5f7;
            border: 1px solid #3a3a3e; border-radius: 9px; padding: 9px 12px;
            selection-background-color: #0a84ff; selection-color: white;
        }
        QLineEdit#albumSearch:focus, QTextEdit:focus { border-color: #0a84ff; }
        QToolButton#quietButton {
            border: none; border-radius: 7px; background: transparent; padding: 6px 9px;
            color: #c7c7ce; font-size: 20px;
        }
        QToolButton#quietButton:hover { background: #37373c; color: white; }
        QToolButton#quietButton:pressed { background: #45454b; }
        QToolButton#quietButton::menu-indicator { image: none; width: 0px; height: 0px; }
        QPushButton#sourceLink { color: #64aaff; border: none; padding: 0; text-align: left; }
        QPushButton#sourceLink:hover { color: #a6ccff; }
        QFrame#ratingPanel { background: #29292c; border: 1px solid #48484e; border-radius: 12px; }
        QToolButton#ratingFilter {
            color: #d3d3da; background: #343436; border: 1px solid #48484e;
            border-radius: 7px; padding: 7px 12px;
        }
        QToolButton#ratingFilter:hover { background: #424248; }
        QToolButton#ratingFilter[active="true"] { color: #88bfff; background: #20334d; border-color: #39597f; }
    """
    if not native_mac:
        stylesheet += """
            QLineEdit, QComboBox, QDateEdit {
                background: #2c2c2e; color: #f5f5f7; border: 1px solid #45454b;
                border-radius: 7px; padding: 6px 9px;
            }
            QPushButton {
                background: #3a3a3e; color: #f5f5f7; border: 1px solid #4b4b52;
                border-radius: 7px; padding: 7px 13px;
            }
            QPushButton:hover { background: #47474e; }
            QPushButton:pressed { background: #303035; }
            QPushButton:disabled { color: #77777d; background: #29292c; border-color: #353539; }
            QComboBox QAbstractItemView { background: #2c2c2e; color: #f5f5f7; }
            QMenu { background: #29292c; color: #f5f5f7; border: 1px solid #45454b; padding: 5px; }
            QMenu::item { padding: 6px 18px; border-radius: 4px; }
            QMenu::item:selected { background: #0a84ff; }
        """
    app.setStyleSheet(stylesheet)


def secondary(label, *, muted=False):
    label.setProperty("muted" if muted else "secondary", True)


def quiet_button(button):
    button.setObjectName("quietButton")
    button.setAutoRaise(True)
