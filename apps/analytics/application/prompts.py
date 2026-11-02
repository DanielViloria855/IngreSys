"""Aplicación (analytics): prompts del LLM y validación de su respuesta.

Privacidad: solo se envían datos AGREGADOS. Nunca nombres, cédulas ni placas individuales.
"""
import json

from apps.analytics.application.dtos import DashboardMetricsDTO
from apps.analytics.domain.insight import Insight, InsightLevel, InsightUnavailable

MAX_INSIGHTS = 5

SYSTEM_PROMPT = (
    "Eres un analista de logística de recibo de mercancía. Recibes métricas agregadas en JSON. "
    'Responde solo JSON con la forma {"insights":[{"level":"info|warning|alert","title":"...","message":"..."}]}, '
    "máximo 5 insights, en español, frases cortas, sin inventar datos que no estén en el JSON."
)


def build_user_prompt(metrics: DashboardMetricsDTO) -> str:
    """JSON de métricas + rango + comparación con el periodo anterior (si existe)."""
    data = metrics.to_dict()
    data.pop("range_key", None)
    return json.dumps(data, ensure_ascii=False)


def parse_insights(content: str) -> list[Insight]:
    """Valida la respuesta del LLM. Si el JSON no sirve lanza InsightUnavailable (activa el respaldo por reglas)."""
    try:
        payload = json.loads(content)
        raw_items = payload["insights"]
        if not isinstance(raw_items, list):
            raise TypeError("insights no es una lista")
        insights = [
            Insight(
                level=InsightLevel(str(item["level"]).lower()),
                title=str(item["title"]).strip(),
                message=str(item["message"]).strip(),
            )
            for item in raw_items
        ]
    except (ValueError, KeyError, TypeError) as exc:
        raise InsightUnavailable(f"Respuesta del LLM inválida: {exc}") from exc
    if not insights:
        raise InsightUnavailable("El LLM no devolvió insights.")
    return insights[:MAX_INSIGHTS]
