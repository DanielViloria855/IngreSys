"""Aplicación (analytics): casos de uso."""
import hashlib
import json
from dataclasses import replace
from datetime import datetime, timezone
from typing import Callable

from apps.analytics.application.dtos import DashboardMetricsDTO, InsightsResult
from apps.analytics.application.ports import InsightCache, InsightGenerator, MetricsRepository
from apps.analytics.domain.insight import InsightUnavailable
from apps.analytics.domain.metrics import DateRange
from shared.application.base import BaseUseCase

DELTA_FIELDS = ("trucks", "boxes", "pallets", "witness_samples", "novelty_entries")


def _pct_change(current: int, previous: int) -> float | None:
    if previous == 0:
        return None  # sin base de comparación: no se muestra variación
    return round((current - previous) / previous * 100, 1)


class GetDashboardMetrics(BaseUseCase[DateRange, DashboardMetricsDTO]):
    """Caso de uso (aplicación): métricas del rango + comparación con el periodo anterior."""

    def __init__(self, repository: MetricsRepository):
        self._repository = repository

    def execute(self, date_range: DateRange) -> DashboardMetricsDTO:
        current = self._repository.get_metrics(date_range)
        before = self._repository.get_metrics(date_range.previous())
        previous = {name: getattr(before, name) for name in DELTA_FIELDS}
        previous["range_label"] = before.range_label
        deltas = {name: _pct_change(getattr(current, name), getattr(before, name)) for name in DELTA_FIELDS}
        return replace(current, previous=previous, deltas=deltas)


class GenerateAIInsights(BaseUseCase[DashboardMetricsDTO, InsightsResult]):
    """Caso de uso (aplicación): interpreta las métricas con IA y cae a reglas si falla.

    1) Si las métricas no cambiaron, devuelve lo guardado en caché (no gasta cuota del LLM).
    2) Intenta el generador principal (p. ej. Groq).
    3) Si lanza InsightUnavailable, usa el generador de respaldo (reglas).
    """

    def __init__(
        self,
        primary: InsightGenerator,
        fallback: InsightGenerator,
        cache: InsightCache | None = None,
        clock: Callable[[], datetime] | None = None,
    ):
        self._primary = primary
        self._fallback = fallback
        self._cache = cache
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    @staticmethod
    def metrics_hash(metrics: DashboardMetricsDTO) -> str:
        payload = json.dumps(metrics.to_dict(), sort_keys=True, default=str)
        return hashlib.sha256(payload.encode()).hexdigest()

    def execute(self, metrics: DashboardMetricsDTO) -> InsightsResult:
        digest = self.metrics_hash(metrics)
        if self._cache is not None:
            cached = self._cache.get(metrics.range_key, digest)
            if cached is not None:
                return replace(cached, from_cache=True)
        try:
            insights = self._primary.generate(metrics)
            result = InsightsResult(insights, self._primary.model_name, self._clock())
            if self._cache is not None:
                self._cache.save(metrics.range_key, digest, result)
        except InsightUnavailable:
            insights = self._fallback.generate(metrics)
            result = InsightsResult(insights, self._fallback.model_name, self._clock(), fallback_used=True)
        return result
