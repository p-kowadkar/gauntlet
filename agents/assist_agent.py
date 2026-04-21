import json
import requests
import base64
import concurrent.futures
import openai
from config import (
    BASETEN_API_KEY, BASETEN_BASE_URL, BASETEN_MODEL_SLUG,
    BASETEN_VISION_MODEL, OPENAI_API_KEY, OPENAI_FALLBACK_MODEL,
    OPENAI_REASONING_EFFORT, YOUCOM_API_KEY, YOUCOM_SEARCH_URL
)

baseten_client = openai.OpenAI(
    base_url=BASETEN_BASE_URL,
    api_key=BASETEN_API_KEY
) if BASETEN_API_KEY else None
fallback_client = openai.OpenAI(api_key=OPENAI_API_KEY)


def _format_model_used(model_name: str) -> str:
    if model_name == BASETEN_MODEL_SLUG:
        return "GLM-5 (Baseten)"
    if model_name == BASETEN_VISION_MODEL:
        return "Kimi K2.5 (Baseten)"
    if model_name == OPENAI_FALLBACK_MODEL:
        return "gpt-5.4-mini"
    return model_name


def _is_token_limit_error(error: Exception) -> bool:
    msg = str(error).lower()
    return (
        "max_tokens or model output limit was reached" in msg
        or ("max output" in msg and "token" in msg and "reached" in msg)
    )


def _create_completion_with_retry(client, kwargs: dict, is_reasoning: bool):
    try:
        return client.chat.completions.create(**kwargs)
    except Exception as e:
        if not (is_reasoning and _is_token_limit_error(e)):
            raise

        retry_kwargs = dict(kwargs)
        current = int(retry_kwargs.get("max_completion_tokens", 0) or 0)
        retry_kwargs["max_completion_tokens"] = min(max(current * 2, 1200), 8000)
        return client.chat.completions.create(**retry_kwargs)


def _llm_call(messages, max_tokens=1000, json_mode=False, vision=False, reasoning_effort=None):
    if vision:
        if not baseten_client:
            raise RuntimeError("Vision mode requires Baseten API key configuration.")
        client = baseten_client
        model = BASETEN_VISION_MODEL
        is_reasoning = False
    else:
        client = baseten_client if baseten_client else fallback_client
        model = BASETEN_MODEL_SLUG if baseten_client else OPENAI_FALLBACK_MODEL
        is_reasoning = (model == OPENAI_FALLBACK_MODEL)

    kwargs = {
        "model": model,
        "messages": messages,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    if is_reasoning:
        kwargs["max_completion_tokens"] = max_tokens
        effort = reasoning_effort or OPENAI_REASONING_EFFORT
        kwargs["reasoning"] = {"effort": effort}
    else:
        kwargs["max_tokens"] = max_tokens

    resp = _create_completion_with_retry(client, kwargs, is_reasoning)
    return (resp.choices[0].message.content or ""), model


def _llm_call_with_override(messages, model_override, max_tokens=1000, json_mode=False, reasoning_effort=None):
    if model_override == "baseten":
        if not baseten_client:
            raise RuntimeError("Baseten override requested but BASETEN_API_KEY is not configured.")
        client = baseten_client
        model = BASETEN_MODEL_SLUG
        is_reasoning = False
    elif model_override == "fallback":
        client = fallback_client
        model = OPENAI_FALLBACK_MODEL
        is_reasoning = True
    else:
        raise ValueError("model_override must be either 'baseten' or 'fallback'.")

    kwargs = {
        "model": model,
        "messages": messages,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    if is_reasoning:
        kwargs["max_completion_tokens"] = max_tokens
        effort = reasoning_effort or OPENAI_REASONING_EFFORT
        kwargs["reasoning"] = {"effort": effort}
    else:
        kwargs["max_tokens"] = max_tokens

    resp = _create_completion_with_retry(client, kwargs, is_reasoning)
    return (resp.choices[0].message.content or ""), model


def _search_youcom(query, count=5):
    try:
        resp = requests.get(
            YOUCOM_SEARCH_URL,
            params={"query": query, "count": count},
            headers={"X-API-Key": YOUCOM_API_KEY},
            timeout=15,
        )
        resp.raise_for_status()
        web_results = resp.json().get("results", {}).get("web", [])
        findings = []
        for r in web_results[:count]:
            desc = r.get("description", "")
            if desc:
                findings.append(desc)
            else:
                snippets = r.get("snippets", [])
                if snippets:
                    findings.append(snippets[0])
        return findings
    except Exception:
        return []


def _dedupe_keep_order(items):
    seen = set()
    out = []
    for item in items:
        text = (item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def _classify_query(query):
    messages = [
        {
            "role": "system",
            "content": (
                "You are a query classifier. Classify this query and return ONLY JSON: "
                "{needs_search, sub_questions (list of parallel search queries if complex, else empty), is_complex}"
            ),
        },
        {"role": "user", "content": query},
    ]
    try:
        content, _ = _llm_call(
            messages,
            max_tokens=600,
            json_mode=True,
            vision=False,
            reasoning_effort="none",
        )
        parsed = json.loads(content)
        sub_questions = parsed.get("sub_questions", [])
        if not isinstance(sub_questions, list):
            sub_questions = []
        sub_questions = [str(q).strip() for q in sub_questions if str(q).strip()]
        return {
            "needs_search": bool(parsed.get("needs_search", True)),
            "sub_questions": sub_questions,
            "is_complex": bool(parsed.get("is_complex", False)),
        }
    except Exception:
        return {
            "needs_search": True,
            "sub_questions": [],
            "is_complex": False,
        }


def _assist_messages_for_query(query, search_results):
    context = "\n".join(f"- {r}" for r in search_results[:8]) if search_results else "- No search context available."
    return [
        {
            "role": "system",
            "content": (
                "You are a helpful assistant. Answer based on these real-time search results:\n"
                f"{context}"
            ),
        },
        {"role": "user", "content": query},
    ]


def run_assist(query, search_enabled=True, vision_data=None):
    query = (query or "").strip()
    if vision_data is not None:
        if not query:
            query = "Describe what you see on this screen"
        try:
            base64.b64decode(vision_data, validate=True)
        except Exception as e:
            raise ValueError(f"Invalid vision_data base64 input: {e}")

        messages = [
            {
                "role": "system",
                "content": "You are a helpful visual assistant. Analyze the screenshot and answer clearly.",
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": query},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{vision_data}"}},
                ],
            },
        ]
        content, _ = _llm_call(messages, max_tokens=1200, json_mode=False, vision=True)
        return {
            "content": content.strip(),
            "model_used": "Kimi K2.5 (Baseten)",
            "search_results": [],
            "sources": [],
        }

    if search_enabled:
        classification = _classify_query(query)
        raw_results = []
        if classification.get("needs_search", True):
            sub_questions = classification.get("sub_questions", [])
            if classification.get("is_complex") and len(sub_questions) > 1:
                with concurrent.futures.ThreadPoolExecutor(max_workers=min(6, len(sub_questions))) as executor:
                    futures = [executor.submit(_search_youcom, sq, 5) for sq in sub_questions]
                    for fut in concurrent.futures.as_completed(futures):
                        try:
                            raw_results.extend(fut.result() or [])
                        except Exception:
                            pass
            else:
                raw_results = _search_youcom(query, 8)
        raw_results = _dedupe_keep_order(raw_results)
        messages = _assist_messages_for_query(query, raw_results)
        content, model_name = _llm_call(messages, max_tokens=1000, json_mode=False, vision=False)
        return {
            "content": content.strip(),
            "model_used": _format_model_used(model_name),
            "search_results": raw_results,
            "sources": raw_results[:5],
        }

    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": query},
    ]
    content, model_name = _llm_call(messages, max_tokens=1000, json_mode=False, vision=False)
    return {
        "content": content.strip(),
        "model_used": _format_model_used(model_name),
        "search_results": [],
        "sources": [],
    }


def run_assist_with_model(query, search_enabled, model_override, vision_data=None):
    query = (query or "").strip()
    if vision_data is not None:
        return run_assist(query, search_enabled=search_enabled, vision_data=vision_data)

    if search_enabled:
        classification = _classify_query(query)
        raw_results = []
        if classification.get("needs_search", True):
            sub_questions = classification.get("sub_questions", [])
            if classification.get("is_complex") and len(sub_questions) > 1:
                with concurrent.futures.ThreadPoolExecutor(max_workers=min(6, len(sub_questions))) as executor:
                    futures = [executor.submit(_search_youcom, sq, 5) for sq in sub_questions]
                    for fut in concurrent.futures.as_completed(futures):
                        try:
                            raw_results.extend(fut.result() or [])
                        except Exception:
                            pass
            else:
                raw_results = _search_youcom(query, 8)
        raw_results = _dedupe_keep_order(raw_results)
        messages = _assist_messages_for_query(query, raw_results)
        content, model_name = _llm_call_with_override(
            messages, model_override=model_override, max_tokens=1000, json_mode=False
        )
        return {
            "content": content.strip(),
            "model_used": _format_model_used(model_name),
            "search_results": raw_results,
            "sources": raw_results[:5],
        }

    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": query},
    ]
    content, model_name = _llm_call_with_override(
        messages, model_override=model_override, max_tokens=1000, json_mode=False
    )
    return {
        "content": content.strip(),
        "model_used": _format_model_used(model_name),
        "search_results": [],
        "sources": [],
    }
