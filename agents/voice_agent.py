"""
Audio synthesis: OpenAI TTS (tts-1, nova voice).
VoiceRun is the production deployment layer -- not called directly here.

VoiceRun demo approach:
  - OpenAI TTS synthesizes the briefing audio live in the overlay
  - At demo time: open voicerun.com/developers and explain that in
    production, Gauntlet triggers a VoiceRun voice agent call to the
    security team automatically when risk score exceeds threshold

VoiceRun SDK reference (production integration):
    pip install voicerun
    from voicerun import VoiceAgent, TextToSpeechEvent, StartEvent

    class BriefingAgent(VoiceAgent):
        async def handler(self, event, context, emit):
            if isinstance(event, StartEvent):
                emit(TextToSpeechEvent(self.briefing_text, voice="nova"))
"""
import os
import json
from pathlib import Path

import openai
from config import OPENAI_API_KEY, get_output_dir
from core.agent_base import AgentBase

tts_client = openai.OpenAI(api_key=OPENAI_API_KEY)


def _synthesize_briefing(text: str, voice: str = "nova") -> str:
    """
    Synthesize text to speech via OpenAI TTS API (tts-1 model).
    Returns path to the generated .mp3 file.
    Voices: alloy, echo, fable, onyx, nova, shimmer
    """
    out_path = get_output_dir() / "briefing.mp3"
    try:
        response = tts_client.audio.speech.create(
            model="tts-1",
            voice=voice,
            input=text,
        )
        response.stream_to_file(str(out_path))
        return str(out_path) if out_path.exists() else ""
    except Exception as e:
        print(f"[VoiceAgent] TTS failed: {e}")
        return ""


def _play_audio(file_path: str) -> bool:
    if not file_path or not os.path.exists(file_path):
        return False
    try:
        if os.name == "nt":
            os.startfile(file_path)
        else:
            import subprocess
            subprocess.Popen(["xdg-open", file_path])
        return True
    except Exception:
        return False


def _export_report(context: dict, output_path: str) -> str:
    report = {
        "domain":          context.get("domain"),
        "risk_assessment": context.get("risk_assessment"),
        "failure_summary": context.get("failure_summary"),
        "root_causes":     context.get("root_causes"),
        "hardened_prompt": context.get("hardened_prompt"),
        "test_cases":      context.get("test_cases"),
    }
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(report, f, indent=2)
    return str(path)


class VoiceAgent(AgentBase):
    SKILLS = {
        "synthesize_briefing": _synthesize_briefing,
        "play_audio":          _play_audio,
        "export_report":       _export_report,
    }

    def run(self, context: dict) -> dict:
        audio_path = self.invoke_skill(
            "synthesize_briefing",
            text=context.get("exec_summary", "Risk assessment complete."),
        )
        played = False
        if audio_path:
            played = self.invoke_skill("play_audio", file_path=audio_path)

        report_path = self.invoke_skill(
            "export_report",
            context=context,
            output_path=str(get_output_dir() / "report.json"),
        )
        return {
            "audio_path":   audio_path,
            "audio_played": played,
            "report_path":  report_path,
        }
