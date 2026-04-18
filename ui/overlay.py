import json
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QStackedWidget, QFrame, QApplication
)
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QMouseEvent

from config import OVERLAY_WIDTH, OVERLAY_HEIGHT, CONFIG_FILE
from ui.components import COLORS
from ui.assist_panel import AssistPanel
from ui.screen_panel import ScreenPanel
from ui.gauntlet_panel import GauntletPanel
from ui.settings_dialog import SettingsDialog


class GauntletOverlay(QWidget):
    def __init__(self):
        super().__init__()
        self._dragging = False
        self._offset   = QPoint()
        self._config   = self._load_config()
        self._setup_window()
        self._setup_ui()
        self._show_tab(2)

    def _setup_window(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(OVERLAY_WIDTH, OVERLAY_HEIGHT)
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.width() - OVERLAY_WIDTH - 20, 80)

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        self.container = QFrame()
        self.container.setObjectName("container")
        self.container.setStyleSheet("""
            #container {
                background: rgba(14, 14, 22, 0.93);
                border-radius: 14px;
                border: 1px solid rgba(92, 107, 192, 0.42);
            }
        """)
        cl = QVBoxLayout(self.container)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)
        cl.addWidget(self._top_bar())
        cl.addWidget(self._tab_bar())
        cl.addWidget(self._content(), 1)
        root.addWidget(self.container)

    def _top_bar(self):
        bar = QWidget()
        bar.setFixedHeight(38)
        bar.setStyleSheet(
            "background: rgba(20,20,30,0.6); border-radius: 14px 14px 0 0;"
        )
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(14, 0, 10, 0)

        title = QLabel("⚔️ Gauntlet")
        title.setStyleSheet(
            "color: #9FA8DA; font-size: 13px; font-weight: bold; border: none;"
        )
        layout.addWidget(title)
        layout.addStretch()

        close = QPushButton("✕")
        close.setFixedSize(22, 22)
        close.setStyleSheet(
            "background: rgba(239,83,80,0.7); color: white; border: none;"
            "border-radius: 4px; font-size: 11px; font-weight: bold;"
        )
        close.clicked.connect(QApplication.instance().quit)
        layout.addWidget(close)
        return bar

    def _tab_bar(self):
        bar = QWidget()
        bar.setFixedHeight(38)
        bar.setStyleSheet(
            "background: rgba(18,18,26,0.8);"
            "border-bottom: 1px solid rgba(92,107,192,0.2);"
        )
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(4)

        self._tab_btns = []
        for i, label in enumerate(["Assist", "Screen", "Gauntlet", "⚙"]):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setFixedHeight(28)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(
                "QPushButton { background: transparent; color: #888899;"
                "border: none; border-radius: 6px; font-size: 12px; padding: 0 10px; }"
                "QPushButton:checked { background: rgba(92,107,192,0.3); color: #E8E8F0; }"
                "QPushButton:hover { background: rgba(92,107,192,0.15); color: #E8E8F0; }"
            )
            btn.clicked.connect(lambda _, idx=i: self._show_tab(idx))
            self._tab_btns.append(btn)
            layout.addWidget(btn)
        layout.addStretch()
        return bar

    def _content(self):
        self._stack = QStackedWidget()
        self._assist_panel = AssistPanel()
        self._stack.addWidget(self._assist_panel)   # index 0

        self._screen_panel = ScreenPanel()
        self._stack.addWidget(self._screen_panel)   # index 1

        self._gauntlet_panel = GauntletPanel()
        self._stack.addWidget(self._gauntlet_panel)  # index 2
        self._stack.addWidget(QWidget())              # index 3 (settings slot)
        return self._stack

    def _show_tab(self, idx):
        for i, btn in enumerate(self._tab_btns):
            btn.setChecked(i == idx)
        if idx == 3:
            self._tab_btns[2].setChecked(True)
            dialog = SettingsDialog(config=self._config, parent=self)
            if dialog.exec():
                self._config = dialog.config
                self.setWindowOpacity(self._config.get("OVERLAY_OPACITY", 0.92))
        else:
            self._stack.setCurrentIndex(idx)

    def _load_config(self):
        if CONFIG_FILE.exists():
            try:
                return json.loads(CONFIG_FILE.read_text())
            except Exception:
                pass
        return {}

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._offset = event.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._dragging and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._offset)

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._dragging = False
