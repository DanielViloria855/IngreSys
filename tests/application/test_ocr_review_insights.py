from datetime import datetime, timezone

import pytest

from apps.analytics.application.dtos import ChartPoint, DashboardMetricsDTO
from apps.analytics.application.prompts import parse_insights
from apps.analytics.application.ports import InsightGenerator
from apps.analytics.application.use_cases import GenerateAIInsights, GetDashboardMetrics
from apps.analytics.domain.insight import Insight, InsightLevel, InsightUnavailable
from apps.analytics.domain.metrics import DateRange
from apps.analytics.infrastructure.in_memory import InMemoryInsightCache, InMemoryMetricsRepository
from apps.analytics.infrastructure.llm.rule_based_adapter import RuleBasedInsightAdapter
from apps.entries.application.dtos import GetEntryDetailQuery, ReviewEntryCommand
from apps.entries.application.use_cases import GetEntryDetail, ReadContainerWithAI, ReadPlateWithAI, ReviewEntry
from apps.entries.domain.entities import EntryStatus, TruckEntry
from apps.entries.domain.exceptions import EntryAlreadyReviewed, EntryNotFound, PermissionDeniedForAction
from apps.entries.infrastructure.in_memory import InMemoryTruckEntryRepository
from apps.entries.infrastructure.ocr.fake_ocr_adapter import FakeOcrAdapter
from shared.application.actor import Actor
from shared.domain.roles import Role


# -- OCR con adaptador falso ----------------------------------------------------------------
def test_read_container_with_fake_ocr_valid():
    result = ReadContainerWithAI(FakeOcrAdapter(["CSQU 305438 3"])).execute(b"img")
    assert result.is_valid and result.candidate == "CSQU3054383" and result.expected_check_digit == 3


def test_read_container_with_fake_ocr_bad_digit():
    result = ReadContainerWithAI(FakeOcrAdapter(["CSQU3054384"])).execute(b"img")
    assert not result.is_valid and result.candidate == "CSQU3054384" and result.expected_check_digit == 3


def test_read_container_nothing_found():
    result = ReadContainerWithAI(FakeOcrAdapter(["HOLA"])).execute(b"img")
    assert result.candidate == "" and result.expected_check_digit is None


def test_read_plate_with_fake_ocr():
    result = ReadPlateWithAI(FakeOcrAdapter(["COLOMBIA", "SKX 482"])).execute(b"img")
    assert result.is_valid and result.candidate == "SKX482"


# -- Revisión y aislamiento ----------------------------------------------------------------------
def make_entry(repo, owner=1):
    return repo.save(TruckEntry.register(questionnaire_id=1, created_by_id=owner, plate="ABC123", container_code="", container_iso_valid=True), [])


def test_review_flow_and_permissions():
    repo = InMemoryTruckEntryRepository()
    entry_id = make_entry(repo)
    clock = lambda: datetime(2026, 1, 1, tzinfo=timezone.utc)  # noqa: E731
    supervisor = Actor(9, "Sup", Role.SUPERVISOR)
    operator = Actor(1, "Op", Role.OPERATOR)
    with pytest.raises(PermissionDeniedForAction):
        ReviewEntry(repo, clock).execute(ReviewEntryCommand(entry_id, operator))
    ReviewEntry(repo, clock).execute(ReviewEntryCommand(entry_id, supervisor, " ok "))
    saved = repo.get(entry_id)
    assert saved.status is EntryStatus.REVIEWED and saved.review_comment == "ok" and saved.reviewed_by_id == 9
    with pytest.raises(EntryAlreadyReviewed):
        ReviewEntry(repo, clock).execute(ReviewEntryCommand(entry_id, supervisor))
    with pytest.raises(EntryNotFound):
        ReviewEntry(repo, clock).execute(ReviewEntryCommand(999, supervisor))


def test_operator_cannot_open_other_users_entry():
    repo = InMemoryTruckEntryRepository()
    entry_id = make_entry(repo, owner=1)
    use_case = GetEntryDetail(repo)
    with pytest.raises(EntryNotFound):
        use_case.execute(GetEntryDetailQuery(entry_id, Actor(2, "Otro", Role.OPERATOR)))
    assert use_case.execute(GetEntryDetailQuery(entry_id, Actor(1, "Dueño", Role.OPERATOR))).id == entry_id
    assert use_case.execute(GetEntryDetailQuery(entry_id, Actor(5, "Sup", Role.SUPERVISOR))).timeline[0].key == "registrado"


# -- Tablero e insights ----------------------------------------------------------------------------
def metrics(**over):
    base = dict(
        range_key="k", range_label="Hoy", days=1, trucks=10, boxes=100, pallets=20, witness_samples=5, novelty_entries=0,
        containers_total=4, containers_iso_valid=4, iso_valid_pct=100.0, seals_not_ok=0, pending_review=2,
        by_hour=[ChartPoint(f"{h:02d}h", 3 if h == 10 else 0) for h in range(24)],
    )
    base.update(over)
    return DashboardMetricsDTO(**base)


class Boom(InsightGenerator):
    model_name = "boom"

    def generate(self, m):
        raise InsightUnavailable("sin internet")


class Fixed(InsightGenerator):
    model_name = "fijo"

    def __init__(self):
        self.calls = 0

    def generate(self, m):
        self.calls += 1
        return [Insight(InsightLevel.INFO, "t", "m")]


def test_insights_fall_back_to_rules_when_primary_fails():
    result = GenerateAIInsights(Boom(), RuleBasedInsightAdapter()).execute(metrics(novelty_entries=5))
    assert result.fallback_used and result.model_used == "Reglas automáticas"
    assert result.insights[0].level is InsightLevel.ALERT  # 50 % de novedades


def test_insights_cache_avoids_second_call_and_invalidates_on_change():
    primary, cache = Fixed(), InMemoryInsightCache()
    use_case = GenerateAIInsights(primary, RuleBasedInsightAdapter(), cache)
    first = use_case.execute(metrics())
    second = use_case.execute(metrics())
    assert primary.calls == 1 and not first.from_cache and second.from_cache
    use_case.execute(metrics(trucks=11))
    assert primary.calls == 2


def test_parse_insights_validation():
    good = '{"insights":[{"level":"warning","title":"A","message":"B"}]}'
    assert parse_insights(good)[0].level is InsightLevel.WARNING
    many = '{"insights":[' + ",".join(['{"level":"info","title":"t","message":"m"}'] * 8) + "]}"
    assert len(parse_insights(many)) == 5
    for bad in ["no es json", '{"x":1}', '{"insights":[{"level":"urgent","title":"a","message":"b"}]}', '{"insights":[]}']:
        with pytest.raises(InsightUnavailable):
            parse_insights(bad)


def test_rule_based_zero_trucks_and_stable():
    assert RuleBasedInsightAdapter().generate(metrics(trucks=0))[0].title == "Sin ingresos"
    stable = RuleBasedInsightAdapter().generate(metrics(by_hour=[ChartPoint("06h", 0)] * 24))
    assert stable[0].title == "Operación estable"


def test_dashboard_metrics_adds_previous_period_deltas():
    today = DateRange.from_preset("today", datetime(2026, 11, 2).date())
    repo = InMemoryMetricsRepository(metrics(trucks=10), {today.previous().key: metrics(trucks=8, range_label="Ayer")})
    result = GetDashboardMetrics(repo).execute(today)
    assert result.deltas["trucks"] == 25.0 and result.previous["range_label"] == "Ayer"


def test_date_range_previous_and_validation():
    r = DateRange.from_preset("7d", datetime(2026, 11, 8).date())
    assert r.days == 7 and r.previous().end.isoformat() == "2026-11-01" and r.previous().days == 7
    with pytest.raises(Exception):
        DateRange.from_preset("custom", datetime(2026, 11, 8).date(), "2026-11-09", "2026-11-01")


def test_rule_based_flags_supplier_with_many_issues():
    from apps.analytics.application.dtos import SupplierIssues

    issues = [SupplierIssues("Frontera Cargo", 20, 12, 7, 5, 3, 60.0), SupplierIssues("Otro", 20, 3, 2, 1, 0, 15.0)]
    found = RuleBasedInsightAdapter().generate(metrics(supplier_issues=issues))
    assert any("Frontera Cargo" in i.title for i in found)
    calm = [SupplierIssues("A", 20, 5, 3, 1, 1, 25.0), SupplierIssues("B", 20, 4, 3, 1, 0, 20.0)]
    assert not any("Proveedor" in i.title for i in RuleBasedInsightAdapter().generate(metrics(supplier_issues=calm)))
