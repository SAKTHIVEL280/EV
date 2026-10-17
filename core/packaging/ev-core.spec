# PyInstaller spec for ev-core (docs/ARCHITECTURE.md §5.2, spike S2).
# onedir, not onefile: onefile unpacks to a temp folder on every launch, which
# is slow and often flagged by antivirus (CLAUDE.md §5.1).
# Console subsystem: the app spawns it with CREATE_NO_WINDOW and needs real
# stdin/stdout pipes for the handshake and parent-exit detection.
from PyInstaller.utils.hooks import collect_data_files, copy_metadata

a = Analysis(
    ["entry.py"],
    pathex=[".."],
    # Package data: the model catalog (ev_core/models/manifest.json).
    datas=copy_metadata("ev-core") + collect_data_files("ev_core", includes=["**/*.json"]),
    hiddenimports=[],
    excludes=["tkinter", "unittest", "pydoc", "test"],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ev-core",
    console=True,
    debug=False,
    strip=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="ev-core", strip=False, upx=False)
