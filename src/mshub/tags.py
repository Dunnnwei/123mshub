from __future__ import annotations

import unicodedata
from collections.abc import Iterable

from .errors import ValidationError


MAX_TAGS = 12
MAX_TAG_LENGTH = 24


def normalize_tags(values: Iterable[str] | None) -> list[str]:
    """Return clean, stable tags suitable for storage and filtering."""
    if values is None:
        return []

    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            raise ValidationError("标签必须是文本。")
        tag = " ".join(value.strip().removeprefix("#").strip().split())
        if not tag:
            continue
        if len(tag) > MAX_TAG_LENGTH:
            raise ValidationError(f"单个标签不能超过 {MAX_TAG_LENGTH} 个字符：{tag[:12]}…")
        if any(unicodedata.category(character).startswith("C") for character in tag):
            raise ValidationError("标签不能包含控制字符。")
        key = tag.casefold()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(tag)
        if len(normalized) > MAX_TAGS:
            raise ValidationError(f"每个技能最多设置 {MAX_TAGS} 个标签。")
    return normalized
