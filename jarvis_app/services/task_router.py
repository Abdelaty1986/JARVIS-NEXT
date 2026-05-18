from jarvis_app.utils.text_normalizer import normalize_text, detect_task_type


class TaskRouter:
    def route(self, text):
        task_type = detect_task_type(text)
        return {
            "route": task_type,
            "normalized": normalize_text(text),
        }
