from __future__ import annotations

from typing import Any


AI_PROVIDER_PRESETS: list[dict[str, Any]] = [
    {
        "id": "openai",
        "name": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4.1-mini",
        "key_hint": "sk-…",
        "note": "OpenAI 官方 API。",
    },
    {
        "id": "deepseek",
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-v4-pro",
        "key_hint": "sk-…",
        "note": "DeepSeek 官方 OpenAI 兼容接口。",
    },
    {
        "id": "openrouter",
        "name": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "model": "~openai/gpt-latest",
        "key_hint": "sk-or-v1-…",
        "note": "一个 Key 可选择多个模型供应商。",
    },
    {
        "id": "siliconflow",
        "name": "硅基流动 SiliconFlow",
        "base_url": "https://api.siliconflow.cn/v1",
        "model": "Qwen/Qwen2.5-72B-Instruct",
        "key_hint": "sk-…",
        "note": "国内 OpenAI 兼容模型平台。",
    },
    {
        "id": "zhipu",
        "name": "智谱 BigModel",
        "base_url": "https://open.bigmodel.cn/api/paas/v4/",
        "model": "glm-5.2",
        "key_hint": "填写智谱 API Key",
        "note": "智谱 GLM OpenAI 兼容接口。",
    },
    {
        "id": "dashscope",
        "name": "阿里云百炼 DashScope",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen3.7-plus",
        "key_hint": "sk-… / sk-ws-…",
        "note": "如控制台提供业务空间专属地址，请用该地址覆盖此默认值。",
    },
]
