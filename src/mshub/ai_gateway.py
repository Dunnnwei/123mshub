"""v1.8.0（审查 P2-1）：OpenAI 兼容 chat/completions 的统一网关。

五处手写的「拼 endpoint → 拼 messages → httpx.post → raise_for_status →
摘 choices[0].message.content → 剥围栏」收敛到这里；两份逐字重复的
_strip_fence 也归一为 strip_fence。错误统一为 ValidationError + 可读文案。

settings_service.test_connection 是连通探测（max_tokens=16、禁重定向、
错误带状态码），行为差异大，保留独立实现不并入。
"""
from __future__ import annotations

import re
from typing import Any

import httpx

from .errors import ValidationError


def strip_fence(value: str) -> str:
    """剥掉模型常见的 ``` 代码围栏（语言标记可有可无）。"""
    value = value.strip()
    value = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", value)
    value = re.sub(r"\s*```$", "", value)
    return value.strip()


def extract_content(data: Any, *, label: str = "AI 请求") -> str:
    """从 chat/completions 响应里取 choices[0].message.content（防御式）。"""
    choices = data.get("choices") if isinstance(data, dict) else None
    message = None
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        message = choices[0].get("message")
    content = str(message.get("content") or "").strip() if isinstance(message, dict) else ""
    if not content:
        raise ValidationError(f"{label}失败：网关没有返回内容。")
    return content


def chat_completion(
    base_url: str,
    api_key: str,
    model: str,
    prompt: str,
    *,
    temperature: float = 0,
    timeout: float = 60,
    json_mode: bool = False,
    label: str = "AI 请求",
    extra_body: dict[str, Any] | None = None,
) -> str:
    """发送一次 user-only 对话，返回 message.content 原文（已 strip）。

    json_mode 请求 response_format=json_object；部分兼容网关不支持会回 400，
    自动去掉该字段重试一次（沿用 scanner 的既有降级行为）。
    """
    if not api_key:
        raise ValidationError(f"{label}失败：未配置 AI 密钥。")
    endpoint = base_url.rstrip("/") + "/chat/completions"
    body: dict[str, Any] = {"temperature": temperature, "messages": [{"role": "user", "content": prompt}]}
    if model:
        body["model"] = model
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    if extra_body:
        body.update(extra_body)
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        response = httpx.post(endpoint, headers=headers, json=body, timeout=timeout)
        if json_mode and response.status_code == 400:
            body.pop("response_format", None)
            response = httpx.post(endpoint, headers=headers, json=body, timeout=timeout)
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPError as exc:
        raise ValidationError(f"{label}失败：{exc}") from exc
    except ValueError as exc:
        raise ValidationError(f"{label}失败：网关返回的内容不是有效 JSON。") from exc
    return extract_content(data, label=label)
