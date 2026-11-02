"""Infraestructura (analytics): adaptador del LLM (Groq, API compatible con OpenAI)."""
from apps.analytics.application.dtos import DashboardMetricsDTO
from apps.analytics.application.ports import InsightGenerator
from apps.analytics.application.prompts import SYSTEM_PROMPT, build_user_prompt, parse_insights
from apps.analytics.domain.insight import Insight, InsightUnavailable


class GroqInsightAdapter(InsightGenerator):
    """Adaptador secundario: interpreta métricas con un LLM vía Groq."""

    def __init__(self, api_key: str, model: str, timeout: float = 20.0):
        self._api_key = api_key
        self._model = model
        self._timeout = timeout
        self.model_name = f"Groq · {model}"

    def generate(self, metrics: DashboardMetricsDTO) -> list[Insight]:
        if not self._api_key:
            raise InsightUnavailable("Falta GROQ_API_KEY.")
        try:
            from groq import Groq

            client = Groq(api_key=self._api_key, timeout=self._timeout)
            completion = client.chat.completions.create(
                model=self._model,
                temperature=0.3,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": build_user_prompt(metrics)},
                ],
            )
            content = completion.choices[0].message.content
        except InsightUnavailable:
            raise
        except Exception as exc:  # red, cuota, modelo inexistente…
            raise InsightUnavailable(f"Groq no respondió: {exc}") from exc
        return parse_insights(content or "")
