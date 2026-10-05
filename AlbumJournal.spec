import sys

from PyInstaller.utils.hooks import collect_data_files

a = Analysis(
    ["packaging/launch.py"],
    pathex=["."],
    binaries=[],
    datas=collect_data_files("ytmusicapi") + [("album_journal/assets/app-icon.png", "album_journal/assets")],
    hiddenimports=["ytmusicapi"],
    hookspath=[],
    runtime_hooks=[],
    excludes=["PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtQml"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name="AlbumJournal",
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False, console=False,
    icon="packaging/AlbumJournal.icns" if sys.platform == "darwin" else None,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="AlbumJournal")
if sys.platform == "darwin":
    app = BUNDLE(
        coll, name="Album Journal.app", bundle_identifier="local.albumjournal.desktop",
        icon="packaging/AlbumJournal.icns",
        info_plist={"NSHighResolutionCapable": True, "NSRequiresAquaSystemAppearance": False},
    )
