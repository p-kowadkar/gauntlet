import re
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit,
    QComboBox, QPushButton, QScrollArea, QStackedWidget,
    QLineEdit, QFileDialog, QFrame
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

from config import DOMAINS
from ui.components import COLORS, StepIndicator, RiskScoreWidget
from utils.thread_worker import PipelineWorker, CodeAnalysisWorker


class VerisStatusWorker(QThread):
    """
    Checks whether Veris sandbox is reachable via local CLI auth.
    LIVE  = Veris CLI token found -- sandbox runs in gVisor isolation
    LOCAL = No Veris token -- pipeline runs direct LLM analysis

    Both modes run real GLM-5 + gpt-5.4-mini adversarial consensus.
    The difference is execution context only.
    """
    status_checked = pyqtSignal(bool)

    def run(self):
        # Check ~/.veris/config.yaml for CLI token (fastest, no network call)
        veris_config = Path.home() / ".veris" / "config.yaml"
        if veris_config.exists():
            content = veris_config.read_text()
            if any(k in content for k in ("token", "api_key", "access")):
                self.status_checked.emit(True)
                return
        # Try SDK as fallback
        try:
            from veris import Veris
            Veris()
            self.status_checked.emit(True)
        except Exception:
            self.status_checked.emit(False)


class GauntletPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None
        self._analysis_worker = None
        self._veris_status_worker = None
        self._last_result = None
        self._setup_ui()
        self._start_veris_status_check()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 8, 12, 8)
        root.setSpacing(10)

        mode_row = QHBoxLayout()
        mode_row.setSpacing(8)

        self.agent_security_btn = QPushButton("🛡️ Agent Security")
        self.agent_security_btn.setCheckable(True)
        self.agent_security_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.agent_security_btn.clicked.connect(lambda: self._set_mode(0))
        mode_row.addWidget(self.agent_security_btn)

        self.code_analysis_btn = QPushButton("🔍 Code Analysis")
        self.code_analysis_btn.setCheckable(True)
        self.code_analysis_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.code_analysis_btn.clicked.connect(lambda: self._set_mode(1))
        mode_row.addWidget(self.code_analysis_btn)

        root.addLayout(mode_row)

        self.mode_stack = QStackedWidget()
        self.mode_stack.addWidget(self._build_agent_security_layout())
        self.mode_stack.addWidget(self._build_code_analysis_layout())
        root.addWidget(self.mode_stack, 1)

        self._set_mode(0)

    def _build_agent_security_layout(self):
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        root.addWidget(self._muted_label("Agent Spec"))

        self.spec_input = QTextEdit()
        self.spec_input.setPlaceholderText(
            "Paste your enterprise AI agent system prompt here..."
        )
        self.spec_input.setMaximumHeight(120)
        self.spec_input.setStyleSheet(
            f"background: {COLORS['surface']}; color: {COLORS['text']};"
            "border: 1px solid rgba(92,107,192,0.3); border-radius: 8px;"
            "font-family: Consolas; font-size: 12px; padding: 8px;"
        )
        root.addWidget(self.spec_input)

        row = QHBoxLayout()
        self.domain_combo = QComboBox()
        self.domain_combo.addItems(DOMAINS)
        self.domain_combo.setStyleSheet(
            f"background: {COLORS['surface']}; color: {COLORS['text']};"
            "border: 1px solid rgba(92,107,192,0.3); border-radius: 6px;"
            "padding: 5px 10px; font-size: 12px;"
        )
        row.addWidget(self.domain_combo, 1)

        self.run_btn = QPushButton("🚀 Run Gauntlet")
        self.run_btn.setMinimumHeight(36)
        self.run_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.run_btn.setStyleSheet(
            f"background: {COLORS['accent']}; color: white; border: none;"
            "border-radius: 8px; font-size: 13px; font-weight: bold; padding: 6px 18px;"
        )
        self.run_btn.clicked.connect(self._on_run)
        row.addWidget(self.run_btn)
        root.addLayout(row)

        self.steps = StepIndicator()
        root.addWidget(self.steps)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border: none; background: transparent;")
        results = QWidget()
        rl = QVBoxLayout(results)
        rl.setSpacing(10)

        self.risk_widget = RiskScoreWidget()
        self.risk_widget.setStyleSheet(
            f"background: {COLORS['surface']}; border-radius: 10px;"
            f"border: 1px solid {COLORS['border']};"
        )
        rl.addWidget(self.risk_widget)

        rl.addWidget(self._muted_label("Critical Findings"))
        self.findings_text = self._result_box(100)
        rl.addWidget(self.findings_text)

        rl.addWidget(self._muted_label("Hardened System Prompt"))
        self.hardened_text = self._result_box(
            120,
            bg="rgba(102,187,106,0.07)",
            border="rgba(102,187,106,0.3)",
        )
        rl.addWidget(self.hardened_text)

        self.voice_btn = QPushButton("🔊 Play Voice Briefing")
        self.voice_btn.setEnabled(False)
        self.voice_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.voice_btn.setStyleSheet(
            "background: rgba(92,107,192,0.2); color: #E8E8F0;"
            "border: 1px solid rgba(92,107,192,0.4); border-radius: 8px;"
            "padding: 8px 16px; font-size: 12px; font-weight: bold;"
        )
        self.voice_btn.clicked.connect(self._on_play)
        rl.addWidget(self.voice_btn)
        rl.addStretch()

        scroll.setWidget(results)
        root.addWidget(scroll, 1)
        return page

    def _build_code_analysis_layout(self):
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        root.addWidget(self._muted_label("File Path"))

        path_row = QHBoxLayout()
        path_row.setSpacing(6)

        self.file_path_input = QLineEdit()
        self.file_path_input.setPlaceholderText("Select a Python file to analyze...")
        self.file_path_input.setStyleSheet(
            f"background: {COLORS['surface']}; color: {COLORS['text']};"
            "border: 1px solid rgba(92,107,192,0.3); border-radius: 8px;"
            "font-family: Consolas; font-size: 11px; padding: 7px;"
        )
        self.file_path_input.textChanged.connect(self._on_file_path_changed)
        path_row.addWidget(self.file_path_input, 1)

        self.browse_btn = QPushButton("📂 Browse")
        self.browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.browse_btn.setStyleSheet(
            "background: rgba(92,107,192,0.18); color: #E8E8F0;"
            "border: 1px solid rgba(92,107,192,0.35); border-radius: 8px;"
            "font-size: 12px; font-weight: bold; padding: 7px 12px;"
        )
        self.browse_btn.clicked.connect(self._on_browse_file)
        path_row.addWidget(self.browse_btn)

        root.addLayout(path_row)

        self.analyze_btn = QPushButton("🔍 Analyze File")
        self.analyze_btn.setMinimumHeight(36)
        self.analyze_btn.setEnabled(False)
        self.analyze_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.analyze_btn.setStyleSheet(
            f"QPushButton {{ background: {COLORS['accent']}; color: white; border: none;"
            "border-radius: 8px; font-size: 13px; font-weight: bold; padding: 6px 18px; }"
            "QPushButton:disabled { background: rgba(92,107,192,89); color: rgba(255,255,255,166); }"
        )
        self.analyze_btn.clicked.connect(self._on_analyze_file)
        root.addWidget(self.analyze_btn)

        self.veris_badge = QLabel()
        self._set_veris_badge(False)
        root.addWidget(self.veris_badge)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border: none; background: transparent;")

        self.analysis_results = QWidget()
        results_layout = QVBoxLayout(self.analysis_results)
        results_layout.setContentsMargins(2, 2, 2, 2)
        results_layout.setSpacing(8)

        self.analyzing_label = QLabel("⏳ Analyzing...")
        self.analyzing_label.setStyleSheet(
            f"color: {COLORS['warning']}; font-size: 12px; font-weight: bold;"
        )
        self.analyzing_label.hide()
        results_layout.addWidget(self.analyzing_label)

        self.analysis_content = QWidget()
        self.analysis_content_layout = QVBoxLayout(self.analysis_content)
        self.analysis_content_layout.setContentsMargins(0, 0, 0, 0)
        self.analysis_content_layout.setSpacing(8)
        results_layout.addWidget(self.analysis_content)
        results_layout.addStretch()

        scroll.setWidget(self.analysis_results)
        root.addWidget(scroll, 1)

        self._render_analysis_placeholder("Select a Python file and click Analyze File.")
        return page

    def _mode_btn_style(self, selected: bool):
        if selected:
            return (
                f"background: {COLORS['accent']}; color: white;"
                f"border: 1px solid {COLORS['accent']}; border-radius: 12px;"
                "font-size: 12px; font-weight: bold; padding: 6px 12px;"
            )
        return (
            "background: transparent; color: #888899;"
            "border: 1px solid rgba(100,100,120,76); border-radius: 12px;"
            "font-size: 12px; font-weight: bold; padding: 6px 12px;"
        )

    def _set_mode(self, idx: int):
        self.mode_stack.setCurrentIndex(idx)
        self.agent_security_btn.setChecked(idx == 0)
        self.code_analysis_btn.setChecked(idx == 1)
        self.agent_security_btn.setStyleSheet(self._mode_btn_style(idx == 0))
        self.code_analysis_btn.setStyleSheet(self._mode_btn_style(idx == 1))

    def _muted_label(self, text):
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 11px; font-weight: bold;"
        )
        return lbl

    def _result_box(self, height, bg=None, border="rgba(92,107,192,0.25)"):
        box = QTextEdit()
        box.setReadOnly(True)
        box.setMaximumHeight(height)
        bg = bg or COLORS["surface"]
        box.setStyleSheet(
            f"background: {bg}; color: {COLORS['text']};"
            f"border: 1px solid {border}; border-radius: 8px;"
            "font-family: Consolas; font-size: 11px; padding: 8px;"
        )
        return box

    def _set_veris_badge(self, live: bool):
        if live:
            text  = "⚡ LIVE — Veris Sandbox Connected"
            color = COLORS["success"]
        else:
            # LOCAL is not mock -- real LLM adversarial consensus runs in-process
            text  = "🔵 LOCAL — Adversarial Consensus (GLM-5 × gpt-5.4-mini)"
            color = "#5C9BD6"
        self.veris_badge.setText(text)
        self.veris_badge.setStyleSheet(
            f"color: {color}; background: rgba(20,20,30,0.5);"
            f"border: 1px solid {color}; border-radius: 8px;"
            "font-size: 11px; font-weight: bold; padding: 4px 8px;"
        )

    def _start_veris_status_check(self):
        self._veris_status_worker = VerisStatusWorker(self)
        self._veris_status_worker.status_checked.connect(self._set_veris_badge)
        self._veris_status_worker.start()

    def _on_file_path_changed(self, text):
        self.analyze_btn.setEnabled(bool(text.strip()))

    def _on_browse_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Python file", "",
            "Python files (*.py);;All files (*)",
        )
        if file_path:
            self.file_path_input.setText(file_path)

    def _on_analyze_file(self):
        file_path = self.file_path_input.text().strip()
        if not file_path:
            return
        p = Path(file_path)
        if not p.exists():
            self._render_analysis_error(f"File not found: {file_path}")
            return
        if p.suffix.lower() != ".py":
            self._render_analysis_error("Please select a valid Python (.py) file.")
            return

        self.analyze_btn.setEnabled(False)
        self.analyze_btn.setText("⏳ Analyzing...")
        self.analyzing_label.show()
        self._clear_analysis_content()

        self._analysis_worker = CodeAnalysisWorker(file_path)
        self._analysis_worker.analysis_complete.connect(self._on_analysis_complete)
        self._analysis_worker.analysis_error.connect(self._on_analysis_error)
        self._analysis_worker.finished.connect(self._on_analysis_finished)
        self._analysis_worker.start()

    def _on_analysis_finished(self):
        self.analyzing_label.hide()
        self.analyze_btn.setText("🔍 Analyze File")
        self.analyze_btn.setEnabled(bool(self.file_path_input.text().strip()))

    def _on_analysis_complete(self, result):
        if result.get("error"):
            self._render_analysis_error(result["error"])
            return
        self._render_analysis_result(result)

    def _on_analysis_error(self, msg):
        self._render_analysis_error(msg)

    def _clear_analysis_content(self):
        while self.analysis_content_layout.count():
            item = self.analysis_content_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _render_analysis_placeholder(self, text):
        self._clear_analysis_content()
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 11px;"
            "border: 1px dashed rgba(100,100,120,0.4); border-radius: 8px; padding: 8px;"
        )
        self.analysis_content_layout.addWidget(lbl)

    def _render_analysis_error(self, msg):
        self._clear_analysis_content()
        lbl = QLabel(f"❌ {msg}")
        lbl.setWordWrap(True)
        lbl.setStyleSheet(
            f"color: {COLORS['danger']}; background: rgba(239,83,80,0.08);"
            "border: 1px solid rgba(239,83,80,0.4); border-radius: 8px;"
            "font-size: 11px; padding: 8px;"
        )
        self.analysis_content_layout.addWidget(lbl)

    def _severity_color(self, severity: str):
        return {
            "CRITICAL": COLORS["danger"],
            "HIGH":     "#FB8C00",
            "MEDIUM":   "#FDD835",
        }.get(severity.upper(), COLORS["text_muted"])

    def _finding_card(self, finding: dict):
        severity = str(finding.get("severity", "MEDIUM")).upper()
        line     = finding.get("line", "?")
        message  = finding.get("message", "")
        fix      = finding.get("fix", "")
        color    = self._severity_color(severity)

        card = QFrame()
        card.setStyleSheet(
            f"background: {COLORS['surface']};"
            "border: 1px solid rgba(92,107,192,0.28); border-radius: 8px;"
        )
        row = QHBoxLayout(card)
        row.setContentsMargins(0, 0, 8, 8)
        row.setSpacing(8)

        bar = QFrame()
        bar.setFixedWidth(4)
        bar.setStyleSheet(f"background: {color}; border: none; border-radius: 2px;")
        row.addWidget(bar)

        body = QVBoxLayout()
        body.setContentsMargins(0, 8, 0, 0)
        body.setSpacing(4)

        header = QLabel(f"Line {line} · {severity}")
        header.setStyleSheet(f"color: {color}; font-size: 10px; font-weight: bold;")
        body.addWidget(header)

        msg_lbl = QLabel(str(message))
        msg_lbl.setWordWrap(True)
        msg_lbl.setStyleSheet(f"color: {COLORS['text']}; font-size: 12px;")
        body.addWidget(msg_lbl)

        fix_lbl = QLabel(f"Fix: {fix}")
        fix_lbl.setWordWrap(True)
        fix_lbl.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 11px; font-style: italic;"
        )
        body.addWidget(fix_lbl)
        row.addLayout(body, 1)
        return card

    def _extract_verdict(self, text: str):
        upper = text.upper()
        if "DANGEROUS" in upper:
            return "DANGEROUS"
        if "NEEDS REVIEW" in upper:
            return "NEEDS REVIEW"
        if "SAFE" in upper:
            return "SAFE"
        return "NEEDS REVIEW"

    def _render_analysis_result(self, result: dict):
        self._clear_analysis_content()

        for finding in result.get("static_issues", []):
            self.analysis_content_layout.addWidget(self._finding_card(finding))

        if not result.get("static_issues"):
            ok = QLabel("✅ No static issues detected.")
            ok.setStyleSheet(f"color: {COLORS['success']}; font-size: 11px; font-weight: bold;")
            self.analysis_content_layout.addWidget(ok)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: rgba(100,100,120,0.35);")
        self.analysis_content_layout.addWidget(sep)

        debate_lbl = QLabel("🤖 Model Debate — GLM-5 × gpt-5.4-mini → gpt-5.4 Final Verdict")
        debate_lbl.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 11px; font-weight: bold;"
        )
        self.analysis_content_layout.addWidget(debate_lbl)

        final_verdict = result.get("final_verdict", "")
        debate_box = QTextEdit()
        debate_box.setReadOnly(True)
        debate_box.setFixedHeight(150)
        debate_box.setPlainText(final_verdict or "No verdict returned.")
        debate_box.setStyleSheet(
            f"background: {COLORS['surface']}; color: {COLORS['text']};"
            "border: 1px solid rgba(92,107,192,0.3); border-radius: 8px;"
            "font-family: Consolas; font-size: 11px; padding: 8px;"
        )
        self.analysis_content_layout.addWidget(debate_box)

        verdict = self._extract_verdict(final_verdict)
        verdict_color = {
            "DANGEROUS":    COLORS["danger"],
            "NEEDS REVIEW": COLORS["warning"],
            "SAFE":         COLORS["success"],
        }.get(verdict, COLORS["warning"])

        verdict_lbl = QLabel(f"VERDICT: {verdict}")
        verdict_lbl.setStyleSheet(
            f"color: {verdict_color}; background: rgba(20,20,30,0.5);"
            f"border: 1px solid {verdict_color}; border-radius: 8px;"
            "font-size: 11px; font-weight: bold; padding: 5px 8px;"
        )
        self.analysis_content_layout.addWidget(verdict_lbl)

    def _on_run(self):
        spec = self.spec_input.toPlainText().strip()
        if not spec:
            return
        self.steps.reset()
        self.findings_text.clear()
        self.hardened_text.clear()
        self.voice_btn.setEnabled(False)
        self.run_btn.setEnabled(False)
        self.run_btn.setText("⏳ Running...")

        self._worker = PipelineWorker(
            agent_spec=spec,
            domain=self.domain_combo.currentText(),
        )
        self._worker.step_started.connect(self._on_step)
        self._worker.pipeline_complete.connect(self._on_complete)
        self._worker.pipeline_error.connect(self._on_error)
        self._worker.start()

    def _on_step(self, name, idx):
        names = ["Research", "Adversarial", "Simulation", "Risk", "Voice"]
        if idx > 0:
            self.steps.set_done(names[idx - 1])
        self.steps.set_running(name)

    def _on_complete(self, result):
        self._last_result = result
        self.run_btn.setEnabled(True)
        self.run_btn.setText("🚀 Run Gauntlet")
        self.steps.set_done("Voice")

        assessment = result.get("risk_assessment", {})
        self.risk_widget.update(
            assessment.get("risk_score", 0),
            assessment.get("risk_level", "UNKNOWN"),
        )
        findings = assessment.get("critical_findings", [])
        self.findings_text.setPlainText(
            "\n".join(f"• {f}" for f in findings) or "No critical findings."
        )
        self.hardened_text.setPlainText(
            result.get("hardened_prompt", "") or "No hardened prompt generated."
        )
        if result.get("audio_path"):
            self.voice_btn.setEnabled(True)

    def _on_error(self, msg):
        self.run_btn.setEnabled(True)
        self.run_btn.setText("🚀 Run Gauntlet")
        self.findings_text.setPlainText(f"❌ Pipeline error:\n{msg}")

    def _on_play(self):
        if self._last_result and self._last_result.get("audio_path"):
            from agents.voice_agent import _play_audio
            _play_audio(self._last_result["audio_path"])
