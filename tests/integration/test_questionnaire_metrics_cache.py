"""Integración: repositorio del cuestionario, métricas agregadas por ORM y caché de insights."""
from datetime import datetime, timedelta, timezone as dt_timezone

import pytest
from django.db import IntegrityError
from django.utils import timezone

from apps.analytics.application.dtos import InsightsResult
from apps.analytics.domain.insight import Insight, InsightLevel
from apps.analytics.domain.metrics import DateRange
from apps.analytics.infrastructure.models import AIInsightCache
from apps.analytics.infrastructure.repositories import DjangoInsightCache, DjangoMetricsRepository
from apps.entries.infrastructure.models import TruckEntry as TruckEntryModel
from apps.questionnaire.domain.entities import QuestionType
from apps.questionnaire.infrastructure.models import Question, Questionnaire
from apps.questionnaire.infrastructure.repositories import DjangoQuestionnaireRepository
from tests.factories import BAD_DIGIT_CONTAINER, VALID_CONTAINER, register

pytestmark = pytest.mark.django_db


# -- cuestionario ----------------------------------------------------------------------------------
def test_active_questionnaire_maps_seed(seeded):
    questionnaire = DjangoQuestionnaireRepository().get_active()
    tags = [q.semantic_tag for q in questionnaire.questions]
    assert len(tags) == 19 and tags[0] == "plate" and tags[-1] == "observations"
    by_tag = {q.semantic_tag: q for q in questionnaire.questions}
    assert by_tag["plate"].type is QuestionType.PLATE_OCR and by_tag["plate"].is_required
    assert by_tag["container_code"].depends_on_id == by_tag["has_container"].id and by_tag["container_code"].depends_on_value == "true"
    assert [c.value for c in by_tag["novelty_type"].choices][:2] == ["pests", "looting"]
    assert [q.order for q in questionnaire.questions] == sorted(q.order for q in questionnaire.questions)


def test_inactive_questions_are_excluded_and_reordering_is_respected(seeded):
    Question.objects.filter(semantic_tag="observations").update(is_active=False)
    Question.objects.filter(semantic_tag="driver_id").update(order=0)
    questions = DjangoQuestionnaireRepository().get_active().questions
    assert "observations" not in {q.semantic_tag for q in questions} and questions[0].semantic_tag == "driver_id"


def test_newest_active_questionnaire_wins_and_none_when_inactive(seeded):
    newer = Questionnaire.objects.create(name="v2", is_active=True)
    assert DjangoQuestionnaireRepository().get_active().id == newer.id
    Questionnaire.objects.update(is_active=False)
    assert DjangoQuestionnaireRepository().get_active() is None


# -- métricas --------------------------------------------------------------------------------------
def at(entry_id, when):
    TruckEntryModel.objects.filter(pk=entry_id).update(created_at=when)


def test_metrics_respect_local_day_bounds(operator):
    tz = timezone.get_current_timezone()
    today = timezone.localdate()
    inside = register(operator)
    yesterday_late = register(operator)
    at(inside, datetime.combine(today, datetime.min.time(), tzinfo=tz))  # 00:00 local de hoy: entra
    at(yesterday_late, datetime.combine(today, datetime.min.time(), tzinfo=tz) - timedelta(seconds=1))  # 23:59:59 de ayer
    repo = DjangoMetricsRepository()
    assert repo.get_metrics(DateRange(today, today)).trucks == 1
    assert repo.get_metrics(DateRange(today, today).previous()).trucks == 1


def test_metrics_shape_for_multi_day_range(operator):
    today = timezone.localdate()
    register(operator, has_container="true", container_code=VALID_CONTAINER, seal_number="1", seal_ok="true")
    register(operator, has_container="true", container_code=BAD_DIGIT_CONTAINER, seal_number="1", seal_ok="true", confirm=True)
    m = DjangoMetricsRepository().get_metrics(DateRange(today - timedelta(days=6), today))
    assert m.days == 7 and len(m.by_day) == 7 and len(m.by_hour) == 24
    assert m.by_day[-1].value == 2 and m.by_day[-1].label == f"{today:%d/%m}"
    assert (m.containers_total, m.containers_iso_valid, m.iso_valid_pct) == (2, 1, 50.0)
    assert {p.label: p.value for p in m.status_breakdown} == {"Registrado": 1, "Con observación": 1, "Revisado": 0}
    assert " – " in m.range_label


def test_empty_period(seeded):
    today = timezone.localdate()
    m = DjangoMetricsRepository().get_metrics(DateRange(today, today))
    assert (m.trucks, m.boxes, m.iso_valid_pct, m.novelty_by_type, m.top_suppliers) == (0, 0, None, [], [])
    assert m.range_label == f"{today:%d/%m/%Y}"


def test_top_suppliers_limited_to_five_sorted(operator):
    suppliers = ["transportes_andina", "logística_del_caribe", "carga_express", "frontera_cargo", "transmar_sa", "otro"]
    for index, supplier in enumerate(suppliers):
        for _ in range(index + 1):
            register(operator, supplier=supplier)
    today = timezone.localdate()
    top = DjangoMetricsRepository().get_metrics(DateRange(today, today)).top_suppliers
    assert [p.label for p in top] == ["Otro", "TransMar S.A.", "Frontera Cargo", "Carga Express", "Logística del Caribe"]


def test_reviewed_entries_are_not_pending(operator):
    entry_id = register(operator)
    TruckEntryModel.objects.filter(pk=entry_id).update(status="revisado")
    register(operator)
    today = timezone.localdate()
    assert DjangoMetricsRepository().get_metrics(DateRange(today, today)).pending_review == 1


# -- caché de insights -----------------------------------------------------------------------------
def result(title="T"):
    return InsightsResult([Insight(InsightLevel.WARNING, title, "M")], "Groq · x", datetime(2026, 1, 1, tzinfo=dt_timezone.utc))


def test_insight_cache_roundtrip_and_overwrite(db):
    cache = DjangoInsightCache()
    assert cache.get("r", "h") is None
    cache.save("r", "h", result("uno"))
    cache.save("r", "h", result("dos"))
    cached = cache.get("r", "h")
    assert cached.from_cache and cached.model_used == "Groq · x" and cached.insights[0].title == "dos"
    assert cached.insights[0].level is InsightLevel.WARNING
    assert AIInsightCache.objects.count() == 1 and cache.get("r", "otro-hash") is None


def test_insight_cache_unique_constraint(db):
    AIInsightCache.objects.create(range_key="r", metrics_hash="h", model_used="m")
    with pytest.raises(IntegrityError):
        AIInsightCache.objects.create(range_key="r", metrics_hash="h", model_used="m")
