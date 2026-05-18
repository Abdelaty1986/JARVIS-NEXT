import argparse
import os
import subprocess
import sys
from pathlib import Path

from jarvis.core.conversation_brain import ConversationBrain
from jarvis.core.voice_runtime import JarvisVoiceRuntime
from jarvis.execution.sandbox_execution_report import SandboxExecutionReport
from jarvis.voice.elevenlabs_tts_provider import ElevenLabsTTSProvider
from jarvis.voice.mic_recorder import MicRecorder
from jarvis.voice.transcription_provider import TranscriptionProvider


def _in_termux():
    return (
        os.environ.get("TERMUX_VERSION") is not None
        or os.environ.get("PREFIX") == "/data/data/com.termux/files/usr"
        or Path("/data/data/com.termux/files/usr/bin/termux-tts-speak").exists()
        or Path("/data/data/com.termux/files/usr/bin").exists()
    )


def _termux_speak_direct(text, language="ar"):
    try:
        subprocess.run(
            ["termux-tts-speak", "-l", language, text],
            check=False, timeout=30,
        )
        return True
    except FileNotFoundError:
        print("[DirectTTS] termux-tts-speak not found")
        return False
    except Exception as exc:
        print(f"[DirectTTS] error: {exc}")
        return False


class LiveJarvisLoop:
    def __init__(self, tts_enabled=False, mic_mode=False):
        self.brain = ConversationBrain()
        self.voice = JarvisVoiceRuntime(
            enabled=True,
            tts_enabled=tts_enabled,
        )
        self.elevenlabs = ElevenLabsTTSProvider() if tts_enabled else None
        self.recorder = MicRecorder() if mic_mode else None
        self.transcriber = TranscriptionProvider()
        self.running = True
        self.mic_mode = mic_mode
        self.in_termux = _in_termux()
        self._tts_fallback_logged = set()

    def _speak(self, message):
        print(f"JARVIS: {message}")

        # Stage 1: ElevenLabs if available
        if self.elevenlabs:
            try:
                result = self.elevenlabs.speak(message)
                provider = result.get("provider", "unknown")
                if provider == "elevenlabs":
                    return
                if provider == "fallback":
                    stage = "elevenlabs_fallback"
                    if stage not in self._tts_fallback_logged:
                        print(f"[TTS] ElevenLabs unavailable — using Termux TTS (via provider)")
                        self._tts_fallback_logged.add(stage)
                    return
            except Exception as exc:
                stage = "elevenlabs_exception"
                if stage not in self._tts_fallback_logged:
                    print(f"[TTS] ElevenLabs exception: {exc} — trying Termux TTS")
                    self._tts_fallback_logged.add(stage)

        # Stage 2: JarvisVoiceRuntime (Termux TTS via runtime)
        if self.voice:
            try:
                self.voice.speak(message)
                return
            except Exception as exc:
                stage = "voice_runtime_exception"
                if stage not in self._tts_fallback_logged:
                    print(f"[TTS] VoiceRuntime error: {exc}")
                    self._tts_fallback_logged.add(stage)

        # Stage 3: Direct termux-tts-speak
        if self.in_termux:
            ok = _termux_speak_direct(message)
            if ok:
                return
            stage = "direct_termux_failed"
            if stage not in self._tts_fallback_logged:
                print("[TTS] Direct termux-tts-speak also failed")
                self._tts_fallback_logged.add(stage)
        else:
            stage = "not_in_termux"
            if stage not in self._tts_fallback_logged:
                print("[TTS] Not running in Termux — no TTS available")
                self._tts_fallback_logged.add(stage)

    def _is_runtime_command(self, text):
        keywords = [
            "راجع",
            "افحص",
            "اختبر",
            "حلل",
            "sandbox",
            "الوضع الآمن",
            "النظام",
            "runtime",
        ]
        return any(word in text for word in keywords)

    def _run_safe_runtime(self, text):
        target = Path("JARVIS_CORE/jarvis/runtime/runtime_audit.py")
        original = target.read_text(encoding="utf-8")

        report = SandboxExecutionReport().run(
            task=text,
            file_path=str(target),
            proposed_content=(
                original
                + "\n# live_jarvis_loop_sandbox_marker\n"
            ),
            human_approval=None,
        )

        final_state = report.get("final_state")
        sandbox_ok = report.get("sandbox", {}).get("apply", {}).get("ok")
        tests_ok = report.get("sandbox", {}).get("post_test", {}).get("ok")
        original_modified = report.get("original_files_modified")
        approval_status = report.get("approval", {}).get("status")

        return (
            "تم تشغيل المهمة في الوضع الآمن.\n"
            f"حالة التقرير: {final_state}\n"
            f"Sandbox: {'ناجح' if sandbox_ok else 'يحتاج مراجعة'}\n"
            f"الاختبارات: {'ناجحة' if tests_ok else 'فشلت'}\n"
            f"الملف الأصلي اتعدل؟ {original_modified}\n"
            f"حالة الموافقة: {approval_status}\n"
            "لم يتم تنفيذ أي تعديل حقيقي."
        )

    def handle(self, text):
        normalized = text.strip()

        if not normalized:
            return "مسمعتش أمر واضح."

        if normalized in {"خروج", "انهاء", "اقفل", "نام"}:
            self.running = False
            return "تم إيقاف جلسة جارفيس."

        if normalized in {"حالتك", "انت شغال", "عامل ايه", "جاهز"}:
            return (
                "أنا شغال في الوضع الآمن. "
                "أقدر أراجع وأحلل وأعمل Sandbox Report، "
                "لكن لا أطبق تعديلات حقيقية بدون موافقة."
            )

        if self._is_runtime_command(normalized):
            return self._run_safe_runtime(normalized)

        brain_result = self.brain.respond(normalized)
        return brain_result.get(
            "response",
            "استلمت كلامك، لكن محتاج أمر أوضح."
        )

    def _get_input(self):
        if not self.mic_mode:
            return input("YOU: ").strip()

        audio_path = None
        try:
            audio_path = self.recorder.record(duration=10)
            text = self.transcriber.transcribe(audio_path)
            print(f"YOU (voice): {text}")
            return text.strip()
        except Exception as exc:
            print(f"[MIC] Voice input failed: {exc}")
            print("[MIC] التبديل إلى الإدخال النصي...")
            return input("YOU (fallback): ").strip()
        finally:
            if audio_path:
                Path(audio_path).unlink(missing_ok=True)

    def run(self):
        if self.in_termux:
            self._speak("أنا جاهز يا هاني. جارفيس يعمل الآن في الوضع الآمن.")
        else:
            print("JARVIS: أنا جاهز يا هاني. جارفيس يعمل الآن في الوضع الآمن.")

        while self.running:
            try:
                text = self._get_input()
                response = self.handle(text)
                self._speak(response)
            except KeyboardInterrupt:
                self._speak("تم إيقاف الجلسة.")
                break
            except Exception as exc:
                self._speak(f"حدث خطأ أثناء التشغيل: {exc}")


def main():
    parser = argparse.ArgumentParser(description="JARVIS Live Interactive Loop")
    parser.add_argument("--mic", action="store_true", help="Enable microphone recording mode")
    parser.add_argument("--tts", action="store_true", help="Enable TTS (ElevenLabs primary, termux fallback)")
    args = parser.parse_args()

    loop = LiveJarvisLoop(tts_enabled=args.tts, mic_mode=args.mic)
    loop.run()


if __name__ == "__main__":
    main()
