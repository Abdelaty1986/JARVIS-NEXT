import os

from google import genai
from google.genai import types

from jarvis.agents.base_agent import BaseAgent


class GeminiAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="Gemini Free Agent",
            role="Architecture and Planning Assistant",
            provider="google_gemini",
            cost="free"
        )

        self.api_key = os.getenv("GEMINI_API_KEY")
        self._client = None

    def _get_client(self):
        if self._client is None:
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    def think(self, task):
        if not self.api_key:
            return {
                "agent": self.name,
                "task": task,
                "analysis": (
                    "GEMINI_API_KEY is not set. "
                    "Agent skipped safely."
                ),
                "risk_level": "unknown",
                "enabled": False,
                "approved_for_direct_apply": False
            }

        try:
            client = self._get_client()
            response = client.models.generate_content(
                model='gemini-1.5-flash',
                contents=f"You are Jarvis planning assistant. Analyze this task safely and briefly:\n\n{task}",
                config=types.GenerateContentConfig(
                    system_instruction="You are JARVIS architecture and planning assistant.",
                ),
            )
            content = response.text

            return {
                "agent": self.name,
                "task": task,
                "analysis": content,
                "risk_level": "medium",
                "enabled": True,
                "approved_for_direct_apply": False
            }

        except Exception as error:
            return {
                "agent": self.name,
                "task": task,
                "analysis": f"Gemini Agent error: {error}",
                "risk_level": "unknown",
                "enabled": False,
                "approved_for_direct_apply": False
            }


if __name__ == "__main__":
    agent = GeminiAgent()

    print(agent.info())

    print(
        agent.think(
            "Review Jarvis architecture safely"
        )
    )
