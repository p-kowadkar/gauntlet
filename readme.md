# ⚔️ Gauntlet

**Adversarial agent testing as a desktop overlay.**

Gauntlet is an always-on-top PyQt6 overlay that red-teams enterprise AI agents in real time. Paste a system prompt, pick a domain, hit run -- Gauntlet researches real-world failure patterns, generates adversarial attacks, runs live simulations through Veris, scores risk, hardens your prompt, and delivers an executive voice briefing. All while you keep working.

Built at **Enterprise Agent Jam NYC 2026**.

---

## What it does

### ⚔️ Gauntlet Tab -- Adversarial Pipeline

5-agent sequential pipeline. Each agent operates from a bounded SKILLS registry -- the LLM picks which skill to invoke, and cannot invent behavior outside that registry. Hallucination is architecturally impossible at the invocation layer.

```
ResearchAgent → AdversarialAgent → SimulationAgent → RiskAgent → VoiceAgent
```

**ResearchAgent** -- hits You.com Search API for real-world failure cases in your domain. Runs three parallel searches: general failures, compliance risks, and known exploits. Returns up to 15 deduplicated findings grounded in live web data.

**AdversarialAgent** -- uses GLM-5 (Baseten) to generate 20 adversarial test cases across 4 attack categories: prompt injection, scope creep, auth bypass, and data exfiltration. Each test case is grounded in the research findings and tailored to the agent's system prompt.

**SimulationAgent** -- runs all 20 test cases through Veris, a live agent simulation sandbox. Veris deploys LLM-powered personas that interact with the target agent in realistic scenarios. Returns pass/fail per test case with root cause analysis. Falls back to realistic mock results if Veris is not configured.

**RiskAgent** -- synthesizes simulation results into a structured risk assessment: risk score (0-100), severity level (LOW / MEDIUM / HIGH / CRITICAL), top 3 critical findings, and a hardened version of the original system prompt with specific guardrails added for each discovered vulnerability.

**VoiceAgent** -- synthesizes an executive briefing via OpenAI TTS (nova voice), writes a full JSON report, and saves both to the configured output directory.

### 💬 Assist Tab -- Grounded Chat

Multi-agent chat assistant with real-time web search grounding via You.com.

- **Search toggle** -- when ON, fan-out/fan-in orchestration: GLM-5 classifies query complexity, parallel You.com searches run for each sub-question, results are merged and fed to the LLM as grounding context. When OFF, direct LLM response, fast.
- **Model display** -- every response shows which model generated it (GLM-5 via Baseten or gpt-5.4-mini).
- **Regenerate button** -- regenerate any response with the other available model.
- Primary model: GLM-5 (Baseten). Fallback: gpt-5.4-mini (OpenAI, reasoning mode).

### 🖥️ Screen Tab -- Vision Analysis

Same as Assist, plus:

- **📸 Analyze Screen** -- captures a full-screen screenshot, scales it down to 1280px wide JPEG for the API payload, sends to Kimi K2.5 (Baseten's vision model), returns a natural language description of what's on screen.
- Screenshots are saved to `{output_dir}/screen/screen_{timestamp}.png` at full resolution for reference.

### ⚙️ Settings

- **🔑 API Keys** -- auto-reads from `.env`, shows masked keys with 👁 toggle, validates each key by making a real API call (not just a length check), saves back to `.env` on Save.
- **🎨 Appearance** -- overlay opacity slider.
- **📁 Workspace** -- output directory picker. All generated files (audio, reports, screenshots) go here.

---

## Model Stack

| Role | Model | Provider | Notes |
|---|---|---|---|
| Primary LLM | `zai-org/GLM-5` | Baseten | 744B MoE, $0.95/M in, $3.15/M out |
| Vision | `moonshotai/Kimi-K2.5` | Baseten | Only vision model on Baseten Model APIs |
| Fallback LLM | `gpt-5.4-mini` | OpenAI | Reasoning model -- `max_completion_tokens`, no temperature |
| TTS | `tts-1` (nova) | OpenAI | Executive voice briefing |
| Search | Search API | You.com | Real-time web + news, LLM-ready snippets |
| Simulation | Veris | Veris AI | Live agent sandbox with LLM personas |

---

## Code Analysis Agent (`veris_code_agent/`)

A separate agent deployable to Veris that analyzes Python code using an **adversarial consensus pipeline**:

```
Code Input
    │
    ▼ Static Analysis (AST) + Runtime Analysis (subprocess timeout)
    │
    ▼ FAN-OUT (parallel)
GLM-5 analysis ────── gpt-5.4-mini analysis
    │                        │
    ▼ CROSS-CRITIQUE (parallel)
GLM-5 critiques mini ── mini critiques GLM-5
              │
              ▼ FINAL JUDGE
         gpt-5.4 synthesizes
              │
              ▼
       Authoritative report
```

**Layer 1 -- AST static analysis:** Detects infinite loops (`while True` with no break), bare excepts, mutable default arguments, off-by-one index access (`range(len(x)+1)`), unclosed file handles, and recursive functions with no base case.

**Layer 2 -- Runtime analysis:** Executes the code in a subprocess with a 5-second hard timeout. A timeout confirms an actual live infinite loop, not just a static suspicion.

**Layer 3 -- Adversarial consensus:** GLM-5 and gpt-5.4-mini independently analyze the combined static + runtime report, then each critiques the other's conclusions. gpt-5.4 (full reasoning model) reads all four outputs and synthesizes the final authoritative verdict.

The agent runs as a FastAPI service inside a Veris sandbox. Veris generates scenarios that test whether the agent correctly identifies each class of bug.

### Deploy the Code Agent

```bash
cd gauntlet/veris_code_agent

veris env create --name "gauntlet-code-analyzer"
veris env vars set OPENAI_API_KEY=<key> --secret
veris env vars set BASETEN_API_KEY=<key> --secret
veris env push
veris scenarios create --num 10
veris run
```

---

## Architecture -- Why the SKILLS registry matters

Every agent in Gauntlet runs from a bounded SKILLS registry defined at class level. The LLM decides which skill to invoke -- it cannot invent new behaviors or call arbitrary functions outside the registry.

```python
class AdversarialAgent(AgentBase):
    SKILLS = {
        "gen_prompt_injection": ...,
        "gen_scope_creep":      ...,
        "gen_auth_bypass":      ...,
        "gen_data_exfil":       ...,
    }
```

This is topology-level reliability. The agent cannot hallucinate a skill call that doesn't exist. Errors are bounded and predictable. This is not a prompt trick -- it's a structural constraint enforced at the invocation layer.

---

## Requirements

- Python 3.11+
- Windows / macOS / Linux (PyQt6)
- Docker (for `veris_code_agent` deployment only)
- API keys: OpenAI, You.com, Baseten (required for primary models), Veris (optional -- CLI auth via `veris login` works)

---

## Install

```bash
pip install -r requirements.txt
```

---

## Configuration

Copy `.env.example` to `.env` and fill in your keys:

```env
OPENAI_API_KEY=
YOUCOM_API_KEY=
BASETEN_API_KEY=
VERIS_API_KEY=           # optional -- CLI auth works too
VERIS_ENV_ID=            # Card Replacement Agent environment
VERIS_RUN_ID=            # completed simulation run ID (for instant results)
```

Keys can also be set and validated directly from the Settings dialog inside the app.

Enable required models on Baseten at `app.baseten.co/model-apis/create`:
- `zai-org/GLM-5`
- `moonshotai/Kimi-K2.5`

---

## Run

```bash
# Launch the overlay
python main.py

# Pipeline smoke test (terminal, no UI)
python test_pipeline.py
```

---

## Project Layout

```
gauntlet/
├── agents/
│   ├── research_agent.py      # You.com search, 3 parallel queries
│   ├── adversarial_agent.py   # GLM-5 attack generation, 4 attack types × 5 cases
│   ├── simulation_agent.py    # Veris SDK integration + mock fallback
│   ├── risk_agent.py          # Risk scoring + prompt hardening + exec summary
│   └── voice_agent.py         # OpenAI TTS + JSON report export
├── core/
│   ├── agent_base.py          # AgentBase ABC with SKILLS registry enforcement
│   └── pipeline.py            # Sequential orchestrator with per-agent error isolation
├── ui/
│   ├── overlay.py             # Frameless always-on-top window, tab routing
│   ├── gauntlet_panel.py      # Pipeline UI -- spec input, step indicators, results
│   ├── assist_panel.py        # Grounded chat -- search toggle, model label, regenerate
│   ├── screen_panel.py        # Vision analysis -- screenshot capture + Kimi K2.5
│   ├── settings_dialog.py     # API key management, appearance, workspace
│   └── components.py          # Shared colors, StepIndicator, RiskScoreWidget
├── utils/
│   └── thread_worker.py       # QThread pipeline worker with signals
├── veris_code_agent/
│   ├── app/
│   │   ├── main.py            # FastAPI agent -- adversarial consensus pipeline
│   │   └── analyzer.py        # AST static + subprocess runtime analysis
│   ├── code/
│   │   └── demo_file.py       # Demo file with 6 deliberate bugs
│   ├── .veris/
│   │   ├── veris.yaml         # HTTP actor config for Veris sandbox
│   │   └── Dockerfile.sandbox # Agent container definition
│   └── requirements.txt
├── config.py                  # All constants, ENV_FILE, read_env(), write_env()
├── main.py                    # App entry point, SIGINT handler, QTimer
├── requirements.txt
└── test_pipeline.py
```

---

## Outputs

Default output directory: `~/.gauntlet/`
Configurable in Settings → Workspace.

| File | Description |
|---|---|
| `briefing.mp3` | Executive voice briefing (OpenAI TTS, nova) |
| `report.json` | Full pipeline output -- test cases, simulation results, risk assessment, hardened prompt |
| `screen/screen_<timestamp>.png` | Full-resolution screenshots from Screen tab |

---

## Sponsors

Built with:
- [Baseten](https://baseten.co) -- GLM-5 and Kimi K2.5 inference
- [You.com](https://you.com) -- real-time web search API
- [Veris](https://veris.ai) -- live agent simulation sandbox
- [OpenAI](https://openai.com) -- gpt-5.4-mini fallback + TTS
- [VoiceRun](https://voicerun.com) -- production voice delivery layer

---

## License

AGPL-3.0
