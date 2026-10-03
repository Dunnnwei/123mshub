"""123ui5.0 source, runtime imports and semantic palette contracts."""

from __future__ import annotations

import json
from pathlib import Path

from mshub.ui5 import UI5_VERSION, action_gradient, css_variables, theme_tokens
from mshub.native.theme import PALETTES


ROOT = Path(__file__).resolve().parents[2]


def test_ui5_version_and_brand_seeds_are_single_source() -> None:
    assert UI5_VERSION == "5.0.0"
    source = json.loads((ROOT / "src/mshub/ui5/tokens.json").read_text(encoding="utf-8"))
    mirror = json.loads((ROOT / "src/mshub/native/design_tokens.json").read_text(encoding="utf-8"))
    assert source == mirror
    assert source["meta"]["seed"] == {"indigo": "#6366F1", "violet": "#7C3AED"}
    assert source["light"]["action_gradient_start"] == "#6366F1"
    assert source["light"]["action_gradient_end"] == "#7C3AED"


def test_ui5_runtime_palette_is_shared_by_native_and_direct_consumers() -> None:
    for mode in ("light", "dark"):
        token = theme_tokens(mode)
        assert token["action"] == "#6366F1"
        assert token["action_gradient_start"] == "#6366F1"
        assert token["action_gradient_end"] == "#7C3AED"
        assert PALETTES[mode] == token
        assert "#6366F1" in action_gradient(mode)
        assert "#7C3AED" in action_gradient(mode)
        assert css_variables(mode)["--ui5-action"] == "#6366F1"
