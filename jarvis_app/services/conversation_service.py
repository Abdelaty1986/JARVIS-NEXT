import json
import uuid
from datetime import datetime, timezone

from jarvis_app.utils.text_normalizer import has_arabic, normalize_text


GREETING_AR = "مرحباً بك في JARVIS-NEXT! أنا جاهز. كيف يمكنني مساعدتك اليوم؟"
GREETING_EN = "Welcome to JARVIS-NEXT! I'm ready. How can I help you today?"


class ConversationService:
    def __init__(self, memory_dir):
        self.memory_dir = memory_dir
        self.history_path = memory_dir / "conversation_history.json"
        self._load()

    def _load(self):
        if self.history_path.exists():
            try:
                self._history = json.loads(self.history_path.read_text(encoding="utf-8"))
            except Exception:
                self._history = []
        else:
            self._history = []
        self._session_context = {}

    def _save(self):
        self.history_path.write_text(
            json.dumps(self._history[-100:], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def greet(self):
        return {"role": "assistant", "content": GREETING_AR if self._session_context.get("arabic") else GREETING_EN}

    def process_message(self, message):
        if not message:
            return {"ok": False, "error": "Empty message"}
        is_arabic = has_arabic(message)
        self._session_context["arabic"] = is_arabic
        normalized = normalize_text(message)

        user_entry = {
            "id": str(uuid.uuid4()),
            "role": "user",
            "content": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._history.append(user_entry)

        if is_arabic:
            response_text = self._generate_arabic_response(message, normalized)
        else:
            response_text = self._generate_english_response(message, normalized)

        assistant_entry = {
            "id": str(uuid.uuid4()),
            "role": "assistant",
            "content": response_text,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._history.append(assistant_entry)
        self._save()

        return {
            "ok": True,
            "user_message": user_entry,
            "assistant_message": assistant_entry,
            "normalized": normalized,
        }

    def _generate_arabic_response(self, original, normalized):
        if any(w in original for w in ["مرحبا", "اهلا", "السلام", "هلا"]):
            return "مرحباً! أنا جاهز تماماً. يمكنني تنفيذ المهام الهندسية، إنشاء الصفحات، بناء المشاريع، وتحليل النظام. ماذا تريد أن تفعل؟"
        if any(w in original for w in ["جاهز", "اشتغال", "شغال"]):
            return "نعم، أنا جاهز! جميع الأنظمة تعمل. يمكنك طلب إنشاء صفحة، بناء مشروع، أو فحص النظام."
        if any(w in original for w in ["شكرا", "شكراً", "يسلمو"]):
            return "العفو! أنا هنا لمساعدتك في أي وقت."
        if any(w in original for w in ["الوداع", "مع السلامة", "باي"]):
            return "مع السلامة! أراك لاحقاً."
        task_keywords = ["انشاء", "صمم", "اعمل", "ابني", "طور", "عدل", "اصلح", "افحص", "مسح"]
        if any(w in original for w in task_keywords):
            return f"فهمت طلبك! سأقوم بتوجيهه إلى المحرك المناسب. سيتم معالجة: {original[:100]}..."
        return f"تم استلام رسالتك. سأقوم بتحليلها ومعالجتها. هل لديك مهمة محددة تريد تنفيذها؟"

    def _generate_english_response(self, original, normalized):
        if any(w in normalized for w in ["hello", "hi", "hey", "greetings"]):
            return "Hello! I'm fully operational. I can handle engineering tasks, create pages, build projects, scan systems, and more. What would you like me to do?"
        if any(w in normalized for w in ["ready", "active", "online"]):
            return "Yes, I'm ready! All systems operational. You can request page creation, project building, system scanning, or any engineering task."
        if any(w in normalized for w in ["thank", "thanks"]):
            return "You're welcome! I'm here to help with any task."
        if any(w in normalized for w in ["bye", "goodbye", "see you"]):
            return "Goodbye! See you later."
        task_keywords = ["create", "build", "make", "design", "modify", "fix", "scan", "refactor"]
        if any(w in normalized for w in task_keywords):
            return f"I understand your request! Routing to the appropriate engine. Processing: {original[:100]}..."
        return f"Message received. I'll analyze and process it. Do you have a specific task you'd like me to execute?"

    def get_history(self, limit=50):
        return self._history[-limit:]

    def clear_history(self):
        self._history = []
        self._session_context = {}
        self._save()
        return {"ok": True}
