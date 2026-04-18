"""
Gauntlet Code Analysis Agent -- FastAPI service for Veris sandbox.

Adversarial Consensus Pipeline:
  1. Static analysis (AST) + runtime analysis (subprocess timeout)
  2. FAN-OUT: GLM-5 AND gpt-5.4-mini analyze in parallel
  3. CROSS-CRITIQUE: each model critiques the other's analysis in parallel
  4. FINAL JUDGE: gpt-5.4 (full reasoning) synthesizes everything
  5. Response delivered via HTTP (VoiceRun handles voice in production)

Accepts: POST /chat {"message": "...", "session_id": "..."}
Returns: {"response": "...", "session_id": "..."}
"""

import os
import json
import concurrent.futures
from pathlib import Path

import openai
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.analyzer import static_analysis, runtime_analysis, format_issues, format_runtime

# ---------------------------------------------------------------------------
# Clients
# ---------------------------------------------------------------------------
BASETEN_BASE_URL   = "https://inference.baseten.co/v1"
BASETEN_MODEL_SLUG = "zai-org/GLM-5"
OPENAI_MINI_MODEL  = "gpt-5.4-mini"
OPENAI_FULL_MODEL  = "gpt-5.4"          # final judge -- full reasoning model

baseten_client = openai.OpenAI(
    base_url=BASETEN_BASE_URL,
    api_key=os.environ.get("BASETEN_API_KEY", ""),
)
openai_client = openai.OpenAI(
    api_key=os.environ.get("OPENAI_API_KEY", ""),
)

CODE_DIR = Path("/agent/code")           # files baked into the Docker image

app = FastAPI(title="Gauntlet Code Analysis Agent")


# ---------------------------------------------------------------------------
# Request / Response schema
# ---------------------------------------------------------------------------
class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"


class ChatResponse(BaseModel):
    response: str
    session_id: str


# ---------------------------------------------------------------------------
# LLM helpers
# ---------------------------------------------------------------------------
def _glm5(messages: list, max_tokens: int = 1500) -> str:
    resp = baseten_client.chat.completions.create(
        model=BASETEN_MODEL_SLUG,
        messages=messages,
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content.strip()


def _mini(messages: list, max_tokens: int = 1500) -> str:
    resp = openai_client.chat.completions.create(
        model=OPENAI_MINI_MODEL,
        messages=messages,
        max_completion_tokens=max_tokens,
        reasoning={"effort": "high"},
    )
    return resp.choices[0].message.content.strip()


def _gpt54_judge(messages: list, max_tokens: int = 2000) -> str:
    """Full gpt-5.4 as the final synthesis judge."""
    resp = openai_client.chat.completions.create(
        model=OPENAI_FULL_MODEL,
        messages=messages,
        max_completion_tokens=max_tokens,
        reasoning={"effort": "high"},
    )
    return resp.choices[0].message.content.strip()


# ---------------------------------------------------------------------------
# Adversarial consensus pipeline
# ---------------------------------------------------------------------------
def _analyze_with_model(model: str, code: str, static_report: str, runtime_report: str) -> str:
    prompt = f"""You are a senior software engineer reviewing Python code for bugs and issues.

Static analysis found these issues:
{static_report}

Runtime analysis result:
{runtime_report}

Code under review:
```python
{code}
```

Provide a clear, structured analysis of ALL bugs found. For each bug:
- State the line number
- Describe what the bug is in plain English
- Explain why it is dangerous
- Suggest a specific fix

Be thorough. Do not miss any issues flagged by static analysis."""

    messages = [{"role": "user", "content": prompt}]
    if model == "glm5":
        return _glm5(messages)
    else:
        return _mini(messages)


def _critique(critic_model: str, critic_analysis: str, other_analysis: str) -> str:
    prompt = f"""You are reviewing another engineer's code analysis. Your job is to find any bugs, 
omissions, or incorrect conclusions in their report.

Their analysis:
{other_analysis}

Your previous analysis:
{critic_analysis}

Critique the other engineer's analysis:
- What did they miss or get wrong?
- What did they get right?
- What would you add or correct?

Be specific and constructive."""

    messages = [{"role": "user", "content": prompt}]
    if critic_model == "glm5":
        return _glm5(messages, max_tokens=800)
    else:
        return _mini(messages, max_tokens=800)


def _synthesize(code: str, glm5_analysis: str, mini_analysis: str,
                glm5_critique: str, mini_critique: str) -> str:
    prompt = f"""You are the final authority in a code review consensus process.

Two senior engineers analyzed the same Python code, then critiqued each other.
Your job: synthesize everything into the single most accurate and complete bug report.

=== GLM-5 Analysis ===
{glm5_analysis}

=== gpt-5.4-mini Analysis ===
{mini_analysis}

=== GLM-5's critique of gpt-5.4-mini ===
{glm5_critique}

=== gpt-5.4-mini's critique of GLM-5 ===
{mini_critique}

Produce the final authoritative report:
1. List every confirmed bug with line number, severity (CRITICAL/HIGH/MEDIUM), plain-English explanation, and fix
2. Note any disagreements between the models and your resolution
3. Give an overall risk assessment: SAFE / NEEDS REVIEW / DANGEROUS
4. One-sentence executive summary suitable for a voice briefing

Format clearly with sections. Be definitive -- you are the final word."""

    messages = [{"role": "user", "content": prompt}]
    return _gpt54_judge(messages)


def run_adversarial_consensus(code: str, filename: str) -> str:
    """Full 4-stage adversarial consensus pipeline."""

    # Stage 1: Static + runtime analysis
    static_issues = static_analysis(code)
    runtime_result = runtime_analysis(code)
    static_report  = format_issues(static_issues)
    runtime_report = format_runtime(runtime_result)

    # Stage 2: Fan-out -- GLM-5 and gpt-5.4-mini analyze in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        glm5_future = ex.submit(_analyze_with_model, "glm5", code, static_report, runtime_report)
        mini_future = ex.submit(_analyze_with_model, "mini", code, static_report, runtime_report)
        glm5_analysis = glm5_future.result()
        mini_analysis = mini_future.result()

    # Stage 3: Cross-critique in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        # GLM-5 critiques mini's analysis; mini critiques GLM-5's analysis
        glm5_critique_future = ex.submit(_critique, "glm5", glm5_analysis, mini_analysis)
        mini_critique_future = ex.submit(_critique, "mini", mini_analysis, glm5_analysis)
        glm5_critique = glm5_critique_future.result()
        mini_critique = mini_critique_future.result()

    # Stage 4: Final synthesis by gpt-5.4 (full)
    final = _synthesize(code, glm5_analysis, mini_analysis, glm5_critique, mini_critique)

    # Wrap with context
    runtime_note = ""
    if runtime_result["timed_out"]:
        runtime_note = "\n\n⏱️  NOTE: Code execution timed out during runtime analysis -- confirmed live infinite loop or recursion."

    return (
        f"# Code Analysis Report: {filename}\n\n"
        f"{final}"
        f"{runtime_note}"
    )


# ---------------------------------------------------------------------------
# Request routing
# ---------------------------------------------------------------------------
def _resolve_file(message: str) -> tuple[str | None, str]:
    """
    Extract filename from message and read from CODE_DIR.
    Returns (code_content, filename) or (None, error_message).
    """
    # Look for known filenames in the message
    msg_lower = message.lower()

    # Check for explicit filenames
    for candidate in CODE_DIR.glob("*.py"):
        if candidate.name.lower() in msg_lower or candidate.stem.lower() in msg_lower:
            code = candidate.read_text(encoding="utf-8")
            return code, candidate.name

    # Default to demo_file.py if message says "demo", "analyze", "check", etc.
    trigger_words = ["demo", "analyze", "check", "review", "scan", "inspect", "test"]
    if any(w in msg_lower for w in trigger_words):
        demo = CODE_DIR / "demo_file.py"
        if demo.exists():
            return demo.read_text(encoding="utf-8"), "demo_file.py"

    # List available files
    available = [f.name for f in CODE_DIR.glob("*.py")]
    return None, (
        f"Please specify which file to analyze. Available files: {', '.join(available)}\n"
        f"Example: 'analyze demo_file.py'"
    )


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    message = req.message.strip()

    # Handle greetings / capability questions
    if any(w in message.lower() for w in ["hello", "hi", "help", "what can you", "capabilities"]):
        available = [f.name for f in CODE_DIR.glob("*.py")]
        return ChatResponse(
            response=(
                "I am the Gauntlet Code Analysis Agent. I use an adversarial consensus pipeline "
                "-- GLM-5 and gpt-5.4-mini analyze your code in parallel, critique each other, "
                "then gpt-5.4 synthesizes the final verdict.\n\n"
                f"Available files to analyze: {', '.join(available)}\n\n"
                "Say 'analyze demo_file.py' to get started."
            ),
            session_id=req.session_id,
        )

    # Resolve file and run pipeline
    code, filename_or_error = _resolve_file(message)
    if code is None:
        return ChatResponse(response=filename_or_error, session_id=req.session_id)

    try:
        report = run_adversarial_consensus(code, filename_or_error)
        return ChatResponse(response=report, session_id=req.session_id)
    except Exception as e:
        return ChatResponse(
            response=f"Pipeline error: {str(e)}",
            session_id=req.session_id,
        )


@app.get("/health")
async def health():
    return {"status": "ok", "agent": "gauntlet-code-analyzer"}
