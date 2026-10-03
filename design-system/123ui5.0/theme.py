"""Standalone 123ui5.0 token helper for Python consumers."""

from __future__ import annotations

import copy
import json
from functools import lru_cache
from pathlib import Path

UI5_VERSION = "5.0.0"
TOKEN_PATH = Path(__file__).with_name("tokens.json")


@lru_cache(maxsize=1)
def _read() -> dict:
    value = json.loads(TOKEN_PATH.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not value.get("light") or not value.get("dark"):
        raise ValueError("123ui5.0 token source is incomplete")
    return value


def theme_tokens(mode: str = "light") -> dict:
    return copy.deepcopy(_read()["dark" if str(mode).lower() == "dark" else "light"])


def action_gradient(mode: str = "light") -> str:
    token = theme_tokens(mode)
    return f"linear-gradient(135deg, {token['action_gradient_start']}, {token['action_gradient_end']})"
