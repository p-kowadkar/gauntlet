from __future__ import annotations

import copy

import json
import os
from pathlib import Path
from typing import Any


CONFIG_FILE = Path.home() / ".gauntlet" / "config.json"
ENV_FILE = Path(__file__).parent.parent / ".env"
CONFIG_VERSION = 2


DEFAULT_ROLES: dict[str, dict[str, Any]] = {
    "primary_llm": {"provider": "baseten", "model": "zai-org/GLM-5", "effort": "medium"},
    "adversarial": {"provider": "baseten", "model": "zai-org/GLM-5", "effort": "medium"},
    "risk": {"provider": "baseten", "model": "zai-org/GLM-5", "effort": "medium"},
    "code_analysis": {"provider": "openai", "model": "gpt-5.4-mini", "effort": "medium"},
    "final_judge": {"provider": "openai", "model": "gpt-5.4-mini", "effort": "high"},
    "classifier": {"provider": "openrouter", "model": "openrouter/free", "effort": None},
    "vision": {"provider": "baseten", "model": "moonshotai/Kimi-K2.5", "effort": None},
    "tts": {"provider": "openai", "model": "tts-1", "voice": "nova"},
    "stt": {"provider": "google", "model": "chirp-3", "effort": None},
    "search": {"provider": "youcom"},
}


FALLBACK_CHAINS: dict[str, list[tuple[str, str | None]]] = {
    "primary_llm": [
        ("baseten", "zai-org/GLM-5"),
        ("openai", "gpt-5.4-mini"),
        ("anthropic", "claude-sonnet-4-6"),
        ("xai", "grok-4-1-fast-reasoning"),
        ("google", "gemini-3-flash-preview"),
        ("deepseek", "deepseek-v3.2"),
        ("openrouter", "openrouter/free"),
    ],
    "adversarial": [
        ("baseten", "zai-org/GLM-5"),
        ("openai", "gpt-5.4-mini"),
        ("openrouter", "openrouter/free"),
    ],
    "risk": [
        ("baseten", "zai-org/GLM-5"),
        ("openai", "gpt-5.4-mini"),
        ("openrouter", "openrouter/free"),
    ],
    "code_analysis": [
        ("openai", "gpt-5.4-mini"),
        ("baseten", "zai-org/GLM-5"),
        ("anthropic", "claude-sonnet-4-6"),
        ("google", "gemini-3-flash-preview"),
    ],
    "final_judge": [
        ("openai", "gpt-5.4-mini"),
        ("anthropic", "claude-opus-4-7"),
        ("google", "gemini-3.1-pro-preview"),
    ],
    "classifier": [
        ("openrouter", "openrouter/free"),
        ("google", "gemini-3.1-flash-lite-preview"),
        ("openai", "gpt-5.4-mini"),
        ("baseten", "zai-org/GLM-5"),
    ],
    "vision": [
        ("baseten", "moonshotai/Kimi-K2.5"),
        ("anthropic", "claude-opus-4-7"),
        ("google", "gemini-3.1-pro-preview"),
        ("openai", "gpt-5.4"),
    ],
    "tts": [
        ("xai", "grok-tts"),
        ("google", "gemini-3.1-flash-tts-preview"),
        ("openai", "tts-1"),
    ],
    "stt": [
        ("google", "chirp-3"),
        ("openai", "whisper-1"),
    ],
    "search": [
        ("firecrawl", None),
        ("youcom", None),
        ("brave", None),
    ],
}


class ModelConfig:
    def __init__(self, data: dict[str, Any]):
        self._data = data
        self._env = self._load_env()

    @classmethod
    def load(cls) -> "ModelConfig":
        if CONFIG_FILE.exists():
            try:
                raw = CONFIG_FILE.read_text(encoding="utf-8")
                data = json.loads(raw)
                if isinstance(data, dict):
                    version_raw = data.get("version", 1)
                    try:
                        version = int(version_raw)
                    except (TypeError, ValueError):
                        version = 1
                    if version < CONFIG_VERSION:
                        migrated = cls._migrate_to_v2(data)
                        cfg = cls(migrated)
                        cfg.save()
                        print(f"[ModelConfig] Migrated config schema to v{CONFIG_VERSION}: {CONFIG_FILE}")
                        return cfg
                    return cls(data)
            except Exception:
                pass
        return cls(cls._default_config_v2())

    def save(self) -> None:
        safe_data = json.loads(json.dumps(self._data))
        self._strip_api_keys_recursive(safe_data)
        assert not self._contains_api_key_fields(
            safe_data
        ), "Refusing to write config.json containing API key fields"
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(safe_data, indent=2), encoding="utf-8")
    @classmethod
    def _default_config_v2(cls) -> dict[str, Any]:
        output_dir = str(Path.home() / ".gauntlet")
        roles = copy.deepcopy(DEFAULT_ROLES)
        return {
            "version": CONFIG_VERSION,
            "output_dir": output_dir,
            "overlay": {"opacity": 0.92},
            "model_config": {
                "mode": "api",
                "roles": roles,
                "custom_providers": [],
            },
            "simulation": {
                "tier": "auto",
                "e2b_api_key_env": "E2B_API_KEY",
                "promptfoo_path": "npx promptfoo@latest",
                "veris_env_id": "",
                "veris_run_id": "",
            },
            # Back-compat fields consumed by current UI (Phase 3 will remove).
            "OUTPUT_DIR": output_dir,
            "OVERLAY_OPACITY": 0.92,
        }

    @classmethod
    def _migrate_to_v2(cls, data: dict[str, Any]) -> dict[str, Any]:
        migrated = cls._default_config_v2()

        output_dir = data.get("output_dir", data.get("OUTPUT_DIR", migrated["output_dir"]))
        if not isinstance(output_dir, str) or not output_dir.strip():
            output_dir = migrated["output_dir"]
        else:
            output_dir = output_dir.strip()
        migrated["output_dir"] = output_dir
        migrated["OUTPUT_DIR"] = output_dir

        overlay_opacity: float = 0.92
        overlay_obj = data.get("overlay", {})
        if isinstance(overlay_obj, dict) and "opacity" in overlay_obj:
            try:
                overlay_opacity = float(overlay_obj.get("opacity", 0.92))
            except (TypeError, ValueError):
                overlay_opacity = 0.92
        elif "OVERLAY_OPACITY" in data:
            try:
                overlay_opacity = float(data.get("OVERLAY_OPACITY", 0.92))
            except (TypeError, ValueError):
                overlay_opacity = 0.92
        overlay_opacity = max(0.0, min(1.0, overlay_opacity))
        migrated["overlay"] = {"opacity": overlay_opacity}
        migrated["OVERLAY_OPACITY"] = overlay_opacity

        model_config = data.get("model_config", {})
        if isinstance(model_config, dict):
            mode = str(model_config.get("mode", migrated["model_config"]["mode"])).strip().lower()
            migrated["model_config"]["mode"] = mode if mode else "api"

            custom_providers = model_config.get("custom_providers", [])
            if isinstance(custom_providers, list):
                migrated["model_config"]["custom_providers"] = custom_providers

            roles = model_config.get("roles", {})
            if isinstance(roles, dict):
                normalized_roles: dict[str, dict[str, Any]] = {}
                for role, default_cfg in DEFAULT_ROLES.items():
                    role_cfg = roles.get(role, {})
                    if not isinstance(role_cfg, dict):
                        role_cfg = {}
                    normalized_roles[role] = {**default_cfg, **role_cfg}
                migrated["model_config"]["roles"] = normalized_roles

        simulation = data.get("simulation", {})
        if isinstance(simulation, dict):
            tier = simulation.get("tier", migrated["simulation"]["tier"])
            promptfoo_path = simulation.get("promptfoo_path", migrated["simulation"]["promptfoo_path"])
            e2b_api_key_env = simulation.get("e2b_api_key_env", migrated["simulation"]["e2b_api_key_env"])
            veris_env_id = simulation.get("veris_env_id", migrated["simulation"]["veris_env_id"])
            veris_run_id = simulation.get("veris_run_id", migrated["simulation"]["veris_run_id"])

            migrated["simulation"] = {
                "tier": str(tier).strip() or "auto",
                "e2b_api_key_env": str(e2b_api_key_env).strip() or "E2B_API_KEY",
                "promptfoo_path": str(promptfoo_path).strip() or "npx promptfoo@latest",
                "veris_env_id": str(veris_env_id).strip(),
                "veris_run_id": str(veris_run_id).strip(),
            }

        # Preserve unrecognized keys for forward compatibility.
        known_top_level = {
            "version",
            "output_dir",
            "overlay",
            "model_config",
            "simulation",
            "OUTPUT_DIR",
            "OVERLAY_OPACITY",
        }
        for key, value in data.items():
            if key not in known_top_level and key not in migrated:
                migrated[key] = value

        migrated["version"] = CONFIG_VERSION
        return migrated

    def _strip_api_keys_recursive(self, value: Any) -> None:
        if isinstance(value, dict):
            to_delete = [k for k in value.keys() if "API_KEY" in str(k).upper()]
            for key in to_delete:
                del value[key]
            for v in value.values():
                self._strip_api_keys_recursive(v)
        elif isinstance(value, list):
            for item in value:
                self._strip_api_keys_recursive(item)

    def _contains_api_key_fields(self, value: Any) -> bool:
        if isinstance(value, dict):
            for k, v in value.items():
                if "API_KEY" in str(k).upper():
                    return True
                if self._contains_api_key_fields(v):
                    return True
            return False
        if isinstance(value, list):
            for item in value:
                if self._contains_api_key_fields(item):
                    return True
        return False

    def _load_env(self) -> dict[str, str]:
        env: dict[str, str] = {}
        if ENV_FILE.exists():
            for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()

        for k, v in os.environ.items():
            if k.endswith("_API_KEY") and v:
                env[k] = v
        return env

    def get_role_config(self, role: str) -> dict[str, Any]:
        roles = self._data.get("model_config", {}).get("roles", {})
        role_cfg = roles.get(role, {})
        default_cfg = DEFAULT_ROLES.get(role, {})
        if not isinstance(role_cfg, dict):
            role_cfg = {}
        return {**default_cfg, **role_cfg}

    def resolve(
        self,
        role: str,
        role_override: tuple[str, str] | None = None,
    ) -> tuple[str, str]:
        if role_override:
            p, m = role_override
            p = str(p).strip()
            m = str(m).strip()
            if not p or not m:
                raise ValueError("Invalid role override")
            if self.provider_available(p, m):
                return p, m
            raise RuntimeError(f"No API key configured for provider '{p}'")

        role_cfg = self.get_role_config(role)
        provider_id = str(role_cfg.get("provider", "openrouter")).strip()
        model_id = str(role_cfg.get("model", "openrouter/free")).strip()

        if self.provider_available(provider_id, model_id):
            return provider_id, model_id

        for fb_provider, fb_model in FALLBACK_CHAINS.get(role, []):
            if fb_model is None:
                continue
            if self.provider_available(fb_provider, fb_model):
                return fb_provider, fb_model

        return "openrouter", "openrouter/free"

    def provider_available(self, provider_id: str, model_id: str | None = None) -> bool:
        provider_id = provider_id.strip().lower()
        if provider_id in ("local_ollama", "local_lmstudio"):
            return True
        if provider_id == "openrouter" and (model_id == "openrouter/free" or not model_id):
            return True
        return bool(self.get_api_key(provider_id))

    def get_api_key(self, provider_id: str) -> str:
        key_map = {
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "google": "GOOGLE_API_KEY",
            "xai": "XAI_API_KEY",
            "deepseek": "DEEPSEEK_API_KEY",
            "openrouter": "OPENROUTER_API_KEY",
            "baseten": "BASETEN_API_KEY",
            "firecrawl": "FIRECRAWL_API_KEY",
            "youcom": "YOUCOM_API_KEY",
            "brave": "BRAVE_API_KEY",
            "exa": "EXA_API_KEY",
            "e2b": "E2B_API_KEY",
            "veris": "VERIS_API_KEY",
            "mistral": "MISTRAL_API_KEY",
        }
        env_key = key_map.get(provider_id, f"{provider_id.upper()}_API_KEY")
        return self._env.get(env_key, os.getenv(env_key, ""))

    def get_effort(self, provider_id: str) -> str | None:
        if provider_id in ("openai", "anthropic", "google", "xai", "deepseek"):
            return "medium"
        return None

    def get_custom_base_url(self, provider_id: str) -> str:
        customs = self._data.get("model_config", {}).get("custom_providers", [])
        if not isinstance(customs, list):
            return ""
        for c in customs:
            if not isinstance(c, dict):
                continue
            if c.get("id") == provider_id:
                return str(c.get("base_url", ""))
        return ""

    def get_mode(self) -> str:
        return str(self._data.get("model_config", {}).get("mode", "api"))

    def describe_active_roles(self) -> list[tuple[str, str, str]]:
        items: list[tuple[str, str, str]] = []
        for role in sorted(DEFAULT_ROLES.keys()):
            provider, model = self.resolve(role)
            items.append((role, provider, model))
        return items

