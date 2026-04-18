# Gauntlet
Ambient PyQt6 desktop overlay for adversarial testing of enterprise AI agents.

Gauntlet runs a 5-agent pipeline that researches risks, generates adversarial tests, simulates outcomes, scores risk, and produces an executive voice briefing.

## Current Capabilities
- Always-on-top overlay UI with tabs:
  - **Assist**: grounded chat assistant with optional real-time search and model regeneration
  - **Screen**: screenshot analysis flow with vision model inference
  - **Gauntlet**: full adversarial pipeline runner with progress and risk output
  - **Settings**: API key, appearance, and workspace/output configuration
- 5-agent pipeline:
  - Research → Adversarial → Simulation → Risk → Voice
- Model routing:
  - Primary: Baseten (GLM-5)
  - Vision: Baseten (Kimi K2.5)
  - Fallback: OpenAI gpt-5.4-mini (reasoning mode)
- Output artifacts (audio/report/screenshots) written to configurable output directory.

## Requirements
- Python 3.11+ recommended
- Windows/macOS/Linux
- API keys for one or more of:
  - OpenAI
  - You.com
  - Baseten
  - Veris

## Install
```bash
pip install -r requirements.txt
```

## Configuration
Set keys in `.env`:
```env
OPENAI_API_KEY=
YOUCOM_API_KEY=
BASETEN_API_KEY=
VERIS_API_KEY=
```

Notes:
- Baseten is used as primary model provider when configured.
- OpenAI fallback is used when Baseten is unavailable.
- Screen analysis (vision) requires Baseten vision model access.

## Run
Launch the full desktop overlay:
```bash
python main.py
```

Run pipeline smoke test from terminal:
```bash
python test_pipeline.py
```

## Project Layout
```text
gauntlet/
├── agents/
├── core/
├── ui/
├── utils/
├── config.py
├── main.py
├── requirements.txt
└── test_pipeline.py
```

## Outputs
Default output directory:
- `~/.gauntlet/`

Configurable in:
- Settings → Workspace → Output Directory

Typical generated files:
- `briefing.mp3`
- `report.json`
- `screen/screen_<timestamp>.png`
