"""Infraestructura (analytics): asistente conversacional con un LLM (Groq)."""
import re

from apps.analytics.application.dtos import AskQuery
from apps.analytics.application.ports import AnalyticsAssistant
from apps.analytics.application.prompts import build_assistant_messages
from apps.analytics.domain.assistant import AssistantUnavailable


def clean_answer(text: str) -> str:
    """Deja la respuesta en texto plano: sin markdown y con espacios/guiones normales."""
    text = text.replace("\u202f", " ").replace("\u00a0", " ").replace("\u2011", "-")
    text = re.sub(r"(\*\*|__|`)", "", text)  # negritas y código
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text, flags=re.MULTILINE)  # encabezados
    text = re.sub(r"^\s*[-*]\s+", "• ", text, flags=re.MULTILINE)  # viñetas
    return re.sub(r"[ \t]+\n", "\n", text).strip()


class GroqAssistantAdapter(AnalyticsAssistant):
    """Adaptador secundario: responde preguntas sobre las métricas con un LLM vía Groq."""

    def __init__(self, api_key: str, model: str, timeout: float = 25.0):
        self._api_key = api_key
        self._model = model
        self._timeout = timeout
        self.model_name = f"Groq · {model}"

    def answer(self, query: AskQuery) -> str:
        if not self._api_key:
            raise AssistantUnavailable("Falta GROQ_API_KEY.")
        options = {}
        if self._model.startswith("openai/gpt-oss"):
            options["reasoning_effort"] = "low"  # respuestas más rápidas; el razonamiento largo no aporta aquí
        try:
            from groq import Groq

            client = Groq(api_key=self._api_key, timeout=self._timeout)
            completion = client.chat.completions.create(
                model=self._model,
                temperature=0.2,
                max_tokens=900,
                messages=build_assistant_messages(query),
                **options,
            )
            text = clean_answer(completion.choices[0].message.content or "")
        except Exception as exc:  # red, cuota, modelo inexistente…
            raise AssistantUnavailable(f"Groq no respondió: {exc}") from exc
        if not text:
            raise AssistantUnavailable("Groq devolvió una respuesta vacía.")
        return text
