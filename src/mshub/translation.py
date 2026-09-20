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
) -> str:
    """调用 OpenAI 兼容网关把技能备注翻译为简体中文。"""
    if not text.strip():
        raise ValidationError("备注为空，没有可翻译的内容。")
    if not base_url or not api_key:
        raise ValidationError("翻译备注需要先在设置中填写 AI 网关地址与 Key。")
    prompt = (
        "把下面的 agent skill 备注翻译成简体中文。只输出译文本身，"
        "不要加引号、解释或前后缀；专有名词（产品名/命令/文件名）保留原文。\n\n"
        + text.strip()
    )
    endpoint = f"{base_url.rstrip('/')}/chat/completions"
    request_body: dict = {
        "temperature": 0,
        "messages": [{"role": "user", "content": prompt}],
    }
    if model:
        request_body["model"] = model
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        response = httpx.post(endpoint, headers=headers, json=request_body, timeout=timeout)
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPError as exc:
        raise ValidationError(f"翻译请求失败：{exc}") from exc
    except ValueError as exc:
        raise ValidationError("网关返回的内容不是有效 JSON。") from exc
    choices = data.get("choices") if isinstance(data, dict) else None
    content = ""
    if isinstance(choices, list) and choices:
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        if isinstance(message, dict):
            content = str(message.get("content") or "")
    content = content.strip().strip('"“”‘’').strip()
    if not content:
        raise ValidationError("网关没有返回翻译结果。")
    return content
