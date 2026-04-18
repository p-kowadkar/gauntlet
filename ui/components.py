from PyQt6.QtWidgets import QWidget, QLabel, QFrame, QHBoxLayout, QVBoxLayout
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

COLORS = {
    "bg":           "rgba(14, 14, 22, 0.93)",
    "surface":      "rgba(28, 28, 38, 0.88)",
    "border":       "rgba(92, 107, 192, 0.38)",
    "accent":       "#5C6BC0",
    "accent_hover": "#7986CB",
    "text":         "#E8E8F0",
    "text_muted":   "#888899",
    "success":      "#66BB6A",
    "warning":      "#FFA726",
    "danger":       "#EF5350",
}

STEP_NAMES = ["Research", "Adversarial", "Simulation", "Risk", "Voice"]


class StepIndicator(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(6)
        self._labels = {}
        for name in STEP_NAMES:
            lbl = QLabel(f"○ {name}")
            lbl.setStyleSheet(
                f"color: {COLORS['text_muted']}; font-size: 11px;"
                "border: 1px solid rgba(100,100,120,0.3);"
                "border-radius: 6px; padding: 3px 7px;"
            )
            self._labels[name] = lbl
            layout.addWidget(lbl)
        layout.addStretch()

    def set_running(self, name):
        if name in self._labels:
            self._labels[name].setText(f"🔄 {name}")
            self._labels[name].setStyleSheet(
                f"color: {COLORS['accent']}; font-size: 11px;"
                f"border: 1px solid {COLORS['accent']};"
                "border-radius: 6px; padding: 3px 7px;"
            )

    def set_done(self, name):
        if name in self._labels:
            self._labels[name].setText(f"✅ {name}")
            self._labels[name].setStyleSheet(
                f"color: {COLORS['success']}; font-size: 11px;"
                f"border: 1px solid {COLORS['success']};"
                "border-radius: 6px; padding: 3px 7px;"
            )

    def set_error(self, name):
        if name in self._labels:
            self._labels[name].setText(f"❌ {name}")
            self._labels[name].setStyleSheet(
                f"color: {COLORS['danger']}; font-size: 11px;"
                f"border: 1px solid {COLORS['danger']};"
                "border-radius: 6px; padding: 3px 7px;"
            )

    def reset(self):
        for name in STEP_NAMES:
            self._labels[name].setText(f"○ {name}")
            self._labels[name].setStyleSheet(
                f"color: {COLORS['text_muted']}; font-size: 11px;"
                "border: 1px solid rgba(100,100,120,0.3);"
                "border-radius: 6px; padding: 3px 7px;"
            )


class RiskScoreWidget(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(100)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._score_lbl = QLabel("--")
        self._score_lbl.setFont(QFont("Consolas", 52, QFont.Weight.Bold))
        self._score_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._score_lbl.setStyleSheet(f"color: {COLORS['text_muted']};")

        self._level_lbl = QLabel("Run Gauntlet to see results")
        self._level_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._level_lbl.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 12px;"
        )

        layout.addWidget(self._score_lbl)
        layout.addWidget(self._level_lbl)

    def update(self, score: int, level: str):
        self._score_lbl.setText(str(score))
        color = (
            COLORS["success"] if score < 40
            else COLORS["warning"] if score < 70
            else COLORS["danger"]
        )
        self._score_lbl.setStyleSheet(f"color: {color};")
        self._level_lbl.setText(f"Risk Level: {level}")
        self._level_lbl.setStyleSheet(
            f"color: {color}; font-size: 12px; font-weight: bold;"
        )
