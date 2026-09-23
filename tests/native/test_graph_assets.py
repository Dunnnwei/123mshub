from __future__ import annotations

from pathlib import Path

from mshub.native.views.graph_view import GraphView


def test_graph_island_is_local_and_has_bridge(native_facade) -> None:
    index = GraphView.graph_asset_path()
    assert index.is_file()
    root = index.parent
    html = index.read_text(encoding="utf-8")
    assert "qrc:///qtwebchannel/qwebchannel.js" in html
    assert "http://" not in html and "https://" not in html
    js_files = list(root.rglob("*.js"))
    assert js_files
    combined = "\n".join(path.read_text(encoding="utf-8") for path in js_files)
    assert "getGraph" in combined
    assert "openMemory" in combined
    assert all("http://" not in path.read_text(encoding="utf-8") and "https://" not in path.read_text(encoding="utf-8") for path in root.rglob("*.*") if path.is_file())
