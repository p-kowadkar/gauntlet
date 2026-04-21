import sys
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QThread, pyqtSignal

from core.pipeline import GauntletPipeline


class PipelineWorker(QThread):
    """
    Runs GauntletPipeline off the main thread so the UI never blocks.

    Signals:
        step_started(name, index)   -- before each agent
        pipeline_complete(result)   -- full result dict on success
        pipeline_error(message)     -- error string on exception
    """

    step_started = pyqtSignal(str, int)
    pipeline_complete = pyqtSignal(dict)
    pipeline_error = pyqtSignal(str)

    def __init__(self, agent_spec: str, domain: str, parent=None):
        super().__init__(parent)
        self.agent_spec = agent_spec
        self.domain = domain

    def run(self):
        try:
            pipeline = GauntletPipeline(
                on_step=lambda name, idx: self.step_started.emit(name, idx)
            )
            result = pipeline.run(
                agent_spec=self.agent_spec,
                domain=self.domain,
            )
            self.pipeline_complete.emit(result)
        except Exception as e:
            self.pipeline_error.emit(str(e))


class CodeAnalysisWorker(QThread):
    analysis_complete = pyqtSignal(dict)
    analysis_error = pyqtSignal(str)

    def __init__(self, file_path: str, parent=None):
        super().__init__(parent)
        self.file_path = file_path

    def run(self):
        try:
            from agents.code_analysis_agent import analyze_file

            result = analyze_file(self.file_path)
            self.analysis_complete.emit(result)
        except Exception as e:
            self.analysis_error.emit(str(e))


class StreamingAssistWorker(QThread):
    token_received = pyqtSignal(str)
    stream_complete = pyqtSignal(dict)
    stream_error = pyqtSignal(str)

    def __init__(
        self,
        query: str,
        search_enabled: bool,
        role: str = "primary_llm",
        model_override: str | tuple[str, str] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.query = query
        self.search_enabled = search_enabled
        self.role = role
        self.model_override = model_override

    def run(self):
        try:
            from agents.assist_agent import _normalize_override, prepare_assist_request
            from core.model_router import ModelRouter

            role_override = None
            if self.model_override:
                role_override = _normalize_override(self.model_override)

            prepared = prepare_assist_request(
                query=self.query,
                search_enabled=self.search_enabled,
            )
            messages = prepared.get("messages", [])

            router = ModelRouter()
            _provider, model_name = router.config.resolve(
                self.role,
                role_override=role_override,
            )

            parts: list[str] = []
            final_content = ""
            for token, is_final in router.stream_chat(
                role=self.role,
                messages=messages,
                max_tokens=1000,
                role_override=role_override,
            ):
                if is_final:
                    final_content = token or "".join(parts)
                else:
                    if token:
                        parts.append(token)
                        self.token_received.emit(token)

            if not final_content:
                final_content = "".join(parts)

            self.stream_complete.emit(
                {
                    "content": final_content.strip(),
                    "model_used": model_name,
                    "role": self.role,
                    "search_results": prepared.get("search_results", []),
                    "sources": prepared.get("sources", []),
                }
            )
        except Exception as e:
            self.stream_error.emit(str(e))


class StreamingCodeAnalysisWorker(QThread):
    stage_update = pyqtSignal(str)
    token_received = pyqtSignal(str)
    analysis_complete = pyqtSignal(dict)
    analysis_error = pyqtSignal(str)

    def __init__(self, file_path: str, parent=None):
        super().__init__(parent)
        self.file_path = file_path

    def _emit_stage(self, message: str) -> None:
        msg = str(message)
        if not msg.endswith("\n"):
            msg += "\n"
        self.stage_update.emit(msg)

    def _stream_llm(
        self,
        role: str,
        messages: list[dict],
        max_tokens: int,
        role_override: tuple[str, str] | None = None,
    ) -> tuple[str, str]:
        from core.model_router import ModelRouter

        router = ModelRouter()
        _provider, model_name = router.config.resolve(
            role,
            role_override=role_override,
        )

        parts: list[str] = []
        full_content = ""
        for token, is_final in router.stream_chat(
            role=role,
            messages=messages,
            max_tokens=max_tokens,
            role_override=role_override,
        ):
            if is_final:
                full_content = token or "".join(parts)
            else:
                if token:
                    parts.append(token)
                    self.token_received.emit(token)

        if not full_content:
            full_content = "".join(parts)
        if full_content and not full_content.endswith("\n"):
            self.stage_update.emit("\n")
        return full_content, model_name

    def _result_template(self) -> dict[str, Any]:
        return {
            "filename": Path(self.file_path).name,
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

    def run(self):
        result = self._result_template()
        try:
            veris_agent_path = Path(__file__).resolve().parent.parent / "veris_code_agent"
            if str(veris_agent_path) not in sys.path:
                sys.path.insert(0, str(veris_agent_path))

            from agents.code_analysis_agent import _select_secondary_override
            from app.analyzer import format_issues, format_runtime, runtime_analysis, static_analysis

            code = Path(self.file_path).read_text(encoding="utf-8")

            self._emit_stage("━━ Stage 1/4: Static + Runtime analysis")
            static_issues = static_analysis(code)
            runtime_result = runtime_analysis(code, timeout_seconds=5)
            self._emit_stage(
                f"Static issues: {len(static_issues)} | Runtime timeout: {bool(runtime_result.get('timed_out', False))}"
            )

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

            self._emit_stage("━━ Stage 2/4: Primary model analysis")
            primary_analysis, primary_model = self._stream_llm(
                role="code_analysis",
                messages=analysis_messages,
                max_tokens=1500,
            )
            self._emit_stage(f"Primary model: {primary_model}")

            secondary_override = _select_secondary_override(primary_model)
            self._emit_stage("━━ Stage 2/4: Secondary model analysis")
            if secondary_override:
                secondary_analysis, secondary_model = self._stream_llm(
                    role="code_analysis",
                    messages=analysis_messages,
                    max_tokens=1500,
                    role_override=secondary_override,
                )
            else:
                secondary_analysis, secondary_model = self._stream_llm(
                    role="primary_llm",
                    messages=analysis_messages,
                    max_tokens=1500,
                )
            self._emit_stage(f"Secondary model: {secondary_model}")

            primary_name = primary_model
            secondary_name = secondary_model

            primary_critique_prompt = (
                "Critique this engineer's analysis. What did they miss or get wrong?\n"
                f"Their analysis ({secondary_name}): {secondary_analysis}\n"
                f"Your analysis ({primary_name}): {primary_analysis}"
            )
            secondary_critique_prompt = (
                "Critique this engineer's analysis. What did they miss or get wrong?\n"
                f"Their analysis ({primary_name}): {primary_analysis}\n"
                f"Your analysis ({secondary_name}): {secondary_analysis}"
            )

            self._emit_stage(f"━━ Stage 3/4: {primary_name} critiques {secondary_name}")
            primary_critique, _ = self._stream_llm(
                role="code_analysis",
                messages=[{"role": "user", "content": primary_critique_prompt}],
                max_tokens=800,
            )

            self._emit_stage(f"━━ Stage 3/4: {secondary_name} critiques {primary_name}")
            if secondary_override:
                secondary_critique, _ = self._stream_llm(
                    role="code_analysis",
                    messages=[{"role": "user", "content": secondary_critique_prompt}],
                    max_tokens=800,
                    role_override=secondary_override,
                )
            else:
                secondary_critique, _ = self._stream_llm(
                    role="primary_llm",
                    messages=[{"role": "user", "content": secondary_critique_prompt}],
                    max_tokens=800,
                )

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

            self._emit_stage("━━ Stage 4/4: Final judge synthesis")
            final_verdict, judge_model = self._stream_llm(
                role="final_judge",
                messages=[{"role": "user", "content": final_prompt}],
                max_tokens=2000,
            )
            self._emit_stage(f"Judge model: {judge_model}")

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
            self.analysis_complete.emit(result)
        except Exception as e:
            self.analysis_error.emit(str(e))
