from google import genai
from google.genai import types


def get_gemini_client():
    import os
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError(
            "GEMINI_API_KEY environment variable is not set. "
            "Set it to your Google AI API key."
        )
    return genai.Client(api_key=api_key)


def analyze_with_gemini(prompt_context, code_snippet):
    client = get_gemini_client()
    response = client.models.generate_content(
        model='gemini-1.5-flash',
        contents=f"{prompt_context}\n\nCode:\n{code_snippet}",
        config=types.GenerateContentConfig(
            system_instruction="You are JARVIS Safety Guard. Analyze code for execution safety.",
        ),
    )
    return response.text
