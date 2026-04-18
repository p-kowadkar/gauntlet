import base64
import time
from PyQt6.QtCore import QBuffer, QIODevice, Qt
from PyQt6.QtWidgets import QPushButton, QHBoxLayout, QApplication

from config import get_output_dir
from ui.assist_panel import AssistPanel
from ui.components import COLORS


class ScreenPanel(AssistPanel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._insert_screen_row()

    def _insert_screen_row(self):
        row = QHBoxLayout()
        row.setSpacing(8)

        self.analyze_btn = QPushButton("📸 Analyze Screen")
        self.analyze_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.analyze_btn.setMinimumHeight(34)
        self.analyze_btn.setStyleSheet(
            f"background: {COLORS['accent']}; color: white; border: none;"
            "border-radius: 8px; padding: 6px 14px; font-weight: bold; font-size: 12px;"
        )
        self.analyze_btn.clicked.connect(self._on_analyze_screen)
        row.addWidget(self.analyze_btn)
        row.addStretch()

        self._root.insertLayout(0, row)

    def _on_analyze_screen(self):
        if self._active_worker and self._active_worker.isRunning():
            return

        screen = QApplication.primaryScreen()
        if screen is None:
            self._add_chat_bubble("assistant", "❌ Could not access the primary screen.")
            return

        screenshot = screen.grabWindow(0)

        # Save full-resolution PNG to disk for the user's reference
        output_dir = get_output_dir() / "screen"
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = int(time.time())
        file_path = output_dir / f"screen_{timestamp}.png"
        screenshot.save(str(file_path), "PNG")

        # Scale down for API payload -- full-res PNG encodes to 3-5MB base64,
        # which blows past the request body limit. Scale to max 1280px wide,
        # encode as JPEG at 80% quality → ~100-250KB base64, well within limits.
        MAX_WIDTH = 1280
        if screenshot.width() > MAX_WIDTH:
            screenshot = screenshot.scaledToWidth(
                MAX_WIDTH,
                Qt.TransformationMode.SmoothTransformation
            )

        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        screenshot.save(buffer, "JPEG", quality=80)
        img_bytes = buffer.data().data()
        img_b64 = base64.b64encode(img_bytes).decode()

        query = self.input.text().strip() or "Describe what you see on this screen in detail"
        self.input.clear()
        search_enabled = self.search_toggle.isChecked()

        self._add_chat_bubble("user", query)
        placeholder = self._add_chat_bubble("assistant", "⏳ Analyzing screen...")
        self._start_worker(
            query=query,
            search_enabled=search_enabled,
            placeholder_widget=placeholder,
            model_override=None,
            vision_data=img_b64,
        )
