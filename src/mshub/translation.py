from __future__ import annotations

import re

import httpx

from .errors import ValidationError

_CJK_RANGES = re.compile(r"[\u3000-\u303f\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


def is_mostly_chinese(text: str) -> bool:
    """判断文本是否已经是中文（CJK 字符占比过半即认定，无需再翻译）。"""
    if not text:
        return False
    letters = [char for char in text if not char.isspace()]
    if not letters:
        return False
    cjk = [char for char in letters if _CJK_RANGES.match(char)]
    return len(cjk) >= max(2, int(len(letters) * 0.3))


def translate_description(
    text: str,
    *,
    base_url: str,
    api_key: str,
    model: str = "",
    timeout: float = 60,
    target: str = "zh",
) -> str:
    """调用 OpenAI 兼容网关翻译技能备注；target=zh 译为简体中文，target=en 译为英文。"""
    if not text.strip():
        raise ValidationError("备注为空，没有可翻译的内容。")
    if not base_url or not api_key:
        raise ValidationError("翻译备注需要先在设置中填写 AI 网关地址与 Key。")
    if target == "en":
        prompt = (
            "Translate the following agent skill note into concise English. "
            "Only output the translation itself, without quotes, explanations "
            "or prefixes; keep proper nouns (product names/commands/file names) as-is.\n\n"
            + text.strip()
        )
    else:
        prompt = (
            "把下面的 agent skill 备注翻译成简体中文。只输出译文本身，"
            "不要加引号、解释或前后缀；专有名词（产品名/命令/文件名）保留原文。\n\n"
            + text.strip()
        )
    # v1.8.0（审查 P2-1）：AI HTTP 调用收敛到 ai_gateway
    from .ai_gateway import chat_completion

    content = chat_completion(base_url, api_key, model, prompt, timeout=timeout, label="翻译请求")
    return content.strip().strip('"“”‘’').strip()
