"""Unitarias (aplicación + adaptador de reglas): tablero, insights, prompts y su validación."""
import json
from datetime import date, datetime, timezone

import pytest

from apps.analytics.application.dtos import ChartPoint, DashboardMetricsDTO, InsightsResult
from apps.analytics.application.ports import InsightGenerator
from apps.analytics.application.prompts import MAX_INSIGHTS, SYSTEM_PROMPT, build_user_prompt, parse_insights
from apps.analytics.application.use_cases import GenerateAIInsights, GetDashboardMetrics, _pct_change
from apps.analytics.domain.insight import Insight, InsightLevel, InsightUnavailable
from apps.analytics.domain.metrics import DateRange
from apps.analytics.infrastructure.in_memory import InMemoryInsightCache, InMemoryMetricsRepository
from apps.analytics.infrastructure.llm.rule_based_adapter import RuleBasedInsightAdapter

NOW = datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc)


def metrics(**over):
    base = dict(
        range_key="k", range_label="Hoy", days=1, trucks=10, boxes=100, pallets=20, witness_samples=5, novelty_entries=0,
        containers_total=0, containers_iso_valid=0, iso_valid_pct=None, seals_not_ok=0, pending_review=0,
        by_hour=[ChartPoint(f"{h:02d}h", 0) for h in range(24)],
    )
    base.update(over)
    return DashboardMetricsDTO(**base)


class Counting(InsightGenerator):
    def __init__(self, fail=False, name="primario"):
        self.calls, self.fail, self.model_name = 0, fail, name

    def generate(self, m):
        self.calls += 1
        if self.fail:
            raise InsightUnavailable("x")
        return [Insight(InsightLevel.INFO, "t", "m")]


# -- variaciones -----------------------------------------------------------------------------------
@pytest.mark.parametrize("current,previous,expected", [(10, 0, None), (0, 0, None), (5, 10, -50.0), (11, 3, 266.7), (3, 3, 0.0)])
def test_pct_change(current, previous, expected):
    assert _pct_change(current, previous) == expected


def test_dashboard_deltas_are_none_without_previous_data():
    repo = InMemoryMetricsRepository(metrics(trucks=4))
    today = DateRange(date(2026, 11, 5), date(2026, 11, 5))
    repo._by_key[today.previous().key] = metrics(trucks=0, boxes=0, pallets=0, witness_samples=0, range_label="Ayer")
    result = GetDashboardMetrics(repo).execute(today)
    assert result.deltas["trucks"] is None and result.previous["trucks"] == 0 and result.previous["range_label"] == "Ayer"
    assert set(result.deltas) == {"trucks", "boxes", "pallets", "witness_samples", "novelty_entries"}


# -- generación de insights ------------------------------------------------------------------------
def test_fallback_results_are_not_cached_so_primary_is_retried():
    primary, cache = Counting(fail=True), InMemoryInsightCache()
    use_case = GenerateAIInsights(primary, RuleBasedInsightAdapter(), cache)
    use_case.execute(metrics())
    use_case.execute(metrics())
    assert primary.calls == 2 and cache.store == {}


def test_cache_is_scoped_by_range_key():
    primary = Counting()
    use_case = GenerateAIInsights(primary, RuleBasedInsightAdapter(), InMemoryInsightCache())
    use_case.execute(metrics(range_key="a"))
    use_case.execute(metrics(range_key="b"))
    assert primary.calls == 2


def test_without_cache_always_calls_primary_and_uses_clock():
    primary = Counting()
    use_case = GenerateAIInsights(primary, RuleBasedInsightAdapter(), clock=lambda: NOW)
    first, second = use_case.execute(metrics()), use_case.execute(metrics())
    assert primary.calls == 2 and first.generated_at == NOW and not second.from_cache and first.model_used == "primario"


def test_metrics_hash_is_deterministic_and_sensitive():
    h = GenerateAIInsights.metrics_hash
    assert h(metrics()) == h(metrics()) and len(h(metrics())) == 64
    assert h(metrics()) != h(metrics(boxes=101))


def test_insights_result_serialization():
    result = InsightsResult([Insight(InsightLevel.ALERT, "T", "M")], "m", NOW, from_cache=True)
    assert result.to_dict() == {
        "insights": [{"level": "alert", "title": "T", "message": "M"}],
        "model_used": "m", "generated_at": NOW.isoformat(), "from_cache": True, "fallback_used": False,
    }


# -- prompts -------------------------------------------------------------------------------------
def test_user_prompt_is_json_without_range_key_and_keeps_accents():
    prompt = build_user_prompt(metrics(range_label="Últimos 7 días"))
    data = json.loads(prompt)
    assert "range_key" not in data and data["trucks"] == 10 and "Últimos" in prompt


def test_system_prompt_constrains_format_and_language():
    assert '"insights"' in SYSTEM_PROMPT and "español" in SYSTEM_PROMPT and "máximo 5" in SYSTEM_PROMPT


@pytest.mark.parametrize(
    "content",
    ["null", "[]", '"texto"', '{"insights": "no-lista"}', '{"insights": [{"level": "info", "title": "a"}]}',
     '{"insights": ["solo texto"]}', '{"insights": [42]}', ""],
)
def test_parse_insights_rejects_malformed(content):
    with pytest.raises(InsightUnavailable):
        parse_insights(content)


def test_parse_insights_normalizes_level_and_trims():
    [item] = parse_insights('{"insights":[{"level":"ALERT","title":"  A ","message":" B  "}]}')
    assert (item.level, item.title, item.message) == (InsightLevel.ALERT, "A", "B")
    assert MAX_INSIGHTS == 5


# -- adaptador por reglas --------------------------------------------------------------------------
def titles(m):
    return [i.title for i in RuleBasedInsightAdapter().generate(m)]


@pytest.mark.parametrize("novelties,title", [(1, None), (2, "Novedades en aumento"), (3, "Novedades por encima del límite")])
def test_novelty_thresholds(novelties, title):
    found = titles(metrics(novelty_entries=novelties))
    if title is None:
        assert not any("Novedades" in t for t in found)
    else:
        assert title in found


@pytest.mark.parametrize("pct,title", [(60.0, "Contenedores con ISO inválido"), (80.0, "Revisar códigos de contenedor"), (95.0, None)])
def test_iso_thresholds(pct, title):
    found = titles(metrics(iso_valid_pct=pct, containers_total=10))
    assert (title in found) if title else not any("ontenedor" in t for t in found)


def test_seals_pending_peak_and_volume_change():
    m = metrics(seals_not_ok=2, pending_review=6, by_hour=[ChartPoint(f"{h:02d}h", 5 if h == 8 else 0) for h in range(24)],
                deltas={"trucks": -30.0})
    result = RuleBasedInsightAdapter().generate(m)
    by_title = {i.title: i for i in result}
    assert by_title["Sellos no intactos"].level is InsightLevel.ALERT
    assert "Revisiones pendientes" in by_title and "08h" in by_title["Hora pico"].message
    assert "bajó 30 %" in by_title["Cambio de volumen"].message


def test_results_sorted_by_severity_and_capped_at_five():
    m = metrics(novelty_entries=5, novelty_by_type=[ChartPoint("Plagas", 3)], iso_valid_pct=50.0, containers_total=4,
                seals_not_ok=1, pending_review=9, by_hour=[ChartPoint("10h", 2)] * 24, deltas={"trucks": 80.0})
    result = RuleBasedInsightAdapter().generate(m)
    order = {InsightLevel.ALERT: 0, InsightLevel.WARNING: 1, InsightLevel.INFO: 2}
    assert len(result) == 5 and [order[i.level] for i in result] == sorted(order[i.level] for i in result)
    assert result[0].level is InsightLevel.ALERT


def test_rule_adapter_message_for_empty_period_uses_range_label():
    [only] = RuleBasedInsightAdapter().generate(metrics(trucks=0, range_label="Últimos 7 días"))
    assert "últimos 7 días" in only.message
