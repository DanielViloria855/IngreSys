"""Aplicación (analytics): DTOs serializables del tablero."""
from dataclasses import asdict, dataclass, field
from datetime import date, datetime

from apps.analytics.domain.assistant import ChatTurn
from apps.analytics.domain.insight import Insight


@dataclass(frozen=True)
class ChartPoint:
    label: str
    value: int | float


@dataclass(frozen=True)
class SupplierIssues:
    """Incidencias agregadas por proveedor (sin datos personales)."""

    supplier: str
    entries: int
    with_issue: int  # ingresos con alguna incidencia: novedad, sello roto o ISO inválido
    novelty: int
    seals_not_ok: int
    iso_invalid: int
    issue_rate_pct: float


@dataclass(frozen=True)
class DashboardMetricsDTO:
    """DTO (aplicación): métricas agregadas del rango. Sin datos personales (se puede enviar al LLM)."""

    range_key: str
    range_label: str
    days: int
    trucks: int
    boxes: int
    pallets: int
    witness_samples: int
    novelty_entries: int
    containers_total: int
    containers_iso_valid: int
    iso_valid_pct: float | None
    seals_not_ok: int
    pending_review: int
    by_hour: list[ChartPoint] = field(default_factory=list)
    by_day: list[ChartPoint] = field(default_factory=list)
    novelty_by_type: list[ChartPoint] = field(default_factory=list)
    top_suppliers: list[ChartPoint] = field(default_factory=list)
    status_breakdown: list[ChartPoint] = field(default_factory=list)
    supplier_issues: list[SupplierIssues] = field(default_factory=list)  # proveedores con más incidencias
    novelty_by_day: list[ChartPoint] = field(default_factory=list)  # ingresos con novedad por día
    by_weekday: list[ChartPoint] = field(default_factory=list)  # ingresos por día de la semana (total)
    weekday_average: list[ChartPoint] = field(default_factory=list)  # ingresos promedio por ocurrencia de cada día de la semana
    previous: dict | None = None  # valores absolutos del periodo anterior
    deltas: dict = field(default_factory=dict)  # variación % vs. periodo anterior

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class InsightsResult:
    insights: list[Insight]
    model_used: str
    generated_at: datetime
    from_cache: bool = False
    fallback_used: bool = False

    def to_dict(self) -> dict:
        return {
            "insights": [{"level": i.level.value, "title": i.title, "message": i.message} for i in self.insights],
            "model_used": self.model_used,
            "generated_at": self.generated_at.isoformat(),
            "from_cache": self.from_cache,
            "fallback_used": self.fallback_used,
        }


@dataclass(frozen=True)
class AskQuery:
    """Pregunta al asistente: texto + métricas del periodo + turnos previos de la conversación."""

    question: str
    metrics: DashboardMetricsDTO  # periodo seleccionado en el tablero
    history: tuple[ChatTurn, ...] = ()
    reference: DashboardMetricsDTO | None = None  # contexto histórico (últimos 30 días) para patrones y estimaciones
    today: date | None = None  # fecha actual, para saber qué día es «mañana»


@dataclass(frozen=True)
class AnswerResult:
    answer: str
    model_used: str
    generated_at: datetime
    fallback_used: bool = False

    def to_dict(self) -> dict:
        return {
            "answer": self.answer,
            "model_used": self.model_used,
            "generated_at": self.generated_at.isoformat(),
            "fallback_used": self.fallback_used,
        }
