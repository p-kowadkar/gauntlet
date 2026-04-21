from __future__ import annotations

from typing import Any, Generator

from core.model_config import ModelConfig
from core.model_database import (
    PROVIDER_REGISTRY,
    get_base_url,
    get_effort_options,
    get_reasoning_style,
    get_sdk,
    get_thinking_mode,
    is_reasoning,
    supports_json_mode,
    supports_temperature,
    supports_vision,
)


class ModelRouter:
    """
    Universal LLM router used by all agents.
    """

    def __init__(self, config: ModelConfig | None = None):
        self.config = config or ModelConfig.load()
        self._clients: dict[str, Any] = {}

    def chat(
        self,
        role: str,
        messages: list[dict],
        max_tokens: int = 1000,
        json_mode: bool = False,
        vision: bool = False,
        stream: bool = False,
        effort: str | None = None,
        role_override: tuple[str, str] | None = None,
    ) -> tuple[str, str]:
        provider_id, model_id = self.config.resolve(role, role_override=role_override)
        sdk = get_sdk(provider_id)

        if sdk == "anthropic_native":
            return self._call_anthropic(
                provider_id=provider_id,
                model_id=model_id,
                messages=messages,
                max_tokens=max_tokens,
                stream=stream,
                effort=effort,
            )
        if sdk == "google_native":
            return self._call_google(
                provider_id=provider_id,
                model_id=model_id,
                messages=messages,
                max_tokens=max_tokens,
                json_mode=json_mode,
                stream=stream,
                effort=effort,
            )
        return self._call_openai_compatible(
            provider_id=provider_id,
            model_id=model_id,
            messages=messages,
            max_tokens=max_tokens,
            json_mode=json_mode,
            vision=vision,
            stream=stream,
            effort=effort,
        )

    def _call_openai_compatible(
        self,
        provider_id: str,
        model_id: str,
        messages: list[dict],
        max_tokens: int,
        json_mode: bool,
        vision: bool,
        stream: bool,
        effort: str | None,
    ) -> tuple[str, str]:
        client = self._get_openai_client(provider_id)

        if vision and not supports_vision(provider_id, model_id):
            raise RuntimeError(
                f"Model '{provider_id}/{model_id}' does not support vision inputs."
            )

        kwargs = self._build_openai_kwargs(
            provider_id=provider_id,
            model_id=model_id,
            messages=messages,
            max_tokens=max_tokens,
            json_mode=json_mode,
            effort=effort,
        )

        if stream:
            kwargs["stream"] = True
            chunks: list[str] = []
            try:
                resp = client.chat.completions.create(**kwargs)
            except Exception as e:
                msg = str(e).lower()
                if "unexpected keyword argument 'reasoning'" in msg and "reasoning" in kwargs:
                    retry = dict(kwargs)
                    retry.pop("reasoning", None)
                    resp = client.chat.completions.create(**retry)
                else:
                    raise
            for chunk in resp:
                choices = getattr(chunk, "choices", None) or []
                if not choices:
                    continue
                delta_obj = getattr(choices[0], "delta", None)
                delta = getattr(delta_obj, "content", None) or ""
                if delta:
                    chunks.append(delta)
            return "".join(chunks), model_id

        resp = self._retry_openai_on_token_limit(
            client=client,
            kwargs=kwargs,
            is_reasoning_model=is_reasoning(provider_id, model_id),
        )
        content = resp.choices[0].message.content or ""
        return content, model_id

    def _get_openai_client(self, provider_id: str):
        if provider_id in self._clients:
            return self._clients[provider_id]

        import openai

        key = self.config.get_api_key(provider_id)
        base_url = get_base_url(provider_id)
        if provider_id.startswith("custom_"):
            base_url = self.config.get_custom_base_url(provider_id)

        if not key and provider_id in ("local_ollama", "local_lmstudio", "openrouter"):
            key = "not-needed"
        if not key and not base_url:
            raise RuntimeError(f"Missing API key for provider '{provider_id}'")

        client = (
            openai.OpenAI(api_key=key, base_url=base_url)
            if base_url
            else openai.OpenAI(api_key=key)
        )
        self._clients[provider_id] = client
        return client

    def _call_anthropic(
        self,
        provider_id: str,
        model_id: str,
        messages: list[dict],
        max_tokens: int,
        stream: bool,
        effort: str | None,
    ) -> tuple[str, str]:
        import anthropic

        key = self.config.get_api_key("anthropic")
        if not key:
            raise RuntimeError("Missing ANTHROPIC_API_KEY")
        client = anthropic.Anthropic(api_key=key)

        system = ""
        anthro_messages: list[dict] = []
        for m in messages:
            role = str(m.get("role", "user"))
            content = m.get("content", "")
            if role == "system":
                system = str(content)
                continue
            anthro_messages.append(
                {
                    "role": role if role in ("assistant", "user") else "user",
                    "content": self._to_anthropic_content(content),
                }
            )

        kwargs: dict[str, Any] = {
            "model": model_id,
            "max_tokens": max_tokens,
            "messages": anthro_messages,
        }
        if system:
            kwargs["system"] = system

        mode = get_thinking_mode(provider_id, model_id)
        if mode == "adaptive":
            kwargs["thinking"] = {"type": "adaptive"}
            if effort and effort != "none":
                kwargs["output_config"] = {"effort": effort}
        elif mode == "enabled" and effort and effort != "none":
            budget_map = {"low": 1024, "medium": 4096, "high": 8192, "xhigh": 16000, "max": 32000}
            kwargs["thinking"] = {
                "type": "enabled",
                "budget_tokens": budget_map.get(effort, 4096),
            }

        if stream:
            chunks: list[str] = []
            with client.messages.stream(**kwargs) as s:
                for text in s.text_stream:
                    chunks.append(text)
            return "".join(chunks), model_id

        resp = self._retry_anthropic(client, kwargs)
        content_blocks = getattr(resp, "content", []) or []
        text_blocks = [b.text for b in content_blocks if getattr(b, "type", "") == "text"]
        if text_blocks:
            return "\n".join(text_blocks), model_id
        return "", model_id

    def _to_anthropic_content(self, content: Any) -> Any:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            blocks: list[dict[str, Any]] = []
            for part in content:
                if not isinstance(part, dict):
                    continue
                part_type = part.get("type")
                if part_type == "text":
                    blocks.append({"type": "text", "text": str(part.get("text", ""))})
                elif part_type == "image_url":
                    image_obj = part.get("image_url", {})
                    url = image_obj.get("url", "") if isinstance(image_obj, dict) else ""
                    if isinstance(url, str) and url.startswith("data:") and ";base64," in url:
                        prefix, b64_data = url.split(",", 1)
                        media_type = "image/png"
                        if ":" in prefix and ";" in prefix:
                            media_type = prefix.split(":", 1)[1].split(";", 1)[0]
                        blocks.append(
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": b64_data,
                                },
                            }
                        )
                    else:
                        blocks.append({"type": "text", "text": f"[image omitted] {url}"})
            if blocks:
                return blocks
        return str(content)

    def _retry_anthropic(self, client: Any, kwargs: dict[str, Any]):
        import anthropic

        try:
            return client.messages.create(**kwargs)
        except anthropic.OverloadedError:
            return client.messages.create(**kwargs)

    def _call_google(
        self,
        provider_id: str,
        model_id: str,
        messages: list[dict],
        max_tokens: int,
        json_mode: bool,
        stream: bool,
        effort: str | None,
    ) -> tuple[str, str]:
        import google.generativeai as genai

        key = self.config.get_api_key("google")
        if not key:
            raise RuntimeError("Missing GOOGLE_API_KEY")
        genai.configure(api_key=key)

        system_parts: list[str] = []
        contents: list[dict[str, Any]] = []
        for m in messages:
            role = str(m.get("role", "user"))
            raw_content = m.get("content", "")
            text = self._to_google_text(raw_content)
            if role == "system":
                system_parts.append(text)
            elif role == "assistant":
                contents.append({"role": "model", "parts": [text]})
            else:
                contents.append({"role": "user", "parts": [text]})

        if not contents:
            contents = [{"role": "user", "parts": [""]}]

        gen_config_kwargs: dict[str, Any] = {"max_output_tokens": max_tokens}
        if json_mode and supports_json_mode(provider_id, model_id):
            gen_config_kwargs["response_mime_type"] = "application/json"
        gen_config = genai.GenerationConfig(**gen_config_kwargs)

        model_info = PROVIDER_REGISTRY.get("google", {}).get("models", {}).get(model_id, {})
        if model_info.get("thinking_level") and effort:
            thinking_level_map = {
                "none": "minimal",
                "low": "low",
                "medium": "medium",
                "high": "high",
                "xhigh": "high",
                "max": "high",
            }
            try:
                setattr(gen_config, "thinking_level", thinking_level_map.get(effort, "medium"))
            except (AttributeError, TypeError):
                pass

        system_instruction = "\n".join(system_parts).strip() if system_parts else None
        model = (
            genai.GenerativeModel(model_name=model_id, system_instruction=system_instruction)
            if system_instruction
            else genai.GenerativeModel(model_name=model_id)
        )

        if stream:
            chunks: list[str] = []
            for chunk in model.generate_content(contents, generation_config=gen_config, stream=True):
                text = getattr(chunk, "text", None)
                if text:
                    chunks.append(text)
            return "".join(chunks), model_id

        resp = self._retry_google(model, contents, gen_config)
        return str(getattr(resp, "text", "") or ""), model_id

    def _to_google_text(self, content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            texts: list[str] = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    texts.append(str(part.get("text", "")))
            return "\n".join(t for t in texts if t)
        return str(content)

    def _retry_google(self, model: Any, contents: list[dict], gen_config: Any):
        try:
            return model.generate_content(contents, generation_config=gen_config)
        except Exception as e:
            msg = str(e).lower()
            if any(t in msg for t in ("resource_exhausted", "rate limit", "internal", "unavailable")):
                return model.generate_content(contents, generation_config=gen_config)
            raise

    def _retry_openai_on_token_limit(self, client: Any, kwargs: dict[str, Any], is_reasoning_model: bool):
        try:
            return client.chat.completions.create(**kwargs)
        except Exception as e:
            msg = str(e).lower()
            if "unexpected keyword argument 'reasoning'" in msg and "reasoning" in kwargs:
                retry_no_reasoning = dict(kwargs)
                retry_no_reasoning.pop("reasoning", None)
                return client.chat.completions.create(**retry_no_reasoning)
            is_token_error = (
                "max_tokens or model output limit was reached" in msg
                or ("max output" in msg and "token" in msg and "reached" in msg)
            )
            if not (is_reasoning_model and is_token_error):
                raise
            retry = dict(kwargs)
            current = int(retry.get("max_completion_tokens", 0) or 0)
            retry["max_completion_tokens"] = min(max(current * 2, 1200), 8000)
            return client.chat.completions.create(**retry)

    def stream_chat(
        self,
        role: str,
        messages: list[dict],
        max_tokens: int = 1000,
        role_override: tuple[str, str] | None = None,
    ) -> Generator[tuple[str, bool], None, None]:
        provider_id, model_id = self.config.resolve(role, role_override=role_override)
        sdk = get_sdk(provider_id)
        full_content: list[str] = []

        if sdk == "anthropic_native":
            import anthropic

            key = self.config.get_api_key("anthropic")
            client = anthropic.Anthropic(api_key=key)
            system, msgs = self._split_anthropic_messages(messages)
            with client.messages.stream(
                model=model_id,
                max_tokens=max_tokens,
                system=system,
                messages=msgs,
            ) as s:
                for text in s.text_stream:
                    full_content.append(text)
                    yield text, False
        elif sdk == "google_native":
            content, _ = self._call_google(
                provider_id=provider_id,
                model_id=model_id,
                messages=messages,
                max_tokens=max_tokens,
                json_mode=False,
                stream=True,
                effort=None,
            )
            if content:
                full_content.append(content)
                yield content, False
        else:
            client = self._get_openai_client(provider_id)
            kwargs = self._build_openai_kwargs(
                provider_id=provider_id,
                model_id=model_id,
                messages=messages,
                max_tokens=max_tokens,
                json_mode=False,
                effort=None,
            )
            kwargs["stream"] = True
            try:
                stream_resp = client.chat.completions.create(**kwargs)
            except Exception as e:
                msg = str(e).lower()
                if "unexpected keyword argument 'reasoning'" in msg and "reasoning" in kwargs:
                    retry = dict(kwargs)
                    retry.pop("reasoning", None)
                    stream_resp = client.chat.completions.create(**retry)
                else:
                    raise
            for chunk in stream_resp:
                choices = getattr(chunk, "choices", None) or []
                if not choices:
                    continue
                delta_obj = getattr(choices[0], "delta", None)
                delta = getattr(delta_obj, "content", None) or ""
                if delta:
                    full_content.append(delta)
                    yield delta, False

        yield "".join(full_content), True

    def _split_anthropic_messages(self, messages: list[dict]) -> tuple[str, list[dict]]:
        system = ""
        msgs: list[dict] = []
        for m in messages:
            role = m.get("role", "user")
            if role == "system":
                system = str(m.get("content", ""))
            else:
                msgs.append(
                    {
                        "role": role if role in ("assistant", "user") else "user",
                        "content": self._to_anthropic_content(m.get("content", "")),
                    }
                )
        return system, msgs

    def _build_openai_kwargs(
        self,
        provider_id: str,
        model_id: str,
        messages: list[dict],
        max_tokens: int,
        json_mode: bool,
        effort: str | None,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": model_id,
            "messages": messages,
        }

        if json_mode and supports_json_mode(provider_id, model_id):
            kwargs["response_format"] = {"type": "json_object"}

        if is_reasoning(provider_id, model_id):
            kwargs["max_completion_tokens"] = max_tokens
            eff = effort or self.config.get_effort(provider_id)
            if eff and get_effort_options(provider_id, model_id):
                kwargs["reasoning"] = {"effort": eff}
        else:
            kwargs["max_tokens"] = max_tokens
            if supports_temperature(provider_id, model_id):
                kwargs["temperature"] = 0.7

        if provider_id == "xai":
            kwargs.pop("reasoning", None)
            style = get_reasoning_style(provider_id, model_id)
            if style == "effort_kw":
                xai_effort = "high" if (effort or "").lower() in ("medium", "high", "xhigh", "max") else "low"
                kwargs["reasoning_effort"] = xai_effort

        return kwargs

