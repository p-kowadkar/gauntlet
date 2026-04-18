import json
import requests
from pathlib import Path
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QLabel, QLineEdit, QPushButton, QGroupBox, QGridLayout,
    QSlider, QMessageBox, QFileDialog
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from config import (
    CONFIG_FILE, ENV_FILE, read_env, write_env,
    BASETEN_BASE_URL, BASETEN_MODEL_SLUG, YOUCOM_SEARCH_URL,
    OPENAI_FALLBACK_MODEL
)
from ui.components import COLORS

_API_KEYS = [
    ("OpenAI",   "OPENAI_API_KEY",  "sk-..."),
    ("You.com",  "YOUCOM_API_KEY",  "yk-..."),
    ("Baseten",  "BASETEN_API_KEY", "Baseten API key"),
    ("Veris AI", "VERIS_API_KEY",   "Optional — CLI auth via `veris login` also works"),
]


class _ValidateWorker(QThread):
    """Runs a real API ping off the main thread. Emits (ok, message)."""
    done = pyqtSignal(bool, str)

    def __init__(self, service: str, key: str, parent=None):
        super().__init__(parent)
        self.service = service
        self.key = key

    def run(self):
        try:
            ok, msg = _ping(self.service, self.key)
        except Exception as e:
            ok, msg = False, str(e)
        self.done.emit(ok, msg)


def _ping(service: str, key: str) -> tuple[bool, str]:
    """Synchronous API ping -- called from worker thread."""

    if service == "OpenAI":
        if not key:
            return False, "No key provided"
        import openai
        client = openai.OpenAI(api_key=key)
        # Ping with an actual completion to our fallback model (gpt-5.4-mini).
        # max_completion_tokens=1 -- costs fractions of a cent, confirms
        # both the key AND access to the GPT-5.4 model family we use.
        resp = client.chat.completions.create(
            model=OPENAI_FALLBACK_MODEL,
            messages=[{"role": "user", "content": "hi"}],
            max_completion_tokens=1,
        )
        model = resp.model or OPENAI_FALLBACK_MODEL
        return True, f"Connected ✅  (model: {model})"

    if service == "You.com":
        if not key:
            return False, "No key provided"
        resp = requests.get(
            YOUCOM_SEARCH_URL,
            params={"query": "test", "count": 1},
            headers={"X-API-Key": key},
            timeout=10,
        )
        if resp.status_code == 401:
            return False, "Invalid API key (401)"
        if resp.status_code == 403:
            return False, "Forbidden — key may be inactive (403)"
        resp.raise_for_status()
        hits = len(resp.json().get("results", {}).get("web", []))
        return True, f"Connected ✅  ({hits} result(s) returned)"

    if service == "Baseten":
        if not key:
            return False, "No key provided"
        import openai
        client = openai.OpenAI(base_url=BASETEN_BASE_URL, api_key=key)
        resp = client.chat.completions.create(
            model=BASETEN_MODEL_SLUG,
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=1,
        )
        model = resp.model or BASETEN_MODEL_SLUG
        return True, f"Connected ✅  (model: {model})"

    if service == "Veris AI":
        try:
            from veris import Veris
            if key:
                client = Veris(api_key=key)
            else:
                client = Veris()  # picks up ~/.veris/config.yaml from `veris login`
            envs = client.environments.list()
            count = len(envs) if envs else 0
            return True, f"Connected ✅  ({count} environment(s) found)"
        except ImportError:
            pass

        veris_config = Path.home() / ".veris" / "config.yaml"
        if veris_config.exists():
            content = veris_config.read_text()
            if any(k in content for k in ("token", "api_key", "access")):
                return True, "CLI auth found ✅  (token from `veris login` present)"
            return False, "~/.veris/config.yaml found but no token — run `veris login`"

        return False, "Not configured — run `veris login` or provide an API key"

    return False, f"Unknown service: {service}"


class SettingsDialog(QDialog):
    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.config = config.copy()
        self._env_values = read_env()
        self.setWindowTitle("⚙️  Settings")
        self.setMinimumSize(580, 460)
        self.setModal(True)
        self._key_inputs = {}
        self._validate_btns = {}
        self._workers = {}
        self._setup_ui()
        self._apply_style()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._api_keys_tab(),   "🔑 API Keys")
        self.tabs.addTab(self._appearance_tab(), "🎨 Appearance")
        self.tabs.addTab(self._workspace_tab(),  "📁 Workspace")
        layout.addWidget(self.tabs)

        footer = QHBoxLayout()
        footer.addStretch()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        footer.addWidget(cancel)
        save = QPushButton("💾 Save")
        save.setDefault(True)
        save.setStyleSheet(
            f"background: {COLORS['accent']}; color: white; font-weight: bold;"
            "border: none; border-radius: 6px; padding: 8px 20px;"
        )
        save.clicked.connect(self._save)
        footer.addWidget(save)
        layout.addLayout(footer)

    def _api_keys_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(10)

        for display_name, env_key, placeholder in _API_KEYS:
            group = QGroupBox(display_name)
            group.setFlat(True)
            row = QHBoxLayout(group)

            inp = QLineEdit()
            inp.setEchoMode(QLineEdit.EchoMode.Password)
            inp.setPlaceholderText(placeholder)
            inp.setText(self._env_values.get(env_key, ""))
            self._key_inputs[env_key] = inp
            row.addWidget(inp)

            eye = QPushButton("👁")
            eye.setFixedWidth(32)
            eye.setCheckable(True)
            eye.setToolTip("Show / hide key")
            eye.toggled.connect(
                lambda checked, i=inp: i.setEchoMode(
                    QLineEdit.EchoMode.Normal if checked
                    else QLineEdit.EchoMode.Password
                )
            )
            row.addWidget(eye)

            val_btn = QPushButton("✓ Test")
            val_btn.setFixedWidth(60)
            val_btn.setToolTip(f"Ping {display_name} API to verify key")
            val_btn.clicked.connect(
                lambda _, dn=display_name, ek=env_key: self._run_validate(dn, ek)
            )
            self._validate_btns[env_key] = val_btn
            row.addWidget(val_btn)

            layout.addWidget(group)

        env_label = QLabel(f"Stored in: {ENV_FILE}")
        env_label.setStyleSheet("color: #555; font-size: 10px; padding: 4px 2px;")
        layout.addWidget(env_label)

        note = QLabel("VoiceRun: production voice delivery — voicerun.com/developers")
        note.setStyleSheet("color: #444; font-size: 10px; padding: 2px;")
        layout.addWidget(note)
        layout.addStretch()
        return widget

    def _run_validate(self, display_name: str, env_key: str):
        key = self._key_inputs[env_key].text().strip()
        btn = self._validate_btns[env_key]

        btn.setText("⏳")
        btn.setEnabled(False)
        btn.setStyleSheet("background: #333; color: #aaa; border-radius: 6px; padding: 6px;")

        worker = _ValidateWorker(display_name, key, parent=self)
        self._workers[env_key] = worker

        def on_done(ok: bool, msg: str):
            if ok:
                btn.setText("✅")
                btn.setStyleSheet(
                    f"background: rgba(102,187,106,0.2); color: {COLORS['success']};"
                    "border: 1px solid rgba(102,187,106,0.5); border-radius: 6px; padding: 6px;"
                )
                QMessageBox.information(self, f"{display_name} — Connected", msg)
            else:
                btn.setText("❌")
                btn.setStyleSheet(
                    f"background: rgba(239,83,80,0.15); color: {COLORS['danger']};"
                    "border: 1px solid rgba(239,83,80,0.4); border-radius: 6px; padding: 6px;"
                )
                QMessageBox.warning(self, f"{display_name} — Failed", msg)
            btn.setEnabled(True)

        worker.done.connect(on_done)
        worker.start()

    def _appearance_tab(self):
        widget = QWidget()
        layout = QGridLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.addWidget(QLabel("Overlay Opacity:"), 0, 0)
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(50, 100)
        slider.setValue(int(self.config.get("OVERLAY_OPACITY", 0.92) * 100))
        slider.valueChanged.connect(
            lambda v: self.config.update({"OVERLAY_OPACITY": v / 100})
        )
        layout.addWidget(slider, 0, 1)
        return widget

    def _workspace_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(12)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.addWidget(QLabel("Output Directory"))
        row = QHBoxLayout()
        self._output_dir_input = QLineEdit()
        self._output_dir_input.setPlaceholderText(str(Path.home() / ".gauntlet"))
        self._output_dir_input.setText(
            self.config.get("OUTPUT_DIR", str(Path.home() / ".gauntlet"))
        )
        self._output_dir_input.textChanged.connect(
            lambda v: self.config.update({"OUTPUT_DIR": v})
        )
        row.addWidget(self._output_dir_input)
        browse = QPushButton("📂 Browse")
        browse.setFixedWidth(90)
        browse.clicked.connect(self._browse_output_dir)
        row.addWidget(browse)
        layout.addLayout(row)
        note = QLabel("Audio briefings, JSON reports, and screenshots saved here.")
        note.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(note)
        layout.addStretch()
        return widget

    def _browse_output_dir(self):
        current = self._output_dir_input.text() or str(Path.home())
        chosen = QFileDialog.getExistingDirectory(self, "Select Output Directory", current)
        if chosen:
            self._output_dir_input.setText(chosen)
            self.config["OUTPUT_DIR"] = chosen

    def _save(self):
        env_updates = {
            env_key: self._key_inputs[env_key].text().strip()
            for _, env_key, _ in _API_KEYS
        }
        write_env(env_updates)
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(self.config, indent=2))
        self.accept()

    def _apply_style(self):
        self.setStyleSheet(f"""
            QDialog {{ background: #14141A; color: #E8E8F0; }}
            QTabWidget::pane {{
                border: 1px solid rgba(92,107,192,0.3);
                border-radius: 8px; background: #1E1E28;
            }}
            QTabBar::tab {{
                background: #2A2A38; color: #888899;
                border-radius: 6px; padding: 8px 16px; margin-right: 4px;
            }}
            QTabBar::tab:selected {{ background: {COLORS['accent']}; color: white; }}
            QGroupBox {{
                color: #E8E8F0; font-size: 12px; font-weight: bold;
                border: 1px solid rgba(92,107,192,0.25);
                border-radius: 8px; margin-top: 6px; padding-top: 10px;
            }}
            QLineEdit {{
                background: #0F0F18; color: #E8E8F0;
                border: 1px solid rgba(92,107,192,0.3);
                border-radius: 6px; padding: 6px 10px; font-family: Consolas;
            }}
            QPushButton {{
                background: #2A2A38; color: #E8E8F0;
                border: 1px solid rgba(92,107,192,0.3);
                border-radius: 6px; padding: 6px 12px;
            }}
            QPushButton:hover {{ background: #3A3A4A; }}
            QPushButton:checked {{ background: rgba(92,107,192,0.4); }}
        """)
