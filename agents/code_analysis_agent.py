import concurrent.futures
import sys
from pathlib import Path

import openai

from config import (
    BASETEN_API_KEY,
    BASETEN_BASE_URL,
    BASETEN_MODEL_SLUG,
    OPENAI_API_KEY,
    OPENAI_FALLBACK_MODEL,
    OPENAI_REASONING_EFFORT,
)

# Add veris_code_agent to path so we can reuse analyzer.py
sys.path.insert(0, str(Path(__file__).parent.parent / "veris_code_agent"))
from app.analyzer import static_analysis, runtime_analysis, format_issues, format_runtime  # noqa: E402


baseten_client = openai.OpenAI(
    base_url=BASETEN_BASE_URL,
    api_key=BASETEN_API_KEY,
) if BASETEN_API_KEY else None
fallback_client = openai.OpenAI(api_key=OPENAI_API_KEY)


def _llm(model: str, messages: list[dict], max_tokens: int) -> str:
    use_glm5 = model == "glm5" and baseten_client is not None
    client = baseten_client if use_glm5 else fallback_client
    model_name = BASETEN_MODEL_SLUG if use_glm5 else OPENAI_FALLBACK_MODEL

    kwargs = {
        "model": model_name,
        "messages": messages,
    }
    if use_glm5:
        kwargs["max_tokens"] = max_tokens
    else:
        kwargs["max_completion_tokens"] = max_tokens
        kwargs["reasoning"] = {"effort": OPENAI_REASONING_EFFORT}

    try:
        response = client.chat.completions.create(**kwargs)
    except TypeError as e:
        msg = str(e)
        retry_kwargs = dict(kwargs)
        changed = False

        if "reasoning" in msg and "reasoning" in retry_kwargs:
            retry_kwargs.pop("reasoning", None)
            changed = True
        if "max_completion_tokens" in msg and "max_completion_tokens" in retry_kwargs:
            retry_kwargs["max_tokens"] = retry_kwargs.pop("max_completion_tokens")
            changed = True

        if not changed:
            raise
        response = client.chat.completions.create(**retry_kwargs)
    return response.choices[0].message.content or ""


def analyze_file(file_path: str) -> dict:
    result = {
        "filename": Path(file_path).name,
        "static_issues": [],
        "runtime": {},
        "glm5_analysis": "",
        "mini_analysis": "",
        "glm5_critique": "",
        "mini_critique": "",
        "final_verdict": "",
        "error": None,
    }
    try:
        code = Path(file_path).read_text(encoding="utf-8")

        static_issues = static_analysis(code)
        runtime_result = runtime_analysis(code, timeout_seconds=5)
        static_report = format_issues(static_issues)
        runtime_report = format_runtime(runtime_result)

        analysis_prompt = (
            "You are a senior engineer reviewing Python code for bugs.\n"
            f"Static analysis found: {static_report}\n"
            f"Runtime result: {runtime_report}\n"
            f"Code: ```python\n{code}\n```\n"
            "List every bug with line number, severity (CRITICAL/HIGH/MEDIUM), "
            "plain explanation, and fix."
        )
        analysis_messages = [{"role": "user", "content": analysis_prompt}]

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            future_glm5 = executor.submit(_llm, "glm5", analysis_messages, 1500)
            future_mini = executor.submit(_llm, "mini", analysis_messages, 1500)
            glm5_analysis = future_glm5.result()
            mini_analysis = future_mini.result()

        glm5_critique_prompt = (
            "Critique this engineer's analysis. What did they miss or get wrong?\n"
            f"Their analysis: {mini_analysis}\n"
            f"Your analysis: {glm5_analysis}"
        )
        mini_critique_prompt = (
            "Critique this engineer's analysis. What did they miss or get wrong?\n"
            f"Their analysis: {glm5_analysis}\n"
            f"Your analysis: {mini_analysis}"
        )

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            future_glm5_critique = executor.submit(
                _llm, "glm5", [{"role": "user", "content": glm5_critique_prompt}], 800
            )
            future_mini_critique = executor.submit(
                _llm, "mini", [{"role": "user", "content": mini_critique_prompt}], 800
            )
            glm5_critique = future_glm5_critique.result()
            mini_critique = future_mini_critique.result()

        final_prompt = (
            "You are the final authority. Two engineers analyzed code, then critiqued each other.\n"
            "Synthesize into the definitive bug report.\n"
            f"GLM-5 analysis: {glm5_analysis}\n"
            f"gpt-5.4-mini analysis: {mini_analysis}\n"
            f"GLM-5 critique of mini: {glm5_critique}\n"
            f"mini critique of GLM-5: {mini_critique}\n"
            "Produce: numbered bug list with line, severity, explanation, fix.\n"
            "End with: VERDICT: SAFE | NEEDS REVIEW | DANGEROUS\n"
            "Then one sentence executive summary."
        )
        final_verdict = _llm("mini", [{"role": "user", "content": final_prompt}], 2000)

        result.update(
            {
                "static_issues": static_issues,
                "runtime": runtime_result,
                "glm5_analysis": glm5_analysis,
                "mini_analysis": mini_analysis,
                "glm5_critique": glm5_critique,
                "mini_critique": mini_critique,
                "final_verdict": final_verdict,
            }
        )
    except Exception as e:
        result["error"] = str(e)
    return result
