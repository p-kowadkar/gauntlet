from __future__ import annotations

from typing import Any


PROVIDER_REGISTRY: dict[str, dict[str, Any]] = {
    "openai": {
        "display": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "sdk": "openai_compatible",
        "families": {
            "gpt-4o": {
                "models": ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini"],
                "reasoning": False,
                "temperature": True,
                "param": "max_tokens",
                "vision": True,
                "json_mode": True,
            },
            "o-series": {
                "models": ["o3", "o3-mini", "o4-mini"],
                "reasoning": True,
                "effort": ["low", "medium", "high"],
                "temperature": False,
                "param": "max_completion_tokens",
                "vision": False,
                "json_mode": True,
            },
            "gpt-5": {
                "models": ["gpt-5.4", "gpt-5.4-mini", "gpt-5.4-pro"],
                "reasoning": True,
                "effort": ["none", "low", "medium", "high", "xhigh"],
                "temperature": False,
                "param": "max_completion_tokens",
                "vision": True,
                "json_mode": True,
            },
        },
        "tts": ["tts-1", "tts-1-hd"],
        "default": "gpt-5.4-mini",
    },
    "anthropic": {
        "display": "Anthropic",
        "base_url": "https://api.anthropic.com",
        "sdk": "anthropic_native",
        "models": {
            "claude-opus-4-7": {
                "thinking_mode": "adaptive",
                "effort": ["low", "medium", "high", "xhigh", "max"],
                "vision": True,
                "json_mode": False,
                "drop_temperature": True,
            },
            "claude-opus-4-6": {
                "thinking_mode": "enabled",
                "effort": ["low", "medium", "high", "xhigh", "max"],
                "vision": True,
                "json_mode": False,
            },
            "claude-opus-4-5": {
                "thinking_mode": "enabled",
                "effort": ["low", "medium", "high"],
                "vision": True,
                "json_mode": False,
            },
            "claude-sonnet-4-6": {
                "thinking_mode": "enabled",
                "effort": ["low", "medium", "high", "max"],
                "vision": True,
                "json_mode": False,
            },
            "claude-haiku-4-5": {
                "thinking_mode": "disabled",
                "vision": True,
                "json_mode": False,
            },
        },
        "default": "claude-sonnet-4-6",
    },
    "google": {
        "display": "Google",
        "base_url": "https://generativelanguage.googleapis.com",
        "sdk": "google_native",
        "models": {
            "gemini-3.1-pro-preview": {
                "thinking_level": True,
                "risky_temperature": True,
                "vision": True,
                "json_mode": True,
            },
            "gemini-3-flash-preview": {
                "thinking_level": True,
                "vision": True,
                "json_mode": True,
            },
            "gemini-3.1-flash-lite-preview": {
                "thinking_level": True,
                "fast": True,
                "vision": True,
                "json_mode": True,
            },
        },
        "tts": ["gemini-3.1-flash-tts-preview"],
        "stt": ["chirp-3"],
        "default": "gemini-3-flash-preview",
    },
    "xai": {
        "display": "xAI / Grok",
        "base_url": "https://api.x.ai/v1",
        "sdk": "openai_compatible",
        "models": {
            "grok-4-1-fast-reasoning": {
                "reasoning_style": "variant",
                "vision": True,
                "json_mode": True,
                "context": "2M",
            },
            "grok-4-1-fast-non-reasoning": {
                "reasoning_style": "none",
                "vision": True,
                "json_mode": True,
                "context": "2M",
                "fast": True,
            },
            "grok-4.20-reasoning": {
                "reasoning_style": "variant",
                "vision": True,
                "json_mode": True,
                "context": "2M",
            },
            "grok-4.20-non-reasoning": {
                "reasoning_style": "none",
                "vision": True,
                "json_mode": True,
                "context": "2M",
            },
            "grok-3-mini": {
                "reasoning_style": "effort_kw",
                "effort": ["low", "high"],
                "vision": False,
                "json_mode": True,
            },
            "grok-3": {
                "reasoning_style": "none",
                "vision": False,
                "json_mode": True,
            },
        },
        "tts": {
            "model": "grok-tts",
            "price_per_1m_chars": 4.20,
            "voices": ["Ara", "Eve", "Leo", "Rex", "Sal"],
        },
        "stt": {"available": True, "languages": 25},
        "default": "grok-4-1-fast-reasoning",
    },
    "deepseek": {
        "display": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "sdk": "openai_compatible",
        "models": {
            "deepseek-v3.2": {
                "reasoning": False,
                "temperature": True,
                "vision": False,
                "json_mode": True,
            },
            "deepseek-r1": {
                "reasoning": True,
                "temperature": False,
                "vision": False,
                "json_mode": True,
            },
            "deepseek-coder-v3": {
                "reasoning": False,
                "temperature": True,
                "vision": False,
                "json_mode": True,
            },
        },
        "default": "deepseek-v3.2",
    },
    "openrouter": {
        "display": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "sdk": "openai_compatible",
        "model_defaults": {"vision": False, "json_mode": False},
        "free_models": [
            "openrouter/free",
            "google/gemma-3-27b:free",
            "nvidia/nemotron-3-super:free",
            "meta-llama/llama-3.3-70b:free",
            "deepseek/r1:free",
        ],
        "default": "openrouter/free",
    },
    "baseten": {
        "display": "Baseten",
        "base_url": "https://inference.baseten.co/v1",
        "sdk": "openai_compatible",
        "models": {
            "zai-org/GLM-5": {"vision": False, "json_mode": True},
            "moonshotai/Kimi-K2.5": {"vision": True, "json_mode": True},
        },
        "default": "zai-org/GLM-5",
    },
    "local_ollama": {
        "display": "Ollama (Local)",
        "base_url": "http://localhost:11434/v1",
        "sdk": "openai_compatible",
        "discovery": "http://localhost:11434/api/tags",
        "auto_detect": True,
        "default": None,
    },
    "local_lmstudio": {
        "display": "LM Studio (Local)",
        "base_url": "http://localhost:1234/v1",
        "sdk": "openai_compatible",
        "discovery": "http://localhost:1234/v1/models",
        "auto_detect": True,
        "default": None,
    },
}


def _model_meta(provider_id: str, model_id: str) -> dict[str, Any]:
    provider = PROVIDER_REGISTRY.get(provider_id, {})
    defaults = provider.get("model_defaults", {})

    for family in provider.get("families", {}).values():
        if model_id in family.get("models", []):
            return {**defaults, **{k: v for k, v in family.items() if k != "models"}}

    model = provider.get("models", {}).get(model_id)
    if model is not None:
        return {**defaults, **model}
    return dict(defaults)


def is_reasoning(provider_id: str, model_id: str) -> bool:
    sdk = PROVIDER_REGISTRY.get(provider_id, {}).get("sdk")
    if sdk in ("anthropic_native", "google_native"):
        return False
    return bool(_model_meta(provider_id, model_id).get("reasoning", False))


def supports_temperature(provider_id: str, model_id: str) -> bool:
    meta = _model_meta(provider_id, model_id)
    if meta.get("drop_temperature"):
        return False
    return bool(meta.get("temperature", True))


def get_effort_options(provider_id: str, model_id: str) -> list[str]:
    return list(_model_meta(provider_id, model_id).get("effort", []))


def supports_xhigh(provider_id: str, model_id: str) -> bool:
    return "xhigh" in get_effort_options(provider_id, model_id)


def supports_vision(provider_id: str, model_id: str) -> bool:
    return bool(_model_meta(provider_id, model_id).get("vision", False))


def supports_json_mode(provider_id: str, model_id: str) -> bool:
    return bool(_model_meta(provider_id, model_id).get("json_mode", False))


def get_thinking_mode(provider_id: str, model_id: str) -> str:
    if PROVIDER_REGISTRY.get(provider_id, {}).get("sdk") != "anthropic_native":
        return "disabled"
    return str(_model_meta(provider_id, model_id).get("thinking_mode", "disabled"))


def get_reasoning_style(provider_id: str, model_id: str) -> str:
    if provider_id != "xai":
        return "none"
    return str(_model_meta(provider_id, model_id).get("reasoning_style", "none"))


def get_sdk(provider_id: str) -> str:
    return str(PROVIDER_REGISTRY.get(provider_id, {}).get("sdk", "openai_compatible"))


def get_base_url(provider_id: str) -> str:
    return str(PROVIDER_REGISTRY.get(provider_id, {}).get("base_url", ""))

