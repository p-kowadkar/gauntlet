import base64
import os
import shutil
import subprocess
import time
from pathlib import Path
from PyQt6.QtCore import QBuffer, QIODevice, Qt
from PyQt6.QtGui import QPixmap
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

    def _linux_tool_capture(self, output_dir: Path) -> QPixmap | None:
        """Fallback capture for Linux sessions where Qt returns an empty pixmap."""
        if os.name == "nt":
            return None

        tmp_path = output_dir / f"_capture_{int(time.time() * 1000)}.png"
        tools = [
            ("gnome-screenshot", ["gnome-screenshot", "-f", str(tmp_path)]),
            ("grim", ["grim", str(tmp_path)]),
        ]

        for tool_name, command in tools:
            if not shutil.which(tool_name):
                continue
            try:
                proc = subprocess.run(
                    command,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=12,
                )
                if proc.returncode != 0:
                    continue
                if not tmp_path.exists() or tmp_path.stat().st_size == 0:
                    continue

                pm = QPixmap(str(tmp_path))
                tmp_path.unlink(missing_ok=True)
                if not pm.isNull() and pm.width() > 0 and pm.height() > 0:
                    return pm
            except Exception:
                continue

        tmp_path.unlink(missing_ok=True)
        return None

    def _on_analyze_screen(self):
        if self._active_worker and self._active_worker.isRunning():
            return

        screen = QApplication.primaryScreen()
        if screen is None:
            self._add_chat_bubble("assistant", "❌ Could not access the primary screen.")
            return

        screenshot = screen.grabWindow(0)

        output_dir = get_output_dir() / "screen"
        output_dir.mkdir(parents=True, exist_ok=True)

        if screenshot.isNull() or screenshot.width() == 0 or screenshot.height() == 0:
            fallback = self._linux_tool_capture(output_dir)
            if fallback is not None:
                screenshot = fallback
            else:
                session = os.getenv("XDG_SESSION_TYPE", "unknown").lower()
                if session == "wayland":
                    self._add_chat_bubble(
                        "assistant",
                        "❌ Screen capture failed on Wayland (empty image from Qt). "
                        "Install `gnome-screenshot` or `grim`, or run under X11/Xorg.",
                    )
                else:
                    self._add_chat_bubble(
                        "assistant",
                        "❌ Screen capture returned an empty image. "
                        "Try installing `gnome-screenshot` and retry.",
                    )
                return

        # Save full-resolution PNG to disk for the user's reference
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
