"""Verify final ZIP integrity, asset hashes, and frozen fix modules."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import types
import zipfile

from PyInstaller.archive.readers import CArchiveReader


def digest(path):
    return hashlib.file_digest(Path(path).open("rb"), "sha256").hexdigest()


def normalized(code):
    if not isinstance(code, types.CodeType):
        return code
    return code.replace(
        co_filename="", co_firstlineno=1, co_linetable=b"",
        co_consts=tuple(normalized(value) for value in code.co_consts),
    )


root = Path(__file__).resolve().parents[3]
bundle = root / "release/native-v1.11.1/123mshub"
exe = bundle / "123mshub.exe"
zip_path = root / "release/123mshub-native-v1.11.1-win64.zip"
archive = CArchiveReader(str(exe))
pyz = archive.open_embedded_archive("PYZ.pyz")
modules = {}
for module in (
    "mshub", "mshub.native.main_window", "mshub.native.shell_widgets",
    "mshub.native.navigation_symbols", "mshub.native.column_resize",
    "mshub.native.list_table", "mshub.native.ui", "mshub.native.ui_icons",
    "mshub.native.starfield", "mshub.native.graph_bridge", "mshub.native.job_controller",
    "mshub.native.theme", "mshub.native.i18n",
    "mshub.native.views.skill_view", "mshub.native.views.memory_view",
    "mshub.ui5",
):
    path = root / "src" / (module.replace(".", "/") + ".py")
    if not path.is_file():
        path = path.with_suffix("") / "__init__.py"
    frozen = pyz.extract(module)
    source = compile(path.read_bytes(), frozen.co_filename, "exec", dont_inherit=True)
    matches = normalized(frozen) == normalized(source)
    assert matches, module
    modules[module] = matches

asset_matches = {}
for asset in ("NEWmshublogo.ico", "new123uilogo.ico", "MATERIAL-SYMBOLS-LICENSE.txt"):
    source = root / "packaging/native/icons" / asset
    frozen = bundle / "_internal/mshub/native/icons" / asset
    asset_matches[asset] = digest(source) == digest(frozen)
    assert asset_matches[asset], asset
for source_name, bundle_name in (("src/mshub/native/design_tokens.json", "_internal/mshub/native/design_tokens.json"), ("src/mshub/ui5/tokens.json", "_internal/mshub/ui5/tokens.json")):
    source = root / source_name
    frozen = bundle / bundle_name
    asset_matches[bundle_name] = source.is_file() and frozen.is_file() and digest(source) == digest(frozen)
    assert asset_matches[bundle_name], bundle_name

graph_asset_matches = {}
graph_root = root / "src/mshub/native/graph"
frozen_graph_root = bundle / "_internal/mshub/native/graph"
graph_assets = ["index.html"] + [f"assets/{path.name}" for path in sorted((graph_root / "assets").glob("*.css"))] + [f"assets/{path.name}" for path in sorted((graph_root / "assets").glob("*.js"))]
for asset in graph_assets:
    source = graph_root / asset
    frozen = frozen_graph_root / asset
    graph_asset_matches[asset] = source.is_file() and frozen.is_file() and digest(source) == digest(frozen)
    assert graph_asset_matches[asset], asset

with zipfile.ZipFile(zip_path) as zipped:
    assert zipped.testzip() is None
    assert hashlib.sha256(zipped.read("123mshub/123mshub.exe")).hexdigest() == digest(exe)
    count = len(zipped.infolist())

evidence = {
    "version": "1.11.1", "ui5_version": "5.0.0", "frozen_modules_match_source": modules,
    "packaged_assets_match_source": asset_matches, "graph_assets_match_source": graph_asset_matches,
    "zip_crc": "pass",
    "zip_exe_matches_onedir": True, "zip_entries": count,
    "exe_sha256": digest(exe), "zip_sha256": digest(zip_path),
    "exe_bytes": exe.stat().st_size, "zip_bytes": zip_path.stat().st_size,
}
(Path(__file__).parent / "bundle-check.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
print(json.dumps(evidence, indent=2))




