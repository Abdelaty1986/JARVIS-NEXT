import os
import subprocess
from pathlib import Path
from jarvis.core.egyptian_voice_prompts import EgyptianVoicePrompts


def _in_termux():
    return (
        os.environ.get("TERMUX_VERSION") is not None
        or os.environ.get("PREFIX") == "/data/data/com.termux/files/usr"
        or Path("/data/data/com.termux/files/usr/bin/termux-tts-speak").exists()
        or Path("/data/data/com.termux/files/usr/bin").exists()
    )


class JarvisVoiceRuntime:
    """
    Real Arabic/Egyptian voice runtime narrator using Termux TTS.
    """

    def __init__(
        self,
        enabled=True,
        tts_enabled=True,
        dialect="egyptian",
        voice_profile="jarvis_like_arabic",
        speech_rate=0.88,
        speech_pitch=0.82,
    ):
        self.enabled = enabled
        self.tts_enabled = tts_enabled
        self.dialect = dialect
        self.voice_profile = voice_profile
        self.speech_rate = speech_rate
        self.speech_pitch = speech_pitch
        self.prompts = EgyptianVoicePrompts()
        self.in_termux = _in_termux()

    def speak(self, message):
        if not self.enabled:
            return

        if not self.tts_enabled:
            return

        if not self.in_termux:
            return

        try:
            subprocess.run(
                [
                    "termux-tts-speak",
                    "-r", str(self.speech_rate),
                    "-p", str(self.speech_pitch),
                    message,
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            print(f"[VoiceRuntime] Termux TTS: {message[:60]}...")
        except FileNotFoundError:
            print("[VoiceRuntime] termux-tts-speak not found — TTS unavailable")
        except Exception as exc:
            print(f"[VoiceRuntime] Termux TTS error: {exc}")

    def announce_start(self, task):
        self.speak(self.prompts.start(task))

    def announce_planning(self):
        self.speak(self.prompts.planning())

    def announce_validation(self):
        self.speak(self.prompts.validation())

    def announce_tests(self, passed=True):
        if passed:
            self.speak(self.prompts.tests_passed())
        else:
            self.speak(self.prompts.tests_failed())

    def announce_apply_mode(self, mode):
        if mode == "gated_apply":
            self.speak(self.prompts.gated_mode())
        else:
            self.speak(self.prompts.simulation_mode())

    def announce_completion(self):
        self.speak(self.prompts.completed())

    def announce_blocked(self, reason):
        self.speak(self.prompts.blocked(reason))
