import os
import json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY   = os.getenv("OPENAI_API_KEY", "")
YOUCOM_API_KEY   = os.getenv("YOUCOM_API_KEY", "")
BASETEN_API_KEY  = os.getenv("BASETEN_API_KEY", "")
VERIS_API_KEY    = os.getenv("VERIS_API_KEY", "")

# Primary inference: GLM-5 on Baseten
# - zai-org/GLM-5: 744B MoE, 40B active, purpose-built for agentic + coding
# - Baseten-optimized: 178 t/s, 0.93s TTFT, $0.95/M input, $3.15/M output
# - MIT license -- best open-source model on SWE-Bench Pro family
# - Enable at https://app.baseten.co/model-apis/create
BASETEN_BASE_URL     = "https://inference.baseten.co/v1"
BASETEN_MODEL_SLUG   = "zai-org/GLM-5"
BASETEN_VISION_MODEL = "moonshotai/Kimi-K2.5"  # only vision model on Baseten Model APIs

# Fallback inference: gpt-5.4-mini (reasoning model, OpenAI)
# - Released March 17, 2026 -- part of GPT-5.4 reasoning family
# - Context: 400K tokens, max output: 128K tokens
#   (gpt-5.4 standard/pro has 1M context -- mini does NOT)
# - Pricing: $0.75/M input, $4.50/M output
# - CRITICAL API differences vs gpt-4o (non-negotiable):
#     * max_completion_tokens instead of max_tokens
#     * NO temperature parameter -- reasoning models reject it and error
#     * reasoning={"effort": "high"} for deep analysis on security tasks
OPENAI_FALLBACK_MODEL   = "gpt-5.4-mini"
OPENAI_REASONING_EFFORT = "high"

# TTS stays on OpenAI -- separate API, not chat completions, unaffected
OPENAI_TTS_MODEL = "tts-1"

# You.com: correct base URL (not api.you.com)
YOUCOM_SEARCH_URL = "https://ydc-index.io/v1/search"

OVERLAY_WIDTH  = 520
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

# Path to the .env file -- resolved relative to this config.py so it works
# regardless of where the app is launched from.
ENV_FILE    = Path(__file__).parent / ".env"
CONFIG_FILE = Path.home() / ".gauntlet" / "config.json"
CONFIG_FILE.parent.mkdir(exist_ok=True)


def read_env() -> dict:
    """Parse the .env file and return a dict of KEY -> value."""
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
    """
    Write API key updates back to the .env file.
    Preserves all existing lines; only updates/adds the keys in `updates`.
    """
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

    # Append any keys in updates that weren't in the file already
    for key, value in updates.items():
        if key not in written_keys:
            new_lines.append(f"{key}={value}")

    ENV_FILE.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def get_output_dir() -> Path:
    """
    Output directory for all generated files (audio, reports, screenshots).
    Defaults to ~/.gauntlet/ -- overridable in Settings > Workspace.
    Reads config.json at call time so the running app picks up changes live.
    """
    if CONFIG_FILE.exists():
        try:
            cfg = json.loads(CONFIG_FILE.read_text())
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
