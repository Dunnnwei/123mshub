"""Non-server adapter for the legacy /models and read-only proxy operations."""
import os
from urllib.parse import urlparse

import httpx

from ..errors import ValidationError


def validate_endpoint(base):
    parsed = urlparse(base)
    if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValidationError("接口地址必须是完整的 http(s) 地址，不能在地址中放入密钥。")
    return base.rstrip("/")


def list_models(base, key):
    endpoint = validate_endpoint(base) + "/models"
    headers = {"Accept": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    try:
        response = httpx.get(endpoint, headers=headers, timeout=15, follow_redirects=False)
        response.raise_for_status()
        data = response.json()
        items = data.get("data", []) if isinstance(data, dict) else data
        return sorted({str(item["id"]) for item in items if isinstance(item, dict) and item.get("id")})
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        raise ValidationError(f"模型列表获取失败（{type(exc).__name__}），可继续手动填写模型。") from exc


def test_connection(base, key, model):
    endpoint = validate_endpoint(base) + "/chat/completions"
    if not key or not model:
        raise ValidationError("请填写密钥和模型后再测试。")
    try:
        response = httpx.post(endpoint, headers={"Authorization": f"Bearer {key}"},
            json={"model": model, "messages": [{"role": "user", "content": "Reply OK."}],
                  "max_tokens": 16}, timeout=30, follow_redirects=False)
        response.raise_for_status()
        data = response.json()
        if not data.get("choices"):
            raise ValueError("missing choices")
        return "AI 连通成功：指定模型已返回响应；草稿设置尚未保存。"
    except (httpx.HTTPError, ValueError, TypeError, AttributeError) as exc:
        status = getattr(getattr(exc, "response", None), "status_code", "")
        raise ValidationError(f"AI 连通失败（{status or type(exc).__name__}），请检查地址、密钥和模型。") from exc


def detect_proxy(configured=""):
    candidates = [configured] if configured else []
    candidates += [os.environ.get(key, "").strip() for key in
        ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy")]
    valid = []
    for value in candidates:
        try:
            parsed = urlparse(value)
            if parsed.scheme in {"http", "https", "socks5", "socks5h"} and parsed.hostname and value not in valid:
                valid.append(value)
        except ValueError:
            continue
    return {"detected": valid[0] if valid else "", "candidates": valid}


def mask_secret(value):
    if not value:
        return "未配置"
    if len(value) <= 8:
        return "•" * len(value)
    return value[:4] + "…" + value[-4:]
