import base64
import concurrent.futures
import json

import requests

from config import YOUCOM_SEARCH_URL
from core.model_config import ModelConfig
from core.model_router import ModelRouter


def _router() -> ModelRouter:
    return ModelRouter(ModelConfig.load())


def _normalize_override(model_override) -> tuple[str, str]:
    if isinstance(model_override, (tuple, list)) and len(model_override) == 2:
        return str(model_override[0]), str(model_override[1])

    if isinstance(model_override, str):
        val = model_override.strip().lower()
        if val == "baseten":
            return "baseten", "zai-org/GLM-5"
        if val == "fallback":
            return "openai", "gpt-5.4-mini"

    raise ValueError("model_override must be ('provider', 'model') or legacy 'baseten'/'fallback'")


def _search_youcom(query, count=5):
    key = ModelConfig.load().get_api_key("youcom")
    if not key:
        return []
    try:
        resp = requests.get(
            YOUCOM_SEARCH_URL,
            params={"query": query, "count": count},
            headers={"X-API-Key": key},
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
                "You are a query classifier. Return only JSON with keys: "
                "needs_search (bool), sub_questions (list), is_complex (bool)."
            ),
        },
        {"role": "user", "content": query},
    ]
    try:
        content, _ = _router().chat(
            role="classifier",
            messages=messages,
            max_tokens=600,
            json_mode=True,
            effort="none",
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


def prepare_assist_request(query: str, search_enabled: bool) -> dict:
    query = (query or "").strip()
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
        return {
            "messages": messages,
            "search_results": raw_results,
            "sources": raw_results[:5],
        }

    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": query},
    ]
    return {
        "messages": messages,
        "search_results": [],
        "sources": [],
    }


def _run_text_assist(query: str, search_enabled: bool, role_override: tuple[str, str] | None = None):
    router = _router()
    prepared = prepare_assist_request(query=query, search_enabled=search_enabled)
    messages = prepared.get("messages", [])
    content, model_name = router.chat(
        role="primary_llm",
        role_override=role_override,
        messages=messages,
        max_tokens=1000,
        json_mode=False,
    )
    return {
        "content": content.strip(),
        "model_used": model_name,
        "search_results": prepared.get("search_results", []),
        "sources": prepared.get("sources", []),
    }


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
        content, model_name = _router().chat(
            role="vision",
            messages=messages,
            max_tokens=1200,
            json_mode=False,
            vision=True,
        )
        return {
            "content": content.strip(),
            "model_used": model_name,
            "search_results": [],
            "sources": [],
        }

    return _run_text_assist(query=query, search_enabled=search_enabled, role_override=None)


def run_assist_with_model(query, search_enabled, model_override, vision_data=None):
    query = (query or "").strip()
    if vision_data is not None:
        return run_assist(query, search_enabled=search_enabled, vision_data=vision_data)
    override_tuple = _normalize_override(model_override)
    return _run_text_assist(query=query, search_enabled=search_enabled, role_override=override_tuple)
