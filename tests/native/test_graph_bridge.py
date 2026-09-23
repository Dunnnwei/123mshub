from __future__ import annotations

import json

from mshub.native.graph_bridge import GraphBridge
from mshub.native.memory_facade import MemoryFacade


def test_graph_bridge_matches_service_graph_contract(native_facade: MemoryFacade) -> None:
    native_facade.create_entry({"name": "one", "title": "一", "tags": ["same"]})
    native_facade.create_entry({"name": "two", "title": "二", "tags": ["same"], "body": "[[one]]"})
    bridge = GraphBridge(native_facade, "dark")
    payload = json.loads(bridge.getGraph("link,tag"))
    assert {node["id"] for node in payload["nodes"]} == {"one", "two"}
    assert any(edge["kind"] == "双链" for edge in payload["edges"])
    assert any(edge["kind"] == "共同标签" for edge in payload["edges"])
    assert json.loads(bridge.getTheme())["theme"] == "dark"


def test_graph_bridge_rejects_invalid_settings(native_facade: MemoryFacade) -> None:
    bridge = GraphBridge(native_facade)
    assert bridge.writeGraphSettings("[]") is False
    assert bridge.writeGraphSettings("{\"nodeScale\": 1.2}") is True
    assert json.loads(bridge.readGraphSettings())["nodeScale"] == 1.2


def test_graph_bridge_accepts_worker_warm_cache(native_facade: MemoryFacade) -> None:
    bridge = GraphBridge(native_facade)
    bridge.set_graph_cache("link", {"nodes": [], "edges": [], "memory_root": ""})
    assert json.loads(bridge.getGraph("link"))["nodes"] == []
