"""Aplicación (analytics): puertos."""
from abc import ABC, abstractmethod

from apps.analytics.application.dtos import DashboardMetricsDTO, InsightsResult
from apps.analytics.domain.insight import Insight
from apps.analytics.domain.metrics import DateRange


class MetricsRepository(ABC):
    """Puerto (aplicación): contrato para obtener métricas agregadas de un rango."""

    @abstractmethod
    def get_metrics(self, date_range: DateRange) -> DashboardMetricsDTO:
        """Métricas del rango (sin comparación con el periodo anterior)."""


class InsightGenerator(ABC):
    """Puerto (aplicación): contrato para generar insights a partir de métricas."""

    model_name: str = ""

    @abstractmethod
    def generate(self, metrics: DashboardMetricsDTO) -> list[Insight]:
        """Devuelve hasta 5 insights. Lanza InsightUnavailable si no puede responder."""


class InsightCache(ABC):
    """Puerto (aplicación): contrato de caché de insights por rango y hash de métricas."""

    @abstractmethod
    def get(self, range_key: str, metrics_hash: str) -> InsightsResult | None:
        """Insights guardados para esas métricas, o None."""

    @abstractmethod
    def save(self, range_key: str, metrics_hash: str, result: InsightsResult) -> None:
        """Guarda el resultado."""
