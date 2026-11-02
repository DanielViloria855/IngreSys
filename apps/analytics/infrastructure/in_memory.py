"""Infraestructura (analytics): adaptadores en memoria para pruebas."""
from apps.analytics.application.dtos import DashboardMetricsDTO, InsightsResult
from apps.analytics.application.ports import InsightCache, MetricsRepository
from apps.analytics.domain.metrics import DateRange


class InMemoryMetricsRepository(MetricsRepository):
    """Adaptador secundario (falso): devuelve métricas predefinidas por clave de rango."""

    def __init__(self, default: DashboardMetricsDTO, by_key: dict[str, DashboardMetricsDTO] | None = None):
        self._default = default
        self._by_key = by_key or {}

    def get_metrics(self, date_range: DateRange) -> DashboardMetricsDTO:
        return self._by_key.get(date_range.key, self._default)


class InMemoryInsightCache(InsightCache):
    """Adaptador secundario (falso): caché en un diccionario."""

    def __init__(self):
        self.store: dict[tuple[str, str], InsightsResult] = {}

    def get(self, range_key: str, metrics_hash: str) -> InsightsResult | None:
        return self.store.get((range_key, metrics_hash))

    def save(self, range_key: str, metrics_hash: str, result: InsightsResult) -> None:
        self.store[(range_key, metrics_hash)] = result
