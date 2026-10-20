"""Generated HAUI palettes and resources, consumed by the Qt presentation adapter.

Regenerate with scripts/native/sync-haui.mjs; runtime needs no HAUI checkout.
"""
from functools import lru_cache
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


@lru_cache(maxsize=1)
def catalog() -> dict:
    return json.loads((ROOT / "themes.json").read_text(encoding="utf-8"))


def resolve(palette: str = "nous", mode: str = "light", accent: str = "default") -> dict:
    themes = catalog()["themes"]
    theme = themes.get(palette, themes["nous"])
    variant = theme["variants"].get(accent, theme["variants"]["default"])
    return variant["dark" if mode == "dark" else "light"]


@lru_cache(maxsize=1)
def icons() -> dict[str, str]:
    return json.loads((ROOT / "icons.json").read_text(encoding="utf-8"))
