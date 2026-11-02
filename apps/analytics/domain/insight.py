"""Dominio (analytics): insights generados sobre las métricas."""
from dataclasses import dataclass
from enum import Enum

from shared.domain.base import DomainError


class InsightLevel(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ALERT = "alert"


@dataclass(frozen=True)
class Insight:
    """Value object (dominio): un mensaje de análisis."""

    level: InsightLevel
    title: str
    message: str


class InsightUnavailable(DomainError):
    """El generador de insights no pudo responder (red, cuota, JSON inválido…)."""
