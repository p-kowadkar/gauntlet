import copy
import json
import re
import shutil
from pathlib import Path
from typing import Any

import requests
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSlider,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
    QHeaderView,
)

from config import CONFIG_FILE, ENV_FILE, YOUCOM_SEARCH_URL, read_env, write_env
from core.model_config import DEFAULT_ROLES, FALLBACK_CHAINS
from core.model_database import PROVIDER_REGISTRY, get_base_url, get_effort_options
from ui.components import COLORS


BUILTIN_PROVIDER_PILLS = [
    "openai",
    "anthropic",
    "google",
    "xai",
    "deepseek",
    "openrouter",
    "baseten",
]

ROLE_ORDER = [
    "primary_llm",
    "adversarial",
    "risk",
    "code_analysis",
    "final_judge",
    "classifier",
    "vision",
    "tts",
    "stt",
    "search",
]

ROLE_LABELS = {
    "primary_llm": "Primary LLM",
    "adversarial": "Adversarial",
    "risk": "Risk",
    "code_analysis": "Code Analysis",
    "final_judge": "Final Judge",
    "classifier": "Classifier",
    "vision": "Vision",
    "tts": "TTS",
    "stt": "STT",
    "search": "Search",
}

PROVIDER_ENV_KEYS = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "google": "GOOGLE_API_KEY",
    "xai": "XAI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "baseten": "BASETEN_API_KEY",
    "youcom": "YOUCOM_API_KEY",
    "firecrawl": "FIRECRAWL_API_KEY",
    "brave": "BRAVE_API_KEY",
    "exa": "EXA_API_KEY",
    "e2b": "E2B_API_KEY",
    "veris": "VERIS_API_KEY",
}

EXTRA_API_ROWS = [
    ("You.com", "youcom", "YOUCOM_API_KEY", "yk-..."),
    ("Firecrawl", "firecrawl", "FIRECRAWL_API_KEY", "fc-..."),
    ("Brave Search", "brave", "BRAVE_API_KEY", "brv-..."),
    ("Exa", "exa", "EXA_API_KEY", "exa-..."),
    ("E2B", "e2b", "E2B_API_KEY", "e2b_..."),
    ("Veris AI", "veris", "VERIS_API_KEY", "Optional — `veris login` also works"),
]

SEARCH_PROVIDERS = ["youcom", "firecrawl", "brave", "exa"]


def _dedupe_keep_order(items: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        normalized = str(item).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        out.append(normalized)
    return out


def _normalize_model_list(raw: Any) -> list[str]:
    if isinstance(raw, str):
        items = [x.strip() for x in raw.split(",")]
        return _dedupe_keep_order(items)
    if isinstance(raw, list):
        items = [str(x).strip() for x in raw]
        return _dedupe_keep_order(items)
    return []


def _provider_display(provider_id: str, custom_providers: list[dict[str, Any]] | None = None) -> str:
    provider_id = str(provider_id or "").strip()
    if custom_providers:
        for cp in custom_providers:
            if cp.get("id") == provider_id:
                display = str(cp.get("display", "")).strip()
                if display:
                    return display
                break
    if provider_id in PROVIDER_REGISTRY:
        return str(PROVIDER_REGISTRY[provider_id].get("display", provider_id.title()))
    overrides = {
        "youcom": "You.com",
        "firecrawl": "Firecrawl",
        "brave": "Brave Search",
        "exa": "Exa",
        "e2b": "E2B",
        "veris": "Veris AI",
    }
    if provider_id in overrides:
        return overrides[provider_id]
    return provider_id.replace("_", " ").title()


def _provider_env_key(provider_id: str, custom_providers: list[dict[str, Any]] | None = None) -> str:
    provider_id = str(provider_id or "").strip().lower()
    if custom_providers:
        for cp in custom_providers:
            if cp.get("id") == provider_id:
                explicit = str(cp.get("api_key_env", "")).strip()
                if explicit:
                    return explicit
                break
    if provider_id in PROVIDER_ENV_KEYS:
        return PROVIDER_ENV_KEYS[provider_id]
    return f"{provider_id.upper()}_API_KEY"


def _parse_custom_provider_id(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", (name or "").strip()).strip("_").lower()
    if not cleaned:
        return ""
    if not cleaned.startswith("custom_"):
        cleaned = f"custom_{cleaned}"
    return cleaned


def _collect_registry_models(provider_id: str, role: str | None = None) -> list[str]:
    provider = PROVIDER_REGISTRY.get(provider_id, {})
    if not provider:
        return []

    if role == "tts":
        tts = provider.get("tts")
        if isinstance(tts, list):
            return _dedupe_keep_order([str(x) for x in tts])
        if isinstance(tts, dict):
            model = str(tts.get("model", "")).strip()
            return [model] if model else []

    if role == "stt":
        stt = provider.get("stt")
        if isinstance(stt, list):
            return _dedupe_keep_order([str(x) for x in stt])
        if isinstance(stt, dict):
            model = str(stt.get("model", "")).strip()
            return [model] if model else []
        return []

    models: list[str] = []
    families = provider.get("families", {})
    if isinstance(families, dict):
        for fam in families.values():
            if isinstance(fam, dict):
                models.extend([str(x) for x in fam.get("models", [])])
    model_dict = provider.get("models", {})
    if isinstance(model_dict, dict):
        models.extend([str(x) for x in model_dict.keys()])
    free_models = provider.get("free_models", [])
    if isinstance(free_models, list):
        models.extend([str(x) for x in free_models])
    default_model = str(provider.get("default", "")).strip()
    if default_model:
        models.append(default_model)
    return _dedupe_keep_order(models)


def _ping(service_id: str, key: str, meta: dict[str, Any] | None = None) -> tuple[bool, str]:
    service_id = str(service_id or "").strip().lower()
    key = (key or "").strip()
    meta = meta or {}
    if service_id in {"openai", "anthropic", "google", "xai", "deepseek", "openrouter", "baseten", "youcom", "firecrawl", "brave", "exa", "e2b", "veris", "custom_openai"} and not key:
        return False, "No key provided"

    if service_id == "openai":
        import openai

        model = str(PROVIDER_REGISTRY.get("openai", {}).get("default", "gpt-5.4-mini"))
        client = openai.OpenAI(api_key=key)
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Respond with OK"}],
            max_completion_tokens=24,
        )
        return True, f"Connected ✅  (model: {resp.model or model})"

    if service_id in {"baseten", "xai", "deepseek", "openrouter", "custom_openai"}:
        import openai

        if service_id == "custom_openai":
            base_url = str(meta.get("base_url", "")).strip()
            model = str(meta.get("model", "")).strip()
            label = str(meta.get("label", "custom provider")).strip()
        else:
            base_url = get_base_url(service_id)
            model = str(PROVIDER_REGISTRY.get(service_id, {}).get("default", "")).strip()
            if service_id == "openrouter":
                model = model or "openrouter/free"
            label = _provider_display(service_id)
        if not model:
            model = "openrouter/free" if service_id == "openrouter" else "gpt-4o-mini"
        client = openai.OpenAI(base_url=base_url, api_key=key)
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=8,
        )
        return True, f"Connected ✅  ({label} · model: {resp.model or model})"

    if service_id == "anthropic":
        import anthropic

        client = anthropic.Anthropic(api_key=key)
        resp = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=5,
            messages=[{"role": "user", "content": "hi"}],
        )
        if getattr(resp, "id", ""):
            return True, "Connected ✅  (anthropic message API reachable)"
        return True, "Connected ✅"

    if service_id == "google":
        import google.generativeai as genai

        genai.configure(api_key=key)
        models = list(genai.list_models())
        return True, f"Connected ✅  ({len(models)} model(s) visible)"

    if service_id == "youcom":
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

    if service_id in {"firecrawl", "brave", "exa"}:
        if len(key) < 8:
            return False, "Key appears too short"
        return True, "Key format looks valid ✅"

    if service_id == "e2b":
        try:
            from e2b_code_interpreter import Sandbox

            sandboxes = Sandbox.list(api_key=key)
            count = len(sandboxes) if sandboxes else 0
            return True, f"Connected ✅  ({count} sandbox(es) listed)"
        except ImportError:
            if len(key) >= 16:
                return True, "Key saved ✅  (install e2b-code-interpreter to run full validation)"
            return False, "Install e2b-code-interpreter for full validation"

    if service_id == "veris":
        try:
            from veris import Veris

            client = Veris(api_key=key) if key else Veris()
            envs = client.environments.list()
            count = len(envs) if envs else 0
            return True, f"Connected ✅  ({count} environment(s) found)"
        except ImportError:
            if key and len(key) >= 8:
                return True, "Key saved ✅  (install veris-ai for full validation)"
            veris_config = Path.home() / ".veris" / "config.yaml"
            if veris_config.exists():
                return True, "CLI auth found ✅"
            return False, "Not configured — run `veris login` or install veris-ai"

    return False, f"Unknown service: {service_id}"


class _ValidateWorker(QThread):
    done = pyqtSignal(bool, str)

    def __init__(self, service_id: str, key: str, meta: dict[str, Any] | None = None, parent=None):
        super().__init__(parent)
        self.service_id = service_id
        self.key = key
        self.meta = meta or {}

    def run(self):
        try:
            ok, msg = _ping(self.service_id, self.key, self.meta)
        except Exception as e:
            ok, msg = False, str(e)
        self.done.emit(ok, msg)


class SettingsDialog(QDialog):
    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self._raw_config = config if isinstance(config, dict) else {}
        self.config = self._normalize_config(self._raw_config)
        self._env_values = read_env()
        self._custom_env_updates: dict[str, str] = {}
        self._linked_inputs: dict[str, list[QLineEdit]] = {}
        self._workers: dict[int, _ValidateWorker] = {}

        self._role_provider_boxes: dict[str, QComboBox] = {}
        self._role_model_boxes: dict[str, QComboBox] = {}
        self._role_effort_boxes: dict[str, QComboBox] = {}

        self._provider_buttons: dict[str, QPushButton] = {}
        self._selected_provider_id: str = "openai"
        self._provider_selected_family: dict[str, str] = {}
        self._provider_selected_model: dict[str, str] = {}
        self._editing_custom_provider_id: str | None = None

        self._local_models: list[tuple[str, str, str]] = []

        self.setWindowTitle("⚙️  Settings")
        self.setMinimumSize(980, 720)
        self.setModal(True)

        self._setup_ui()
        self._refresh_local_models()
        self._refresh_provider_pills()
        self._refresh_role_table()
        self._on_mode_changed()
        self._apply_style()

    def _normalize_config(self, raw: dict[str, Any]) -> dict[str, Any]:
        cfg = copy.deepcopy(raw if isinstance(raw, dict) else {})
        output_default = str(Path.home() / ".gauntlet")

        output_dir = cfg.get("output_dir", cfg.get("OUTPUT_DIR", output_default))
        output_dir = str(output_dir).strip() or output_default
        cfg["output_dir"] = output_dir
        cfg["OUTPUT_DIR"] = output_dir

        overlay = cfg.get("overlay")
        if not isinstance(overlay, dict):
            overlay = {}
        try:
            opacity = float(overlay.get("opacity", cfg.get("OVERLAY_OPACITY", 0.92)))
        except (TypeError, ValueError):
            opacity = 0.92
        opacity = max(0.0, min(1.0, opacity))
        overlay["opacity"] = opacity
        cfg["overlay"] = overlay
        cfg["OVERLAY_OPACITY"] = opacity

        model_cfg = cfg.get("model_config")
        if not isinstance(model_cfg, dict):
            model_cfg = {}
        mode = str(model_cfg.get("mode", "api")).strip().lower() or "api"
        if mode not in {"api", "local", "auto"}:
            mode = "api"
        model_cfg["mode"] = mode

        roles = model_cfg.get("roles")
        if not isinstance(roles, dict):
            roles = {}
        normalized_roles: dict[str, dict[str, Any]] = {}
        for role, defaults in DEFAULT_ROLES.items():
            role_cfg = roles.get(role, {})
            if not isinstance(role_cfg, dict):
                role_cfg = {}
            normalized_roles[role] = {**copy.deepcopy(defaults), **role_cfg}
        model_cfg["roles"] = normalized_roles

        custom_providers = model_cfg.get("custom_providers")
        if not isinstance(custom_providers, list):
            custom_providers = []
        normalized_customs: list[dict[str, Any]] = []
        for cp in custom_providers:
            if not isinstance(cp, dict):
                continue
            cid = str(cp.get("id", "")).strip().lower()
            if not cid:
                continue
            display = str(cp.get("display", cid)).strip() or cid
            base_url = str(cp.get("base_url", "")).strip()
            models = _normalize_model_list(cp.get("models", []))
            api_version = str(cp.get("api_version", "")).strip()
            api_key_env = str(cp.get("api_key_env", _provider_env_key(cid))).strip()
            normalized_customs.append(
                {
                    "id": cid,
                    "display": display,
                    "base_url": base_url,
                    "models": models,
                    "api_version": api_version,
                    "api_key_env": api_key_env,
                }
            )
        model_cfg["custom_providers"] = normalized_customs
        provider_custom_models = model_cfg.get("provider_custom_models")
        if not isinstance(provider_custom_models, dict):
            provider_custom_models = {}
        sanitized_custom_models: dict[str, list[str]] = {}
        for provider_id, models in provider_custom_models.items():
            sanitized_custom_models[str(provider_id)] = _normalize_model_list(models)
        model_cfg["provider_custom_models"] = sanitized_custom_models
        cfg["model_config"] = model_cfg

        simulation = cfg.get("simulation")
        if not isinstance(simulation, dict):
            simulation = {}
        simulation["tier"] = str(simulation.get("tier", "auto")).strip().lower() or "auto"
        simulation["e2b_api_key_env"] = str(simulation.get("e2b_api_key_env", "E2B_API_KEY")).strip() or "E2B_API_KEY"
        simulation["promptfoo_path"] = str(simulation.get("promptfoo_path", "npx promptfoo@latest")).strip() or "npx promptfoo@latest"
        simulation["veris_env_id"] = str(simulation.get("veris_env_id", "")).strip()
        simulation["veris_run_id"] = str(simulation.get("veris_run_id", "")).strip()
        cfg["simulation"] = simulation

        cfg["version"] = 2
        return cfg

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._api_keys_tab(), "🔑 API Keys")
        self.tabs.addTab(self._models_tab(), "🧠 Models")
        self.tabs.addTab(self._simulation_tab(), "🧪 Simulation")
        self.tabs.addTab(self._appearance_tab(), "🎨 Appearance")
        self.tabs.addTab(self._workspace_tab(), "📁 Workspace")
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

    def _wrap_scroll(self, inner: QWidget) -> QWidget:
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(inner)
        layout.addWidget(scroll)
        return wrapper

    def _register_linked_input(self, env_key: str, inp: QLineEdit) -> None:
        env_key = str(env_key).strip()
        if not env_key:
            return
        self._linked_inputs.setdefault(env_key, []).append(inp)
        inp.textChanged.connect(lambda value, k=env_key, source=inp: self._sync_linked_inputs(k, value, source))

    def _sync_linked_inputs(self, env_key: str, value: str, source: QLineEdit) -> None:
        for inp in self._linked_inputs.get(env_key, []):
            if inp is source:
                continue
            if inp.text() == value:
                continue
            inp.blockSignals(True)
            inp.setText(value)
            inp.blockSignals(False)

    def _build_key_controls(
        self,
        env_key: str,
        service_id: str,
        placeholder: str,
        meta: dict[str, Any] | None = None,
    ) -> tuple[QLineEdit, QPushButton, QPushButton]:
        inp = QLineEdit()
        inp.setEchoMode(QLineEdit.EchoMode.Password)
        inp.setPlaceholderText(placeholder)
        inp.setText(self._env_values.get(env_key, ""))
        self._register_linked_input(env_key, inp)

        eye = QPushButton("👁")
        eye.setFixedWidth(32)
        eye.setCheckable(True)
        eye.setToolTip("Show / hide key")
        eye.toggled.connect(
            lambda checked, i=inp: i.setEchoMode(
                QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
            )
        )

        test_btn = QPushButton("✓ Test")
        test_btn.setFixedWidth(68)
        test_btn.clicked.connect(lambda _: self._run_validate(service_id, inp, test_btn, meta or {}))
        return inp, eye, test_btn

    def _run_validate(
        self,
        service_id: str,
        key_input: QLineEdit,
        button: QPushButton,
        meta: dict[str, Any] | None = None,
    ) -> None:
        key = key_input.text().strip()
        button.setText("⏳")
        button.setEnabled(False)
        button.setStyleSheet("background: #333; color: #aaa; border-radius: 6px; padding: 6px;")

        worker = _ValidateWorker(service_id, key, meta=meta or {}, parent=self)
        self._workers[id(worker)] = worker

        def on_done(ok: bool, msg: str):
            if ok:
                button.setText("✅")
                button.setStyleSheet(
                    f"background: rgba(102,187,106,0.2); color: {COLORS['success']};"
                    "border: 1px solid rgba(102,187,106,0.5); border-radius: 6px; padding: 6px;"
                )
                QMessageBox.information(self, f"{_provider_display(service_id, self._custom_providers())} — Connected", msg)
            else:
                button.setText("❌")
                button.setStyleSheet(
                    f"background: rgba(239,83,80,0.15); color: {COLORS['danger']};"
                    "border: 1px solid rgba(239,83,80,0.4); border-radius: 6px; padding: 6px;"
                )
                QMessageBox.warning(self, f"{_provider_display(service_id, self._custom_providers())} — Failed", msg)
            button.setEnabled(True)
            self._workers.pop(id(worker), None)

        worker.done.connect(on_done)
        worker.start()

    def _api_keys_tab(self):
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        for provider_id in BUILTIN_PROVIDER_PILLS:
            env_key = _provider_env_key(provider_id, self._custom_providers())
            group = QGroupBox(_provider_display(provider_id, self._custom_providers()))
            row = QHBoxLayout(group)
            inp, eye, test_btn = self._build_key_controls(
                env_key=env_key,
                service_id=provider_id,
                placeholder=f"{env_key}=...",
            )
            row.addWidget(inp)
            row.addWidget(eye)
            row.addWidget(test_btn)
            layout.addWidget(group)

            if provider_id == "openrouter":
                tip = QLabel(
                    "ℹ️ OpenRouter: Add $10 credits to increase daily tool calls from 50 → 1,000\n"
                    "   Get free key at openrouter.ai · 28 free models including Llama 3.3 70B, Nemotron 3 Super"
                )
                tip.setStyleSheet("color: #7FB3FF; font-size: 11px; padding: 4px 8px;")
                layout.addWidget(tip)

        for display, service_id, env_key, placeholder in EXTRA_API_ROWS:
            group = QGroupBox(display)
            row = QHBoxLayout(group)
            inp, eye, test_btn = self._build_key_controls(
                env_key=env_key,
                service_id=service_id,
                placeholder=placeholder,
            )
            row.addWidget(inp)
            row.addWidget(eye)
            row.addWidget(test_btn)
            layout.addWidget(group)

        env_label = QLabel(f"Stored in: {ENV_FILE}")
        env_label.setStyleSheet("color: #555; font-size: 10px; padding: 4px 2px;")
        layout.addWidget(env_label)
        layout.addStretch()

        return self._wrap_scroll(root)

    def _models_tab(self):
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        mode_group = QGroupBox("Mode")
        mode_row = QHBoxLayout(mode_group)
        self._mode_local_radio = QRadioButton("Local")
        self._mode_api_radio = QRadioButton("API")
        mode = self.config.get("model_config", {}).get("mode", "api")
        self._mode_api_radio.setChecked(mode in {"api", "auto"})
        self._mode_local_radio.setChecked(mode == "local")
        self._mode_label = QLabel(f"Current: {mode}")
        self._mode_label.setStyleSheet("color: #9FA8DA;")
        mode_row.addWidget(self._mode_local_radio)
        mode_row.addWidget(self._mode_api_radio)
        mode_row.addSpacing(16)
        mode_row.addWidget(self._mode_label)
        mode_row.addStretch()
        self._mode_group = QButtonGroup(self)
        self._mode_group.addButton(self._mode_local_radio)
        self._mode_group.addButton(self._mode_api_radio)
        self._mode_local_radio.toggled.connect(self._on_mode_changed)
        self._mode_api_radio.toggled.connect(self._on_mode_changed)
        layout.addWidget(mode_group)

        self._local_group = QGroupBox("Local Model Discovery")
        local_layout = QVBoxLayout(self._local_group)
        status_row = QHBoxLayout()
        self._local_status = QLabel("Detecting local runtimes...")
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._refresh_local_models)
        status_row.addWidget(self._local_status)
        status_row.addStretch()
        status_row.addWidget(refresh_btn)
        local_layout.addLayout(status_row)
        self._local_model_combo = QComboBox()
        local_layout.addWidget(self._local_model_combo)
        layout.addWidget(self._local_group)

        self._api_group = QGroupBox("API Model Configuration")
        api_layout = QVBoxLayout(self._api_group)
        api_layout.setSpacing(10)

        pills_group = QGroupBox("Providers")
        pills_layout = QVBoxLayout(pills_group)
        self._builtin_pills_row = QHBoxLayout()
        self._builtin_pills_row.setSpacing(6)

        for provider_id in BUILTIN_PROVIDER_PILLS:
            btn = QPushButton(_provider_display(provider_id, self._custom_providers()))
            btn.setCheckable(True)
            btn.clicked.connect(lambda _, p=provider_id: self._select_provider(p))
            self._provider_buttons[provider_id] = btn
            self._builtin_pills_row.addWidget(btn)

        add_custom_btn = QPushButton("+ Add Custom")
        add_custom_btn.clicked.connect(self._start_add_custom_provider)
        self._builtin_pills_row.addWidget(add_custom_btn)
        self._builtin_pills_row.addStretch()
        pills_layout.addLayout(self._builtin_pills_row)

        self._custom_provider_rows = QVBoxLayout()
        self._custom_provider_rows.setSpacing(6)
        pills_layout.addLayout(self._custom_provider_rows)
        api_layout.addWidget(pills_group)

        selected_group = QGroupBox("Selected Provider")
        selected_layout = QFormLayout(selected_group)
        self._selected_provider_name = QLabel("-")
        self._selected_provider_base_url = QLabel("-")
        self._selected_provider_family_label = QLabel("Model Family")
        self._selected_provider_family = QComboBox()
        self._selected_provider_family.currentIndexChanged.connect(self._refresh_selected_provider_models)
        self._selected_provider_model = QComboBox()
        self._selected_provider_model.currentIndexChanged.connect(self._on_selected_provider_model_changed)
        self._selected_provider_custom_models = QLineEdit()
        self._selected_provider_custom_models.setPlaceholderText("model-1, model-2, model-3")
        self._selected_provider_custom_models.editingFinished.connect(self._save_selected_provider_custom_models)
        self._selected_provider_hint = QLabel("")
        self._selected_provider_hint.setStyleSheet("color: #888; font-size: 11px;")

        selected_layout.addRow("Provider", self._selected_provider_name)
        selected_layout.addRow("Base URL", self._selected_provider_base_url)
        selected_layout.addRow(self._selected_provider_family_label, self._selected_provider_family)
        selected_layout.addRow("Model", self._selected_provider_model)
        selected_layout.addRow("Custom Model IDs", self._selected_provider_custom_models)
        selected_layout.addRow("", self._selected_provider_hint)
        api_layout.addWidget(selected_group)

        self._custom_provider_form = QGroupBox("Custom Provider")
        custom_form_layout = QFormLayout(self._custom_provider_form)
        self._custom_name_input = QLineEdit()
        self._custom_base_url_input = QLineEdit()
        self._custom_api_key_input = QLineEdit()
        self._custom_api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._custom_model_ids_input = QLineEdit()
        self._custom_model_ids_input.setPlaceholderText("model-a, model-b")
        self._custom_api_version_input = QLineEdit()
        custom_form_layout.addRow("Provider Name", self._custom_name_input)
        custom_form_layout.addRow("Base URL", self._custom_base_url_input)
        custom_form_layout.addRow("API Key", self._custom_api_key_input)
        custom_form_layout.addRow("Model IDs", self._custom_model_ids_input)
        custom_form_layout.addRow("API Version", self._custom_api_version_input)
        custom_actions = QHBoxLayout()
        custom_actions.addStretch()
        custom_cancel = QPushButton("Cancel")
        custom_cancel.clicked.connect(self._hide_custom_provider_form)
        custom_save = QPushButton("Save Provider")
        custom_save.clicked.connect(self._save_custom_provider)
        custom_actions.addWidget(custom_cancel)
        custom_actions.addWidget(custom_save)
        custom_form_layout.addRow("", custom_actions)
        self._custom_provider_form.setVisible(False)
        api_layout.addWidget(self._custom_provider_form)

        roles_group = QGroupBox("Per-role Assignment")
        roles_layout = QVBoxLayout(roles_group)
        self._role_table = QTableWidget(len(ROLE_ORDER), 4)
        self._role_table.setHorizontalHeaderLabels(["Role", "Provider", "Model", "Effort"])
        self._role_table.verticalHeader().setVisible(False)
        self._role_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._role_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        header = self._role_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)

        for row, role in enumerate(ROLE_ORDER):
            role_item = QTableWidgetItem(ROLE_LABELS.get(role, role))
            self._role_table.setItem(row, 0, role_item)

            provider_box = QComboBox()
            model_box = QComboBox()
            effort_box = QComboBox()

            provider_box.currentIndexChanged.connect(lambda _, r=role: self._on_role_provider_changed(r))
            model_box.currentIndexChanged.connect(lambda _, r=role: self._on_role_model_changed(r))
            effort_box.currentIndexChanged.connect(lambda _, r=role: self._on_role_effort_changed(r))

            self._role_table.setCellWidget(row, 1, provider_box)
            self._role_table.setCellWidget(row, 2, model_box)
            self._role_table.setCellWidget(row, 3, effort_box)

            self._role_provider_boxes[role] = provider_box
            self._role_model_boxes[role] = model_box
            self._role_effort_boxes[role] = effort_box

        roles_layout.addWidget(self._role_table)

        roles_actions = QHBoxLayout()
        reset_btn = QPushButton("Reset to Defaults")
        reset_btn.clicked.connect(self._reset_roles_to_defaults)
        auto_btn = QPushButton("Auto")
        auto_btn.clicked.connect(self._set_auto_mode)
        roles_actions.addWidget(reset_btn)
        roles_actions.addWidget(auto_btn)
        roles_actions.addStretch()
        roles_layout.addLayout(roles_actions)
        api_layout.addWidget(roles_group)

        layout.addWidget(self._api_group)
        layout.addStretch()

        return self._wrap_scroll(root)

    def _simulation_tab(self):
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        mode_group = QGroupBox("Mode")
        mode_layout = QHBoxLayout(mode_group)
        self._sim_mode_buttons: dict[str, QRadioButton] = {}
        self._sim_mode_group = QButtonGroup(self)
        current_tier = str(self.config.get("simulation", {}).get("tier", "auto")).lower()
        for mode_id, label in [
            ("auto", "Auto"),
            ("mock", "Mock"),
            ("promptfoo", "Promptfoo"),
            ("e2b", "E2B"),
            ("veris", "Veris"),
        ]:
            radio = QRadioButton(label)
            radio.setChecked(current_tier == mode_id)
            radio.toggled.connect(lambda checked, m=mode_id: self._on_sim_mode_changed(m, checked))
            self._sim_mode_group.addButton(radio)
            self._sim_mode_buttons[mode_id] = radio
            mode_layout.addWidget(radio)
        mode_layout.addStretch()
        layout.addWidget(mode_group)

        mock_group = QGroupBox("Mock Simulation (always available)")
        mock_layout = QVBoxLayout(mock_group)
        mock_layout.addWidget(
            QLabel(
                "Uses the configured LLM to simulate agent responses.\n"
                "Results are realistic but not live-executed."
            )
        )
        layout.addWidget(mock_group)

        promptfoo_group = QGroupBox("Promptfoo (free, local)")
        promptfoo_layout = QFormLayout(promptfoo_group)
        self._promptfoo_path_input = QLineEdit(self.config.get("simulation", {}).get("promptfoo_path", "npx promptfoo@latest"))
        self._promptfoo_path_input.textChanged.connect(
            lambda v: self.config.setdefault("simulation", {}).update({"promptfoo_path": v.strip() or "npx promptfoo@latest"})
        )
        detect_row = QHBoxLayout()
        detect_btn = QPushButton("Detect")
        detect_btn.clicked.connect(self._detect_promptfoo)
        self._promptfoo_status = QLabel("Not checked")
        self._promptfoo_status.setStyleSheet("color: #888; font-size: 11px;")
        detect_row.addWidget(detect_btn)
        detect_row.addWidget(self._promptfoo_status)
        detect_row.addStretch()
        promptfoo_layout.addRow("Path", self._promptfoo_path_input)
        promptfoo_layout.addRow("Status", detect_row)
        layout.addWidget(promptfoo_group)

        e2b_group = QGroupBox("E2B Cloud Sandbox")
        e2b_layout = QVBoxLayout(e2b_group)
        e2b_row = QHBoxLayout()
        e2b_input, e2b_eye, e2b_test = self._build_key_controls("E2B_API_KEY", "e2b", "e2b_...")
        e2b_row.addWidget(e2b_input)
        e2b_row.addWidget(e2b_eye)
        e2b_row.addWidget(e2b_test)
        e2b_layout.addLayout(e2b_row)
        e2b_info = QLabel("Free tier: $100 one-time credit · No credit card required\nℹ️ Get free key at e2b.dev")
        e2b_info.setStyleSheet("color: #9FA8DA; font-size: 11px;")
        e2b_layout.addWidget(e2b_info)
        layout.addWidget(e2b_group)

        veris_group = QGroupBox("Veris AI (Enterprise)")
        veris_layout = QFormLayout(veris_group)
        veris_key_row = QHBoxLayout()
        veris_input, veris_eye, veris_test = self._build_key_controls("VERIS_API_KEY", "veris", "veris key")
        veris_key_row.addWidget(veris_input)
        veris_key_row.addWidget(veris_eye)
        veris_key_row.addWidget(veris_test)
        self._veris_env_id_input = QLineEdit(self.config.get("simulation", {}).get("veris_env_id", ""))
        self._veris_env_id_input.textChanged.connect(
            lambda v: self.config.setdefault("simulation", {}).update({"veris_env_id": v.strip()})
        )
        self._veris_run_id_input = QLineEdit(self.config.get("simulation", {}).get("veris_run_id", ""))
        self._veris_run_id_input.textChanged.connect(
            lambda v: self.config.setdefault("simulation", {}).update({"veris_run_id": v.strip()})
        )
        veris_layout.addRow("API Key", veris_key_row)
        veris_layout.addRow("Environment ID", self._veris_env_id_input)
        veris_layout.addRow("Run ID", self._veris_run_id_input)
        veris_note = QLabel("ℹ️ veris.ai -- Google Cloud Marketplace")
        veris_note.setStyleSheet("color: #9FA8DA; font-size: 11px;")
        veris_layout.addRow("", veris_note)
        layout.addWidget(veris_group)

        layout.addStretch()
        return self._wrap_scroll(root)

    def _appearance_tab(self):
        widget = QWidget()
        layout = QGridLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.addWidget(QLabel("Overlay Opacity:"), 0, 0)
        self._opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self._opacity_slider.setRange(50, 100)
        self._opacity_slider.setValue(int(float(self.config.get("overlay", {}).get("opacity", 0.92)) * 100))
        self._opacity_slider.valueChanged.connect(self._on_opacity_changed)
        layout.addWidget(self._opacity_slider, 0, 1)
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
        self._output_dir_input.setText(self.config.get("output_dir", str(Path.home() / ".gauntlet")))
        self._output_dir_input.textChanged.connect(self._on_output_dir_changed)
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

    def _on_output_dir_changed(self, value: str) -> None:
        value = str(value or "").strip()
        self.config["output_dir"] = value
        self.config["OUTPUT_DIR"] = value

    def _on_opacity_changed(self, slider_value: int) -> None:
        opacity = max(0.0, min(1.0, slider_value / 100))
        self.config.setdefault("overlay", {})["opacity"] = opacity
        self.config["OVERLAY_OPACITY"] = opacity

    def _on_sim_mode_changed(self, mode: str, checked: bool) -> None:
        if not checked:
            return
        self.config.setdefault("simulation", {})["tier"] = mode

    def _detect_promptfoo(self) -> None:
        configured = self._promptfoo_path_input.text().strip() or "npx promptfoo@latest"
        if configured.lower().startswith("npx"):
            if shutil.which("npx"):
                self._promptfoo_status.setText("Detected ✅  (npx available)")
                self._promptfoo_status.setStyleSheet(f"color: {COLORS['success']}; font-size: 11px;")
            else:
                self._promptfoo_status.setText("Not detected ❌  (install Node.js / npx)")
                self._promptfoo_status.setStyleSheet(f"color: {COLORS['danger']}; font-size: 11px;")
        else:
            if shutil.which(configured):
                self._promptfoo_status.setText("Detected ✅")
                self._promptfoo_status.setStyleSheet(f"color: {COLORS['success']}; font-size: 11px;")
            else:
                self._promptfoo_status.setText("Path not found ❌")
                self._promptfoo_status.setStyleSheet(f"color: {COLORS['danger']}; font-size: 11px;")

    def _custom_providers(self) -> list[dict[str, Any]]:
        providers = self.config.get("model_config", {}).get("custom_providers", [])
        return providers if isinstance(providers, list) else []

    def _custom_provider(self, provider_id: str) -> dict[str, Any] | None:
        for cp in self._custom_providers():
            if cp.get("id") == provider_id:
                return cp
        return None

    def _provider_custom_models_map(self) -> dict[str, list[str]]:
        model_cfg = self.config.setdefault("model_config", {})
        custom_map = model_cfg.get("provider_custom_models")
        if not isinstance(custom_map, dict):
            custom_map = {}
            model_cfg["provider_custom_models"] = custom_map
        return custom_map

    def _current_env_value(self, env_key: str) -> str:
        env_key = str(env_key).strip()
        if env_key in self._linked_inputs and self._linked_inputs[env_key]:
            return self._linked_inputs[env_key][0].text().strip()
        if env_key in self._custom_env_updates:
            return self._custom_env_updates[env_key].strip()
        return str(self._env_values.get(env_key, "")).strip()

    def _has_provider_key(self, provider_id: str) -> bool:
        provider_id = str(provider_id).strip().lower()
        if provider_id in {"local_ollama", "local_lmstudio"}:
            return True
        env_key = _provider_env_key(provider_id, self._custom_providers())
        return bool(self._current_env_value(env_key))

    def _provider_options_for_role(self, role: str, current_provider: str) -> list[str]:
        candidates: list[str] = []

        defaults = DEFAULT_ROLES.get(role, {})
        default_provider = str(defaults.get("provider", "")).strip()
        if default_provider:
            candidates.append(default_provider)

        for provider, _model in FALLBACK_CHAINS.get(role, []):
            if provider:
                candidates.append(str(provider))

        if role == "search":
            candidates.extend(SEARCH_PROVIDERS)

        for cp in self._custom_providers():
            candidates.append(str(cp.get("id", "")).strip())

        if current_provider:
            candidates.append(current_provider)

        ordered = _dedupe_keep_order(candidates)
        mode = self.config.get("model_config", {}).get("mode", "api")

        if mode == "local":
            local_opts = ["local_ollama", "local_lmstudio"]
            if current_provider and current_provider not in local_opts:
                local_opts.append(current_provider)
            return _dedupe_keep_order(local_opts)

        filtered = [pid for pid in ordered if pid and (self._has_provider_key(pid) or pid == current_provider)]
        if not filtered and current_provider:
            filtered = [current_provider]
        if not filtered and default_provider:
            filtered = [default_provider]
        return _dedupe_keep_order(filtered)

    def _models_for_provider(self, provider_id: str, role: str | None = None, family: str | None = None) -> list[str]:
        provider_id = str(provider_id or "").strip()
        cp = self._custom_provider(provider_id)
        if cp:
            return _normalize_model_list(cp.get("models", []))

        if provider_id in {"local_ollama", "local_lmstudio"}:
            models = [m for source, m, _display in self._local_models if source == provider_id]
            return _dedupe_keep_order(models)

        if provider_id in SEARCH_PROVIDERS:
            return []

        provider = PROVIDER_REGISTRY.get(provider_id, {})
        if not provider:
            return []

        if family and isinstance(provider.get("families"), dict):
            fam = provider["families"].get(family, {})
            if isinstance(fam, dict):
                models = [str(x) for x in fam.get("models", [])]
            else:
                models = []
        else:
            models = _collect_registry_models(provider_id, role=role)

        custom_models_map = self._provider_custom_models_map()
        custom_models = _normalize_model_list(custom_models_map.get(provider_id, []))
        return _dedupe_keep_order(models + custom_models)

    def _refresh_provider_pills(self) -> None:
        while self._custom_provider_rows.count():
            item = self._custom_provider_rows.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        for cp in self._custom_providers():
            provider_id = str(cp.get("id", "")).strip()
            if not provider_id:
                continue

            row_widget = QWidget()
            row = QHBoxLayout(row_widget)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(6)

            pill = QPushButton(_provider_display(provider_id, self._custom_providers()))
            pill.setCheckable(True)
            pill.clicked.connect(lambda _, p=provider_id: self._select_provider(p))
            self._provider_buttons[provider_id] = pill
            row.addWidget(pill)

            edit_btn = QPushButton("✏️")
            edit_btn.setFixedWidth(34)
            edit_btn.clicked.connect(lambda _, p=provider_id: self._start_edit_custom_provider(p))
            row.addWidget(edit_btn)

            del_btn = QPushButton("🗑️")
            del_btn.setFixedWidth(34)
            del_btn.clicked.connect(lambda _, p=provider_id: self._delete_custom_provider(p))
            row.addWidget(del_btn)

            row.addStretch()
            self._custom_provider_rows.addWidget(row_widget)

        if self._selected_provider_id not in self._provider_buttons:
            self._selected_provider_id = BUILTIN_PROVIDER_PILLS[0]
        self._select_provider(self._selected_provider_id)

    def _select_provider(self, provider_id: str) -> None:
        self._selected_provider_id = provider_id
        for pid, btn in self._provider_buttons.items():
            btn.setChecked(pid == provider_id)
        self._refresh_selected_provider_editor()

    def _refresh_selected_provider_editor(self) -> None:
        provider_id = self._selected_provider_id
        if not provider_id:
            return

        custom_providers = self._custom_providers()
        self._selected_provider_name.setText(_provider_display(provider_id, custom_providers))

        cp = self._custom_provider(provider_id)
        if cp:
            base_url = str(cp.get("base_url", "")).strip()
        else:
            base_url = get_base_url(provider_id)
        self._selected_provider_base_url.setText(base_url or "-")

        provider = PROVIDER_REGISTRY.get(provider_id, {})
        families = provider.get("families", {})
        has_families = isinstance(families, dict) and len(families) > 0
        self._selected_provider_family.setVisible(has_families)
        self._selected_provider_family_label.setVisible(has_families)

        if has_families:
            selected_family = self._provider_selected_family.get(provider_id, "")
            self._selected_provider_family.blockSignals(True)
            self._selected_provider_family.clear()
            self._selected_provider_family.addItem("All Families", "")
            for fam_key in families.keys():
                self._selected_provider_family.addItem(str(fam_key), str(fam_key))
            fam_idx = self._selected_provider_family.findData(selected_family)
            self._selected_provider_family.setCurrentIndex(fam_idx if fam_idx >= 0 else 0)
            self._selected_provider_family.blockSignals(False)

        self._refresh_selected_provider_models()

    def _refresh_selected_provider_models(self) -> None:
        provider_id = self._selected_provider_id
        if not provider_id:
            return
        family = ""
        if self._selected_provider_family.isVisible():
            family = str(self._selected_provider_family.currentData() or "")
            self._provider_selected_family[provider_id] = family

        models = self._models_for_provider(provider_id, family=family if family else None)
        current = self._provider_selected_model.get(provider_id, "")
        provider_default = str(PROVIDER_REGISTRY.get(provider_id, {}).get("default", "")).strip()
        current = current or provider_default

        self._selected_provider_model.blockSignals(True)
        self._selected_provider_model.clear()
        for m in models:
            self._selected_provider_model.addItem(m, m)
        self._selected_provider_model.addItem("Custom...", "__custom__")

        if current and current in models:
            idx = self._selected_provider_model.findData(current)
        else:
            idx = self._selected_provider_model.findData("__custom__" if current else (models[0] if models else "__custom__"))
        self._selected_provider_model.setCurrentIndex(idx if idx >= 0 else 0)
        self._selected_provider_model.blockSignals(False)
        self._on_selected_provider_model_changed()

    def _on_selected_provider_model_changed(self) -> None:
        provider_id = self._selected_provider_id
        selected = str(self._selected_provider_model.currentData() or "")
        if selected == "__custom__":
            custom_map = self._provider_custom_models_map()
            existing = _normalize_model_list(custom_map.get(provider_id, []))
            self._selected_provider_custom_models.setText(", ".join(existing))
            self._selected_provider_custom_models.setVisible(True)
            self._selected_provider_hint.setText(
                "Add comma-separated custom model IDs for this provider."
            )
        else:
            self._selected_provider_custom_models.setVisible(False)
            if selected:
                self._provider_selected_model[provider_id] = selected
            self._selected_provider_hint.setText("Select a model family and model ID.")

    def _save_selected_provider_custom_models(self) -> None:
        provider_id = self._selected_provider_id
        if not provider_id:
            return
        values = _normalize_model_list(self._selected_provider_custom_models.text())
        custom_map = self._provider_custom_models_map()
        custom_map[provider_id] = values
        self._refresh_selected_provider_models()
        self._refresh_role_table()

    def _start_add_custom_provider(self) -> None:
        self._editing_custom_provider_id = None
        self._custom_name_input.clear()
        self._custom_base_url_input.clear()
        self._custom_api_key_input.clear()
        self._custom_model_ids_input.clear()
        self._custom_api_version_input.clear()
        self._custom_provider_form.setTitle("Add Custom Provider")
        self._custom_provider_form.setVisible(True)

    def _start_edit_custom_provider(self, provider_id: str) -> None:
        cp = self._custom_provider(provider_id)
        if not cp:
            return
        self._editing_custom_provider_id = provider_id
        self._custom_name_input.setText(str(cp.get("display", provider_id)))
        self._custom_base_url_input.setText(str(cp.get("base_url", "")))
        self._custom_model_ids_input.setText(", ".join(_normalize_model_list(cp.get("models", []))))
        self._custom_api_version_input.setText(str(cp.get("api_version", "")))
        env_key = _provider_env_key(provider_id, self._custom_providers())
        self._custom_api_key_input.setText(self._current_env_value(env_key))
        self._custom_provider_form.setTitle(f"Edit Custom Provider — {provider_id}")
        self._custom_provider_form.setVisible(True)

    def _hide_custom_provider_form(self) -> None:
        self._custom_provider_form.setVisible(False)
        self._editing_custom_provider_id = None

    def _save_custom_provider(self) -> None:
        name = self._custom_name_input.text().strip()
        base_url = self._custom_base_url_input.text().strip()
        model_ids = _normalize_model_list(self._custom_model_ids_input.text())
        api_version = self._custom_api_version_input.text().strip()
        api_key = self._custom_api_key_input.text().strip()

        if not name:
            QMessageBox.warning(self, "Invalid Provider", "Provider Name is required.")
            return
        if not base_url:
            QMessageBox.warning(self, "Invalid Provider", "Base URL is required.")
            return
        if not model_ids:
            QMessageBox.warning(self, "Invalid Provider", "At least one model ID is required.")
            return

        provider_id = self._editing_custom_provider_id or _parse_custom_provider_id(name)
        if not provider_id:
            QMessageBox.warning(self, "Invalid Provider", "Could not derive provider ID from name.")
            return

        customs = self._custom_providers()
        existing_ids = {str(cp.get("id", "")).strip() for cp in customs}
        if self._editing_custom_provider_id is None and provider_id in existing_ids:
            QMessageBox.warning(self, "Duplicate Provider", f"Provider '{provider_id}' already exists.")
            return

        api_key_env = _provider_env_key(provider_id, customs)
        entry = {
            "id": provider_id,
            "display": name,
            "base_url": base_url,
            "models": model_ids,
            "api_version": api_version,
            "api_key_env": api_key_env,
        }

        updated: list[dict[str, Any]] = []
        replaced = False
        for cp in customs:
            if cp.get("id") == provider_id:
                updated.append(entry)
                replaced = True
            else:
                updated.append(cp)
        if not replaced:
            updated.append(entry)

        self.config.setdefault("model_config", {})["custom_providers"] = updated
        if api_key:
            self._custom_env_updates[api_key_env] = api_key

        self._hide_custom_provider_form()
        self._refresh_provider_pills()
        self._refresh_role_table()
        self._select_provider(provider_id)

    def _delete_custom_provider(self, provider_id: str) -> None:
        customs = [cp for cp in self._custom_providers() if cp.get("id") != provider_id]
        self.config.setdefault("model_config", {})["custom_providers"] = customs

        roles = self.config.setdefault("model_config", {}).setdefault("roles", {})
        for role, defaults in DEFAULT_ROLES.items():
            role_cfg = roles.get(role, {})
            if not isinstance(role_cfg, dict):
                role_cfg = {}
            if role_cfg.get("provider") == provider_id:
                role_cfg["provider"] = defaults.get("provider")
                role_cfg["model"] = defaults.get("model")
                role_cfg["effort"] = defaults.get("effort")
            roles[role] = role_cfg

        if provider_id in self._provider_buttons:
            btn = self._provider_buttons.pop(provider_id)
            btn.deleteLater()
        if self._selected_provider_id == provider_id:
            self._selected_provider_id = BUILTIN_PROVIDER_PILLS[0]

        custom_map = self._provider_custom_models_map()
        if provider_id in custom_map:
            del custom_map[provider_id]

        self._refresh_provider_pills()
        self._refresh_role_table()

    def _refresh_role_table(self) -> None:
        roles_cfg = self.config.setdefault("model_config", {}).setdefault("roles", {})

        for role in ROLE_ORDER:
            role_cfg = roles_cfg.get(role, {})
            if not isinstance(role_cfg, dict):
                role_cfg = {}
            role_cfg = {**copy.deepcopy(DEFAULT_ROLES.get(role, {})), **role_cfg}
            roles_cfg[role] = role_cfg

            provider_box = self._role_provider_boxes[role]
            model_box = self._role_model_boxes[role]
            effort_box = self._role_effort_boxes[role]

            current_provider = str(role_cfg.get("provider", "")).strip()
            options = self._provider_options_for_role(role, current_provider)
            provider_box.blockSignals(True)
            provider_box.clear()
            for pid in options:
                provider_box.addItem(_provider_display(pid, self._custom_providers()), pid)
            idx = provider_box.findData(current_provider)
            provider_box.setCurrentIndex(idx if idx >= 0 else 0)
            provider_box.blockSignals(False)

            selected_provider = str(provider_box.currentData() or current_provider or "")
            if selected_provider:
                role_cfg["provider"] = selected_provider

            self._populate_role_model_combo(role, model_box, selected_provider)
            selected_model = str(model_box.currentData() or "")
            self._populate_role_effort_combo(role, effort_box, selected_provider, selected_model)

    def _populate_role_model_combo(self, role: str, model_box: QComboBox, provider_id: str) -> None:
        roles_cfg = self.config.setdefault("model_config", {}).setdefault("roles", {})
        role_cfg = roles_cfg.get(role, {})
        if not isinstance(role_cfg, dict):
            role_cfg = {}
            roles_cfg[role] = role_cfg

        models = self._models_for_provider(provider_id, role=role)
        current_model = str(role_cfg.get("model", "")).strip()
        if current_model and current_model not in models and role != "search":
            models = _dedupe_keep_order([current_model] + models)

        model_box.blockSignals(True)
        model_box.clear()

        if role == "search" or not models:
            model_box.addItem("-", "")
            model_box.setEnabled(False)
            if role == "search":
                role_cfg["model"] = ""
            model_box.blockSignals(False)
            return

        for model in models:
            model_box.addItem(model, model)
        idx = model_box.findData(current_model)
        model_box.setCurrentIndex(idx if idx >= 0 else 0)
        model_box.setEnabled(True)
        model_box.blockSignals(False)
        role_cfg["model"] = str(model_box.currentData() or "")

    def _populate_role_effort_combo(
        self,
        role: str,
        effort_box: QComboBox,
        provider_id: str,
        model_id: str,
    ) -> None:
        roles_cfg = self.config.setdefault("model_config", {}).setdefault("roles", {})
        role_cfg = roles_cfg.get(role, {})
        if not isinstance(role_cfg, dict):
            role_cfg = {}
            roles_cfg[role] = role_cfg

        if role in {"search", "tts", "stt"}:
            options: list[str] = []
        else:
            options = get_effort_options(provider_id, model_id) if provider_id in PROVIDER_REGISTRY and model_id else []

        current_effort = role_cfg.get("effort")
        effort_box.blockSignals(True)
        effort_box.clear()

        if not options:
            effort_box.addItem("-", "")
            effort_box.setEnabled(False)
            role_cfg["effort"] = None
            effort_box.blockSignals(False)
            return

        for effort in options:
            effort_box.addItem(effort, effort)
        idx = effort_box.findData(current_effort)
        if idx < 0:
            idx = effort_box.findData("medium")
        if idx < 0:
            idx = 0
        effort_box.setCurrentIndex(idx)
        effort_box.setEnabled(True)
        role_cfg["effort"] = str(effort_box.currentData() or "")
        effort_box.blockSignals(False)

    def _on_role_provider_changed(self, role: str) -> None:
        roles_cfg = self.config.setdefault("model_config", {}).setdefault("roles", {})
        role_cfg = roles_cfg.get(role, {})
        if not isinstance(role_cfg, dict):
            role_cfg = {}
            roles_cfg[role] = role_cfg

        provider_box = self._role_provider_boxes[role]
        model_box = self._role_model_boxes[role]
        effort_box = self._role_effort_boxes[role]
        provider_id = str(provider_box.currentData() or "").strip()
        if not provider_id:
            return
        role_cfg["provider"] = provider_id
        self._populate_role_model_combo(role, model_box, provider_id)
        self._populate_role_effort_combo(role, effort_box, provider_id, str(model_box.currentData() or ""))

    def _on_role_model_changed(self, role: str) -> None:
        roles_cfg = self.config.setdefault("model_config", {}).setdefault("roles", {})
        role_cfg = roles_cfg.get(role, {})
        if not isinstance(role_cfg, dict):
            role_cfg = {}
            roles_cfg[role] = role_cfg
        model_box = self._role_model_boxes[role]
        effort_box = self._role_effort_boxes[role]
        provider_id = str(role_cfg.get("provider", "")).strip()
        model_id = str(model_box.currentData() or "")
        role_cfg["model"] = model_id
        self._populate_role_effort_combo(role, effort_box, provider_id, model_id)

    def _on_role_effort_changed(self, role: str) -> None:
        roles_cfg = self.config.setdefault("model_config", {}).setdefault("roles", {})
        role_cfg = roles_cfg.get(role, {})
        if not isinstance(role_cfg, dict):
            role_cfg = {}
            roles_cfg[role] = role_cfg
        effort_box = self._role_effort_boxes[role]
        if not effort_box.isEnabled():
            role_cfg["effort"] = None
            return
        role_cfg["effort"] = str(effort_box.currentData() or "")

    def _reset_roles_to_defaults(self) -> None:
        self.config.setdefault("model_config", {})["roles"] = copy.deepcopy(DEFAULT_ROLES)
        self._refresh_role_table()

    def _set_auto_mode(self) -> None:
        self.config.setdefault("model_config", {})["mode"] = "auto"
        self._mode_api_radio.setChecked(True)
        self._mode_label.setText("Current: auto")
        QMessageBox.information(self, "Auto Mode", "Model mode set to auto-fallback.")

    def _on_mode_changed(self) -> None:
        model_cfg = self.config.setdefault("model_config", {})
        if self._mode_local_radio.isChecked():
            model_cfg["mode"] = "local"
        elif model_cfg.get("mode") != "auto":
            model_cfg["mode"] = "api"

        mode = model_cfg.get("mode", "api")
        self._mode_label.setText(f"Current: {mode}")
        show_local = mode == "local"
        self._local_group.setVisible(show_local)
        self._api_group.setVisible(not show_local)

    def _refresh_local_models(self) -> None:
        discovered: list[tuple[str, str, str]] = []

        try:
            r = requests.get("http://localhost:11434/api/tags", timeout=2)
            if r.ok:
                tags = r.json().get("models", [])
                for item in tags:
                    name = str(item.get("name", "")).strip()
                    if name:
                        discovered.append(("local_ollama", name, f"Ollama / {name}"))
        except Exception:
            pass

        try:
            r = requests.get("http://localhost:1234/v1/models", timeout=2)
            if r.ok:
                rows = r.json().get("data", [])
                for item in rows:
                    mid = str(item.get("id", "")).strip()
                    if mid:
                        discovered.append(("local_lmstudio", mid, f"LM Studio / {mid}"))
        except Exception:
            pass

        self._local_models = discovered
        self._local_model_combo.clear()
        if not discovered:
            self._local_status.setText("No local models detected. Start Ollama or LM Studio first.")
            self._local_status.setStyleSheet(f"color: {COLORS['warning']};")
            self._local_model_combo.setEnabled(False)
            self._local_model_combo.addItem("No local models detected")
            return

        self._local_model_combo.setEnabled(True)
        for source, model, display in discovered:
            self._local_model_combo.addItem(display, (source, model))
        self._local_status.setText(f"Detected {len(discovered)} local model(s).")
        self._local_status.setStyleSheet(f"color: {COLORS['success']};")

    def _browse_output_dir(self):
        current = self._output_dir_input.text() or str(Path.home())
        chosen = QFileDialog.getExistingDirectory(self, "Select Output Directory", current)
        if chosen:
            self._output_dir_input.setText(chosen)
            self._on_output_dir_changed(chosen)

    def _strip_api_keys_recursive(self, value: Any) -> None:
        if isinstance(value, dict):
            to_delete = [k for k in value.keys() if "API_KEY" in str(k).upper()]
            for key in to_delete:
                del value[key]
            for v in value.values():
                self._strip_api_keys_recursive(v)
        elif isinstance(value, list):
            for item in value:
                self._strip_api_keys_recursive(item)

    def _save(self):
        env_updates: dict[str, str] = {}
        for env_key, inputs in self._linked_inputs.items():
            if not inputs:
                continue
            env_updates[env_key] = inputs[0].text().strip()
        for env_key, value in self._custom_env_updates.items():
            if value.strip():
                env_updates[env_key] = value.strip()
        write_env(env_updates)

        cfg = self._normalize_config(self.config)
        cfg["version"] = 2
        cfg["output_dir"] = str(cfg.get("output_dir", cfg.get("OUTPUT_DIR", ""))).strip() or str(Path.home() / ".gauntlet")
        cfg["OUTPUT_DIR"] = cfg["output_dir"]

        overlay = cfg.setdefault("overlay", {})
        try:
            opacity = float(overlay.get("opacity", cfg.get("OVERLAY_OPACITY", 0.92)))
        except (TypeError, ValueError):
            opacity = 0.92
        opacity = max(0.0, min(1.0, opacity))
        overlay["opacity"] = opacity
        cfg["OVERLAY_OPACITY"] = opacity

        model_cfg = cfg.setdefault("model_config", {})
        roles = model_cfg.setdefault("roles", {})
        for role, defaults in DEFAULT_ROLES.items():
            role_cfg = roles.get(role, {})
            if not isinstance(role_cfg, dict):
                role_cfg = {}
            roles[role] = {**copy.deepcopy(defaults), **role_cfg}

        simulation = cfg.setdefault("simulation", {})
        simulation["tier"] = str(simulation.get("tier", "auto")).strip().lower() or "auto"
        simulation["e2b_api_key_env"] = str(simulation.get("e2b_api_key_env", "E2B_API_KEY")).strip() or "E2B_API_KEY"
        simulation["promptfoo_path"] = str(simulation.get("promptfoo_path", "npx promptfoo@latest")).strip() or "npx promptfoo@latest"
        simulation["veris_env_id"] = str(simulation.get("veris_env_id", "")).strip()
        simulation["veris_run_id"] = str(simulation.get("veris_run_id", "")).strip()

        safe_cfg = copy.deepcopy(cfg)
        self._strip_api_keys_recursive(safe_cfg)
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(safe_cfg, indent=2), encoding="utf-8")
        self.config = safe_cfg
        self.accept()

    def _apply_style(self):
        self.setStyleSheet(
            f"""
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
            QLineEdit, QComboBox {{
                background: #0F0F18; color: #E8E8F0;
                border: 1px solid rgba(92,107,192,0.3);
                border-radius: 6px; padding: 6px 10px;
            }}
            QTableWidget {{
                background: #131321;
                border: 1px solid rgba(92,107,192,0.25);
                border-radius: 8px;
                gridline-color: rgba(92,107,192,0.2);
            }}
            QHeaderView::section {{
                background: #2A2A38; color: #D0D4EF;
                border: none; padding: 6px;
            }}
            QPushButton {{
                background: #2A2A38; color: #E8E8F0;
                border: 1px solid rgba(92,107,192,0.3);
                border-radius: 6px; padding: 6px 12px;
            }}
            QPushButton:hover {{ background: #3A3A4A; }}
            QPushButton:checked {{ background: rgba(92,107,192,0.4); }}
            """
        )
