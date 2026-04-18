from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QFrame,
    QPushButton, QLineEdit, QLabel, QSizePolicy, QMenu
)

from agents.assist_agent import run_assist, run_assist_with_model
from ui.components import COLORS


class AssistWorker(QThread):
    result_ready = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, query: str, search_enabled: bool, model_override: str = None, vision_data: str = None, parent=None):
        super().__init__(parent)
        self.query = query
        self.search_enabled = search_enabled
        self.model_override = model_override
        self.vision_data = vision_data

    def run(self):
        try:
            if self.model_override:
                result = run_assist_with_model(
                    query=self.query,
                    search_enabled=self.search_enabled,
                    model_override=self.model_override,
                    vision_data=self.vision_data,
                )
            else:
                result = run_assist(
                    query=self.query,
                    search_enabled=self.search_enabled,
                    vision_data=self.vision_data,
                )
            self.result_ready.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class AssistPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._active_worker = None
        self._setup_ui()

    def _setup_ui(self):
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(12, 8, 12, 8)
        self._root.setSpacing(8)

        self._root.addLayout(self._top_controls_row())
        self._root.addWidget(self._chat_area(), 1)
        self._root.addLayout(self._input_row())

    def _top_controls_row(self):
        row = QHBoxLayout()
        row.setSpacing(8)

        self.search_toggle = QPushButton("🔍 Search: ON")
        self.search_toggle.setCheckable(True)
        self.search_toggle.setChecked(True)
        self.search_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.search_toggle.clicked.connect(self._update_search_toggle_style)
        row.addWidget(self.search_toggle)

        self.deep_toggle = QPushButton("📚 Deep")
        self.deep_toggle.setCheckable(True)
        self.deep_toggle.setEnabled(False)
        self.deep_toggle.setToolTip("Coming soon: You.com Research API")
        self.deep_toggle.setStyleSheet(
            f"background: rgba(80,80,100,0.2); color: {COLORS['text_muted']};"
            "border: 1px solid rgba(100,100,120,0.3); border-radius: 7px; padding: 6px 10px;"
        )
        row.addWidget(self.deep_toggle)
        row.addStretch()

        self._update_search_toggle_style()
        return row

    def _chat_area(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border: none; background: transparent;")
        self._chat_scroll = scroll

        content = QWidget()
        self._chat_layout = QVBoxLayout(content)
        self._chat_layout.setContentsMargins(0, 4, 0, 4)
        self._chat_layout.setSpacing(8)
        self._chat_layout.addStretch()
        scroll.setWidget(content)
        return scroll

    def _input_row(self):
        row = QHBoxLayout()
        row.setSpacing(8)

        self.input = QLineEdit()
        self.input.setPlaceholderText("Ask Gauntlet Assist...")
        self.input.returnPressed.connect(self._on_send)
        self.input.setStyleSheet(
            f"background: {COLORS['surface']}; color: {COLORS['text']};"
            "border: 1px solid rgba(92,107,192,0.3); border-radius: 8px;"
            "padding: 8px 10px; font-family: Consolas; font-size: 12px;"
        )
        row.addWidget(self.input, 1)

        self.send_btn = QPushButton("Send ➤")
        self.send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_btn.setMinimumHeight(34)
        self.send_btn.setStyleSheet(
            f"background: {COLORS['accent']}; color: white; border: none;"
            "border-radius: 8px; padding: 6px 14px; font-weight: bold; font-size: 12px;"
        )
        self.send_btn.clicked.connect(self._on_send)
        row.addWidget(self.send_btn)
        return row

    def _update_search_toggle_style(self):
        if self.search_toggle.isChecked():
            self.search_toggle.setText("🔍 Search: ON")
            self.search_toggle.setStyleSheet(
                "background: rgba(102,187,106,0.18); color: #A5D6A7;"
                "border: 1px solid rgba(102,187,106,0.45); border-radius: 7px; padding: 6px 10px;"
            )
        else:
            self.search_toggle.setText("🔍 Search: OFF")
            self.search_toggle.setStyleSheet(
                f"background: rgba(80,80,100,0.2); color: {COLORS['text_muted']};"
                "border: 1px solid rgba(100,100,120,0.3); border-radius: 7px; padding: 6px 10px;"
            )

    def _add_chat_bubble(self, role: str, text: str, model_used: str = None, query: str = None, search_enabled: bool = True):
        wrapper = QWidget()
        row = QHBoxLayout(wrapper)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)

        bubble = QFrame()
        bubble.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        bubble_layout = QVBoxLayout(bubble)
        bubble_layout.setContentsMargins(10, 8, 10, 8)
        bubble_layout.setSpacing(6)

        text_lbl = QLabel(text)
        text_lbl.setWordWrap(True)
        text_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        text_lbl.setStyleSheet("font-family: Consolas; font-size: 12px;")
        bubble_layout.addWidget(text_lbl)

        if role == "user":
            bubble.setStyleSheet(
                f"background: {COLORS['accent']}; color: white; border-radius: 10px;"
                "padding: 2px;"
            )
            row.addStretch()
            row.addWidget(bubble, 0, Qt.AlignmentFlag.AlignRight)
        else:
            bubble.setStyleSheet(
                f"background: {COLORS['surface']}; color: {COLORS['text']};"
                "border: 1px solid rgba(92,107,192,0.25); border-radius: 10px; padding: 2px;"
            )
            if model_used:
                footer = QHBoxLayout()
                footer.setContentsMargins(0, 0, 0, 0)
                footer.setSpacing(6)
                model_lbl = QLabel(self._model_badge(model_used))
                model_lbl.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 10px;")
                footer.addWidget(model_lbl)
                footer.addStretch()

                regen = QPushButton("↺ Regenerate")
                regen.setCursor(Qt.CursorShape.PointingHandCursor)
                regen.setStyleSheet(
                    "background: rgba(92,107,192,0.22); color: #CFD8FF;"
                    "border: 1px solid rgba(92,107,192,0.45); border-radius: 6px;"
                    "padding: 3px 8px; font-size: 10px;"
                )
                regen.clicked.connect(
                    lambda _, btn=regen, q=query or "", s=search_enabled: self._show_regen_menu(btn, q, s)
                )
                footer.addWidget(regen)
                bubble_layout.addLayout(footer)

            row.addWidget(bubble, 0, Qt.AlignmentFlag.AlignLeft)
            row.addStretch()

        self._chat_layout.insertWidget(self._chat_layout.count() - 1, wrapper)
        QTimer.singleShot(0, self._scroll_to_bottom)
        return wrapper

    def _model_badge(self, model_used: str) -> str:
        if "Kimi K2.5" in model_used:
            return "⚡ Kimi K2.5 (Baseten)"
        if "GLM-5" in model_used:
            return "⚡ GLM-5 (Baseten)"
        if "gpt-5.4-mini" in model_used:
            return "🔄 gpt-5.4-mini"
        return model_used

    def _scroll_to_bottom(self):
        bar = self._chat_scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _set_busy(self, busy: bool):
        self.input.setEnabled(not busy)
        self.send_btn.setEnabled(not busy)

    def _on_send(self):
        if self._active_worker and self._active_worker.isRunning():
            return
        query = self.input.text().strip()
        if not query:
            return

        search_enabled = self.search_toggle.isChecked()
        self._add_chat_bubble("user", query)
        self.input.clear()
        placeholder = self._add_chat_bubble("assistant", "⏳ Thinking...")
        self._start_worker(query, search_enabled, placeholder, model_override=None, vision_data=None)

    def _start_worker(self, query: str, search_enabled: bool, placeholder_widget: QWidget, model_override: str = None, vision_data: str = None):
        self._set_busy(True)
        self._active_worker = AssistWorker(
            query=query,
            search_enabled=search_enabled,
            model_override=model_override,
            vision_data=vision_data,
            parent=self,
        )
        self._active_worker.result_ready.connect(
            lambda result, w=placeholder_widget, q=query, s=search_enabled: self._on_result(result, w, q, s)
        )
        self._active_worker.error.connect(
            lambda msg, w=placeholder_widget: self._on_error(msg, w)
        )
        self._active_worker.finished.connect(lambda: self._set_busy(False))
        self._active_worker.start()

    def _remove_chat_widget(self, widget: QWidget):
        self._chat_layout.removeWidget(widget)
        widget.deleteLater()
        QTimer.singleShot(0, self._scroll_to_bottom)

    def _on_result(self, result: dict, placeholder_widget: QWidget, query: str, search_enabled: bool):
        self._remove_chat_widget(placeholder_widget)
        self._add_chat_bubble(
            "assistant",
            result.get("content", ""),
            model_used=result.get("model_used", ""),
            query=query,
            search_enabled=search_enabled,
        )

    def _on_error(self, msg: str, placeholder_widget: QWidget):
        self._remove_chat_widget(placeholder_widget)
        self._add_chat_bubble("assistant", f"❌ {msg}")

    def _show_regen_menu(self, anchor_button: QPushButton, query: str, search_enabled: bool):
        if self._active_worker and self._active_worker.isRunning():
            return
        menu = QMenu(self)
        baseten_action = menu.addAction("With GLM-5 (Baseten)")
        fallback_action = menu.addAction("With gpt-5.4-mini")
        chosen = menu.exec(anchor_button.mapToGlobal(anchor_button.rect().bottomLeft()))
        if not chosen:
            return

        if chosen == baseten_action:
            model_override = "baseten"
        elif chosen == fallback_action:
            model_override = "fallback"
        else:
            return

        placeholder = self._add_chat_bubble("assistant", "⏳ Thinking...")
        self._start_worker(
            query=query,
            search_enabled=search_enabled,
            placeholder_widget=placeholder,
            model_override=model_override,
            vision_data=None,
        )
