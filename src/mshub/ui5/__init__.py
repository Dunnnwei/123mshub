"""Reusable 123ui5.0 design tokens for native and future consumers.

The module intentionally has no Qt or web-framework dependency.  Consumers
can read one semantic palette for either mode and keep Hermes Mono's layout,
state, motion and accessibility rules while applying the Indigo/Violet brand
seeds.
"""

from __future__ import annotations

import copy
import json
from functools import lru_cache
from pathlib import Path

UI5_VERSION = "5.0.0"
TOKEN_PATH = Path(__file__).with_name("tokens.json")


@lru_cache(maxsize=1)
def _read_tokens() -> dict:
    data = json.loads(TOKEN_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not data.get("light") or not data.get("dark"):
        raise ValueError("123ui5.0 tokens.json 不完整")
    return data


def load_tokens() -> dict:
    """Return a deep copy of the complete 123ui5.0 token document."""

    return copy.deepcopy(_read_tokens())


def theme_tokens(mode: str = "light") -> dict:
    """Return the semantic palette for ``light`` or ``dark`` mode."""

    value = "dark" if str(mode).lower() == "dark" else "light"
    return copy.deepcopy(_read_tokens()[value])


def action_gradient(mode: str = "light") -> str:
    """Return a CSS/QSS-compatible directional brand gradient string."""

    token = theme_tokens(mode)
    return f"linear-gradient(135deg, {token['action_gradient_start']}, {token['action_gradient_end']})"


def css_variables(mode: str = "light") -> dict[str, str]:
    """Return semantic tokens as CSS custom-property-ready values."""

    return {f"--ui5-{key.replace('_', '-')}": str(value) for key, value in theme_tokens(mode).items()}


__all__ = [
    "UI5_VERSION",
    "TOKEN_PATH",
    "load_tokens",
    "theme_tokens",
    "action_gradient",
    "css_variables",
]
