import concurrent.futures
import sys
from pathlib import Path

from core.model_config import FALLBACK_CHAINS, ModelConfig
from core.model_router import ModelRouter

# Add veris_code_agent to path so we can reuse analyzer.py
sys.path.insert(0, str(Path(__file__).parent.parent / "veris_code_agent"))
from app.analyzer import format_issues, format_runtime, runtime_analysis, static_analysis  # noqa: E402


def _llm(
    role: str,
    messages: list[dict],
    max_tokens: int,
    role_override: tuple[str, str] | None = None,
) -> tuple[str, str]:
    content, model_used = ModelRouter().chat(
        role=role,
        role_override=role_override,
        messages=messages,
        max_tokens=max_tokens,
        json_mode=False,
    )
    return content, model_used


def _select_secondary_override(primary_model: str) -> tuple[str, str] | None:
    cfg = ModelConfig.load()
    for provider_id, model_id in FALLBACK_CHAINS.get("classifier", []):
        if not model_id:
            continue
        if model_id == primary_model:
            continue
        if cfg.provider_available(provider_id, model_id):
            return provider_id, model_id
    return None


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
        "analysis_model_1": "",
        "analysis_model_2": "",
        "judge_model": "",
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

        primary_analysis, primary_model = _llm("code_analysis", analysis_messages, 1500)
        secondary_override = _select_secondary_override(primary_model)

        if secondary_override:
            secondary_analysis, secondary_model = _llm(
                "code_analysis",
                analysis_messages,
                1500,
                role_override=secondary_override,
            )
        else:
            secondary_analysis, secondary_model = _llm("primary_llm", analysis_messages, 1500)

        primary_name = primary_model
        secondary_name = secondary_model

        primary_critique_prompt = (
            f"Critique this engineer's analysis. What did they miss or get wrong?\n"
            f"Their analysis ({secondary_name}): {secondary_analysis}\n"
            f"Your analysis ({primary_name}): {primary_analysis}"
        )
        secondary_critique_prompt = (
            f"Critique this engineer's analysis. What did they miss or get wrong?\n"
            f"Their analysis ({primary_name}): {primary_analysis}\n"
            f"Your analysis ({secondary_name}): {secondary_analysis}"
        )

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            primary_critique_future = executor.submit(
                _llm,
                "code_analysis",
                [{"role": "user", "content": primary_critique_prompt}],
                800,
                None,
            )
            if secondary_override:
                secondary_critique_future = executor.submit(
                    _llm,
                    "code_analysis",
                    [{"role": "user", "content": secondary_critique_prompt}],
                    800,
                    secondary_override,
                )
            else:
                secondary_critique_future = executor.submit(
                    _llm,
                    "primary_llm",
                    [{"role": "user", "content": secondary_critique_prompt}],
                    800,
                    None,
                )
            primary_critique, _ = primary_critique_future.result()
            secondary_critique, _ = secondary_critique_future.result()

        final_prompt = (
            "You are the final authority. Two engineers analyzed code, then critiqued each other.\n"
            "Synthesize into the definitive bug report.\n"
            f"{primary_name} analysis: {primary_analysis}\n"
            f"{secondary_name} analysis: {secondary_analysis}\n"
            f"{primary_name} critique of {secondary_name}: {primary_critique}\n"
            f"{secondary_name} critique of {primary_name}: {secondary_critique}\n"
            "Produce: numbered bug list with line, severity, explanation, fix.\n"
            "End with: VERDICT: SAFE | NEEDS REVIEW | DANGEROUS\n"
            "Then one sentence executive summary."
        )
        final_verdict, judge_model = _llm("final_judge", [{"role": "user", "content": final_prompt}], 2000)

        result.update(
            {
                "static_issues": static_issues,
                "runtime": runtime_result,
                "glm5_analysis": primary_analysis,
                "mini_analysis": secondary_analysis,
                "glm5_critique": primary_critique,
                "mini_critique": secondary_critique,
                "final_verdict": final_verdict,
                "analysis_model_1": primary_name,
                "analysis_model_2": secondary_name,
                "judge_model": judge_model,
            }
        )
    except Exception as e:
        result["error"] = str(e)
    return result
