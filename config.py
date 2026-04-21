import json
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# API keys (loaded from .env / environment)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
XAI_API_KEY = os.getenv("XAI_API_KEY", "")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
BASETEN_API_KEY = os.getenv("BASETEN_API_KEY", "")
YOUCOM_API_KEY = os.getenv("YOUCOM_API_KEY", "")
FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY", "")
BRAVE_API_KEY = os.getenv("BRAVE_API_KEY", "")
EXA_API_KEY = os.getenv("EXA_API_KEY", "")
E2B_API_KEY = os.getenv("E2B_API_KEY", "")
VERIS_API_KEY = os.getenv("VERIS_API_KEY", "")

# Search provider endpoint
YOUCOM_SEARCH_URL = "https://ydc-index.io/v1/search"

OVERLAY_WIDTH = 520
OVERLAY_HEIGHT = 680

DOMAINS = [
    "Healthcare",
    "Finance & Banking",
    "Legal & Compliance",
    "HR & Recruiting",
    "Customer Support",
    "Insurance",
    "Supply Chain",
    "Custom",
]

ENV_FILE = Path(__file__).parent / ".env"
CONFIG_FILE = Path.home() / ".gauntlet" / "config.json"
CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)


def read_env() -> dict:
    result = {}
    if not ENV_FILE.exists():
        return result
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        result[key.strip()] = value.strip()
    return result


def write_env(updates: dict) -> None:
    existing_lines = []
    if ENV_FILE.exists():
        existing_lines = ENV_FILE.read_text(encoding="utf-8").splitlines()

    written_keys = set()
    new_lines = []
    for line in existing_lines:
        stripped = line.strip()
        if stripped.startswith("#") or "=" not in stripped:
            new_lines.append(line)
            continue
        key = stripped.split("=", 1)[0].strip()
        if key in updates:
            new_lines.append(f"{key}={updates[key]}")
            written_keys.add(key)
        else:
            new_lines.append(line)

    for key, value in updates.items():
        if key not in written_keys:
            new_lines.append(f"{key}={value}")

    ENV_FILE.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def get_output_dir() -> Path:
    if CONFIG_FILE.exists():
        try:
            cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            custom = cfg.get("OUTPUT_DIR", "").strip()
            if custom:
                p = Path(custom)
                p.mkdir(parents=True, exist_ok=True)
                return p
        except Exception:
            pass
    default = Path.home() / ".gauntlet"
    default.mkdir(parents=True, exist_ok=True)
    return default
