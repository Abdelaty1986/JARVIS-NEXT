import json
import os
import subprocess
from datetime import datetime, timezone


class VoiceService:
    def __init__(self):
        self._enabled = True
        self._speaking = False
        self._muted = False
        self._stt_provider = "browser"
        self._tts_provider = "browser"
        self._check_providers()

    def _check_providers(self):
        if os.environ.get("OPENAI_API_KEY"):
            self._stt_provider = "whisper"
        if os.environ.get("ELEVENLABS_API_KEY"):
            self._tts_provider = "elevenlabs"

    def status(self):
        return {
            "enabled": self._enabled,
            "speaking": self._speaking,
            "muted": self._muted,
            "stt_provider": self._stt_provider,
            "tts_provider": self._tts_provider,
            "has_openai_key": bool(os.environ.get("OPENAI_API_KEY")),
            "has_elevenlabs_key": bool(os.environ.get("ELEVENLABS_API_KEY")),
        }

    def transcribe(self, audio_data=None):
        if not audio_data:
            return {"ok": False, "error": "No audio data", "text": ""}
        if self._stt_provider == "whisper":
            return self._whisper_stt(audio_data)
        return {"ok": True, "text": "[browser stt fallback]", "provider": "browser"}

    def _whisper_stt(self, audio_data):
        try:
            import openai
            client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=("audio.webm", audio_data, "audio/webm"),
                language="ar",
            )
            return {"ok": True, "text": transcript.text, "provider": "whisper"}
        except Exception as exc:
            return {"ok": False, "error": str(exc), "text": "", "provider": "whisper"}

    def respond(self, text):
        if self._muted:
            return {"ok": True, "provider": "muted"}
        self._speaking = True
        if self._tts_provider == "elevenlabs":
            result = self._elevenlabs_tts(text)
        else:
            result = {"ok": True, "provider": "browser", "text": text}
        self._speaking = False
        return result

    def _elevenlabs_tts(self, text):
        try:
            import requests
            api_key = os.environ.get("ELEVENLABS_API_KEY")
            if not api_key:
                return {"ok": False, "provider": "browser", "text": text, "error": "No API key"}
            url = "https://api.elevenlabs.io/v1/text-to-speech/21m00Tcm4TlvDq8ikWAM"
            resp = requests.post(url, json={"text": text, "voice_settings": {"stability": 0.5, "similarity_boost": 0.5}},
                                 headers={"xi-api-key": api_key}, timeout=30)
            if resp.status_code == 200:
                return {"ok": True, "provider": "elevenlabs", "audio": True}
            return {"ok": False, "provider": "browser", "text": text, "error": f"ElevenLabs {resp.status_code}"}
        except Exception as exc:
            return {"ok": False, "provider": "browser", "text": text, "error": str(exc)}

    def stop(self):
        self._speaking = False
        return {"ok": True}

    def mute(self):
        self._muted = not self._muted
        return {"muted": self._muted}
