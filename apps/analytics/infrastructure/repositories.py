"""Infraestructura (analytics): adaptadores secundarios con el ORM (métricas y caché)."""
from datetime import datetime, time, timedelta

from django.db.models import Count, Sum
from django.db.models.functions import ExtractHour, TruncDate
from django.utils import timezone

from apps.analytics.application.dtos import ChartPoint, DashboardMetricsDTO, InsightsResult, SupplierIssues
from apps.analytics.application.ports import InsightCache, MetricsRepository
from apps.analytics.domain.insight import Insight, InsightLevel
from apps.analytics.domain.metrics import DateRange
from apps.analytics.infrastructure.models import AIInsightCache
from apps.entries.infrastructure.models import Answer, TruckEntry
from apps.questionnaire.infrastructure.models import Choice

STATUS_LABELS = {"registrado": "Registrado", "con_observacion": "Con observación", "revisado": "Revisado"}


def _bounds(date_range: DateRange) -> tuple[datetime, datetime]:
    tz = timezone.get_current_timezone()
    start = datetime.combine(date_range.start, time.min, tzinfo=tz)
    end = datetime.combine(date_range.end + timedelta(days=1), time.min, tzinfo=tz)
    return start, end


def _label(date_range: DateRange) -> str:
    if date_range.start == date_range.end:
        return f"{date_range.start:%d/%m/%Y}"
    return f"{date_range.start:%d/%m/%Y} – {date_range.end:%d/%m/%Y}"


class DjangoMetricsRepository(MetricsRepository):
    """Adaptador secundario (infraestructura): agregaciones ORM (annotate, Count, Sum…) sobre `Answer` por `semantic_tag`."""

    def get_metrics(self, date_range: DateRange) -> DashboardMetricsDTO:
        start, end = _bounds(date_range)
        entries = TruckEntry.objects.filter(created_at__gte=start, created_at__lt=end)
        answers = Answer.objects.filter(entry__in=entries)

        def total(tag: str) -> int:
            value = answers.filter(question__semantic_tag=tag).aggregate(total=Sum("value_number"))["total"]
            return int(value or 0)

        with_container = entries.exclude(container_code="")
        containers_total = with_container.count()
        containers_valid = with_container.filter(container_iso_valid=True).count()
        novelty_entries = (
            answers.filter(question__semantic_tag="has_novelty", value_bool=True).values("entry").distinct().count()
        )
        seals_not_ok = answers.filter(question__semantic_tag="seal_ok", value_bool=False).values("entry").distinct().count()

        return DashboardMetricsDTO(
            range_key=date_range.key,
            range_label=_label(date_range),
            days=date_range.days,
            trucks=entries.count(),
            boxes=total("boxes_count"),
            pallets=total("pallets_count"),
            witness_samples=total("witness_samples_count"),
            novelty_entries=novelty_entries,
            containers_total=containers_total,
            containers_iso_valid=containers_valid,
            iso_valid_pct=round(containers_valid / containers_total * 100, 1) if containers_total else None,
            seals_not_ok=seals_not_ok,
            pending_review=entries.exclude(status="revisado").count(),
            by_hour=self._by_hour(entries),
            by_day=self._by_day(entries, date_range),
            novelty_by_type=self._novelty_by_type(entries),
            top_suppliers=self._top_suppliers(answers),
            status_breakdown=self._status_breakdown(entries),
            supplier_issues=self._supplier_issues(entries, answers),
            novelty_by_day=self._novelty_by_day(answers, date_range),
            by_weekday=(weekdays := self._by_weekday(entries)),
            weekday_average=self._weekday_average(weekdays, date_range),
        )

    @staticmethod
    def _by_hour(entries) -> list[ChartPoint]:
        counts = {r["h"]: r["n"] for r in entries.annotate(h=ExtractHour("created_at")).values("h").annotate(n=Count("id"))}
        return [ChartPoint(f"{hour:02d}h", counts.get(hour, 0)) for hour in range(24)]

    @staticmethod
    def _by_day(entries, date_range: DateRange) -> list[ChartPoint]:
        counts = {r["d"]: r["n"] for r in entries.annotate(d=TruncDate("created_at")).values("d").annotate(n=Count("id"))}
        return [ChartPoint(f"{day:%d/%m}", counts.get(day, 0)) for day in date_range.each_day()]

    @staticmethod
    def _novelty_by_type(entries) -> list[ChartPoint]:
        rows = (
            Choice.objects.filter(question__semantic_tag="novelty_type", answers__entry__in=entries)
            .values("label")
            .annotate(n=Count("answers"))
            .order_by("-n", "label")
        )
        return [ChartPoint(r["label"], r["n"]) for r in rows]

    @staticmethod
    def _top_suppliers(answers) -> list[ChartPoint]:
        rows = (
            answers.filter(question__semantic_tag="supplier")
            .values("value_text")
            .annotate(n=Count("id"))
            .order_by("-n", "value_text")[:5]
        )
        return [ChartPoint(r["value_text"], r["n"]) for r in rows]

    @staticmethod
    def _novelty_by_day(answers, date_range: DateRange) -> list[ChartPoint]:
        rows = (
            answers.filter(question__semantic_tag="has_novelty", value_bool=True)
            .annotate(d=TruncDate("entry__created_at"))
            .values("d")
            .annotate(n=Count("entry", distinct=True))
        )
        counts = {r["d"]: r["n"] for r in rows}
        return [ChartPoint(f"{day:%d/%m}", counts.get(day, 0)) for day in date_range.each_day()]

    @staticmethod
    def _by_weekday(entries) -> list[ChartPoint]:
        names = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
        totals = [0] * 7
        for row in entries.annotate(d=TruncDate("created_at")).values("d").annotate(n=Count("id")):
            totals[row["d"].weekday()] += row["n"]
        return [ChartPoint(name, total) for name, total in zip(names, totals)]

    @staticmethod
    def _weekday_average(totals: list[ChartPoint], date_range: DateRange) -> list[ChartPoint]:
        """Promedio de ingresos por cada ocurrencia del día de la semana dentro del rango."""
        occurrences = [0] * 7
        for day in date_range.each_day():
            occurrences[day.weekday()] += 1
        return [
            ChartPoint(point.label, round(point.value / count, 1) if count else 0)
            for point, count in zip(totals, occurrences)
        ]

    @staticmethod
    def _supplier_issues(entries, answers, min_entries: int = 5, top: int = 5) -> list[SupplierIssues]:
        """Proveedores con mayor proporción de incidencias (novedad, sello no intacto o ISO inválido)."""
        supplier_of = dict(answers.filter(question__semantic_tag="supplier").values_list("entry_id", "value_text"))
        novelty = set(answers.filter(question__semantic_tag="has_novelty", value_bool=True).values_list("entry_id", flat=True))
        seals = set(answers.filter(question__semantic_tag="seal_ok", value_bool=False).values_list("entry_id", flat=True))
        iso = set(entries.exclude(container_code="").filter(container_iso_valid=False).values_list("id", flat=True))
        stats: dict[str, dict[str, int]] = {}
        for entry_id, name in supplier_of.items():
            row = stats.setdefault(name, {"entries": 0, "with_issue": 0, "novelty": 0, "seals": 0, "iso": 0})
            row["entries"] += 1
            row["novelty"] += entry_id in novelty
            row["seals"] += entry_id in seals
            row["iso"] += entry_id in iso
            row["with_issue"] += entry_id in novelty or entry_id in seals or entry_id in iso
        ranked = [
            SupplierIssues(name, r["entries"], r["with_issue"], r["novelty"], r["seals"], r["iso"], round(r["with_issue"] / r["entries"] * 100, 1))
            for name, r in stats.items() if r["entries"] >= min_entries
        ]
        ranked.sort(key=lambda s: (-s.issue_rate_pct, -s.entries))
        return ranked[:top]

    @staticmethod
    def _status_breakdown(entries) -> list[ChartPoint]:
        counts = {r["status"]: r["n"] for r in entries.values("status").annotate(n=Count("id"))}
        return [ChartPoint(label, counts.get(key, 0)) for key, label in STATUS_LABELS.items()]


class DjangoInsightCache(InsightCache):
    """Adaptador secundario (infraestructura): caché de insights en la tabla AIInsightCache."""

    def get(self, range_key: str, metrics_hash: str) -> InsightsResult | None:
        row = AIInsightCache.objects.filter(range_key=range_key, metrics_hash=metrics_hash).first()
        if row is None:
            return None
        insights = [Insight(InsightLevel(i["level"]), i["title"], i["message"]) for i in row.payload]
        return InsightsResult(insights, row.model_used, row.created_at, from_cache=True)

    def save(self, range_key: str, metrics_hash: str, result: InsightsResult) -> None:
        AIInsightCache.objects.update_or_create(
            range_key=range_key,
            metrics_hash=metrics_hash,
            defaults={
                "payload": [{"level": i.level.value, "title": i.title, "message": i.message} for i in result.insights],
                "model_used": result.model_used,
            },
        )
