# PyInstaller onedir spec for the PySide6 native line. The official Qt hooks
# collect WebEngineProcess, resources and required platform plugins; a custom
# QtQml hook avoids copying unrelated QML modules. The release script performs
# a bounded runtime prune and a clean-directory graph smoke test.
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules


project_root = Path(SPECPATH).resolve().parents[1]
src_root = project_root / "src"
graph_root = src_root / "mshub" / "native" / "graph"
hook_root = Path(SPECPATH).resolve() / "hooks"

graph_datas = [
    # PyInstaller treats the second item as a destination directory.  Keep
    # the source-relative parent so assets/index.js is emitted as
    # mshub/native/graph/assets/index.js rather than assets/index.js/index.js.
    (str(path), str(Path("mshub/native/graph") / path.relative_to(graph_root).parent))
    for path in graph_root.rglob("*")
    if path.is_file()
]

datas = graph_datas + [(str(project_root / "README.md"), ".")]
# PyInstaller's official PySide6 hooks collect the exact Qt DLLs, WebEngine
# helper/resources and translations referenced by these imports.  Do not use
# collect_all("PySide6"): it drags in every QML module and every language pack
# and turns the onedir into a 700 MB unrelated SDK dump.
hiddenimports = (
    collect_submodules("PySide6.QtWebEngineCore")
    + collect_submodules("PySide6.QtWebEngineWidgets")
    + collect_submodules("PySide6.QtWebChannel")
)

a = Analysis(
    [str(src_root / "mshub" / "native" / "__main__.py")],
    pathex=[str(src_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[str(hook_root)],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["PyQt5", "PyQt6", "tkinter"],
    noarchive=False,
)
# Qt 6.11 uses Windows' ICU API (unversioned ucnv_* exports). Developer PATH
# may contain Poppler's incompatible ICU 78 (ucnv_*_78 exports). Never shadow
# the OS ICU with that same-named DLL. WebEngine's separate icudtl.dat stays.
a.binaries = [entry for entry in a.binaries if Path(entry[0]).name.lower()
              not in {"icuuc.dll", "icuin.dll", "icudt78.dll"}]
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    [],
    name="123mshub",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="123mshub",
)
