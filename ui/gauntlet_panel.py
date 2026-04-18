from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit,
    QComboBox, QPushButton, QScrollArea
)
from PyQt6.QtCore import Qt

from config import DOMAINS
from ui.components import COLORS, StepIndicator, RiskScoreWidget
from utils.thread_worker import PipelineWorker


class GauntletPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker      = None
        self._last_result = None
        self._setup_ui()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 8, 12, 8)
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
