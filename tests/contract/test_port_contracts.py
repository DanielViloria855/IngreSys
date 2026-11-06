"""Contrato de los puertos: el adaptador en memoria (usado en las unitarias) y el de Django se comportan igual.

Si una prueba unitaria pasa con el falso pero el real hace otra cosa, estas pruebas lo detectan.
"""
from datetime import datetime, timezone

import pytest

from apps.analytics.application.dtos import InsightsResult
from apps.analytics.application.ports import InsightCache
from apps.analytics.domain.insight import Insight, InsightLevel
from apps.analytics.infrastructure.in_memory import InMemoryInsightCache
from apps.analytics.infrastructure.repositories import DjangoInsightCache
from apps.entries.application.dtos import AnswerValue, EntryFilters
from apps.entries.application.ports import FileStorage, OcrService, TruckEntryRepository
from apps.entries.domain.entities import EntryStatus, TruckEntry
from apps.entries.infrastructure.in_memory import InMemoryFileStorage, InMemoryTruckEntryRepository
from apps.entries.infrastructure.ocr.fake_ocr_adapter import FakeOcrAdapter
from apps.entries.infrastructure.repositories import DjangoTruckEntryRepository
from apps.entries.infrastructure.storage import DjangoFileStorage
from apps.questionnaire.application.ports import QuestionnaireRepository
from apps.questionnaire.infrastructure.in_memory import InMemoryQuestionnaireRepository
from apps.questionnaire.infrastructure.repositories import DjangoQuestionnaireRepository
from tests.application.conftest import build_questionnaire

pytestmark = pytest.mark.django_db


# -- TruckEntryRepository ------------------------------------------------------------------------
@pytest.fixture(params=["memory", "django"])
def entry_repo(request):
    if request.param == "memory":
        return InMemoryTruckEntryRepository(), {"questionnaire_id": 1, "users": (1, 2)}
    operator, operator2 = request.getfixturevalue("operator"), request.getfixturevalue("operator2")
    questionnaire_id = DjangoQuestionnaireRepository().get_active().id
    return DjangoTruckEntryRepository(), {"questionnaire_id": questionnaire_id, "users": (operator.id, operator2.id)}


def new_entry(ctx, owner=0, iso_valid=True):
    return TruckEntry.register(questionnaire_id=ctx["questionnaire_id"], created_by_id=ctx["users"][owner], plate="ABC123",
                               container_code="" if iso_valid else "CSQU3054384", container_iso_valid=iso_valid)


def test_repo_is_a_port(entry_repo):
    assert isinstance(entry_repo[0], TruckEntryRepository)


def test_save_then_get_roundtrip(entry_repo):
    repo, ctx = entry_repo
    entry_id = repo.save(new_entry(ctx, iso_valid=False), [])
    got = repo.get(entry_id)
    assert isinstance(entry_id, int) and got.id == entry_id
    assert (got.plate, got.container_code, got.container_iso_valid, got.status) == ("ABC123", "CSQU3054384", False, EntryStatus.WITH_OBSERVATION)
    assert got.created_by_id == ctx["users"][0]


def test_ids_are_unique(entry_repo):
    repo, ctx = entry_repo
    assert repo.save(new_entry(ctx), []) != repo.save(new_entry(ctx), [])


def test_missing_returns_none(entry_repo):
    repo, _ = entry_repo
    assert repo.get(424242) is None and repo.get_detail(424242) is None


def test_review_is_persisted(entry_repo):
    repo, ctx = entry_repo
    entity = repo.get(repo.save(new_entry(ctx), []))
    entity.mark_reviewed(ctx["users"][1], "ok", datetime(2026, 1, 1, tzinfo=timezone.utc))
    repo.save_review(entity)
    again = repo.get(entity.id)
    assert again.status is EntryStatus.REVIEWED and again.reviewed_by_id == ctx["users"][1] and again.review_comment == "ok"


def test_detail_contract(entry_repo):
    repo, ctx = entry_repo
    with_container = repo.get_detail(repo.save(new_entry(ctx, iso_valid=False), []))
    without = repo.get_detail(repo.save(new_entry(ctx), []))
    assert with_container.container_iso_valid is False and without.container_iso_valid is None
    assert (without.status, without.status_label, without.status_variant) == ("registrado", "Registrado", "info")
    assert without.created_by_id == ctx["users"][0]


def test_list_filters_by_user_and_paginates(entry_repo):
    repo, ctx = entry_repo
    for owner in (0, 1, 1):
        repo.save(new_entry(ctx, owner), [])
    assert repo.list(EntryFilters(user_id=ctx["users"][1]), 1, 20).total == 2
    page = repo.list(EntryFilters(), 2, 2)
    assert (page.number, page.num_pages, page.total, len(page.items)) == (2, 2, 3, 1)


def test_answers_are_accepted(entry_repo):
    repo, ctx = entry_repo
    if isinstance(repo, DjangoTruckEntryRepository):
        question_id = DjangoQuestionnaireRepository().get_active().question_by_tag("driver_name").id
    else:
        question_id = 1
    entry_id = repo.save(new_entry(ctx), [AnswerValue(question_id, "driver_name", value_text="Luis")])
    assert repo.get(entry_id) is not None


# -- QuestionnaireRepository ------------------------------------------------------------------------
@pytest.fixture(params=["memory", "django"])
def questionnaire_repo(request):
    if request.param == "memory":
        return InMemoryQuestionnaireRepository(build_questionnaire())
    request.getfixturevalue("seeded")
    return DjangoQuestionnaireRepository()


def test_questionnaire_contract(questionnaire_repo):
    assert isinstance(questionnaire_repo, QuestionnaireRepository)
    questionnaire = questionnaire_repo.get_active()
    orders = [q.order for q in questionnaire.questions]
    assert orders == sorted(orders) and questionnaire.question_by_tag("plate") is not None
    ids = {q.id for q in questionnaire.questions}
    assert all(q.depends_on_id in ids for q in questionnaire.questions if q.depends_on_id)


# -- InsightCache --------------------------------------------------------------------------------
@pytest.fixture(params=[InMemoryInsightCache, DjangoInsightCache])
def insight_cache(request):
    return request.param()


def test_insight_cache_contract(insight_cache):
    assert isinstance(insight_cache, InsightCache)
    assert insight_cache.get("r", "h") is None
    insight_cache.save("r", "h", InsightsResult([Insight(InsightLevel.ALERT, "t", "m")], "modelo", datetime(2026, 1, 1, tzinfo=timezone.utc)))
    got = insight_cache.get("r", "h")
    assert got.model_used == "modelo" and [(i.level, i.title, i.message) for i in got.insights] == [(InsightLevel.ALERT, "t", "m")]
    assert insight_cache.get("r", "otro") is None and insight_cache.get("otro", "h") is None


# -- FileStorage / OcrService ----------------------------------------------------------------------
@pytest.mark.parametrize("storage_cls", [InMemoryFileStorage, DjangoFileStorage])
def test_file_storage_contract(storage_cls, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    storage = storage_cls()
    assert isinstance(storage, FileStorage)
    first, second = storage.save(3, "a.jpg", b"1"), storage.save(3, "a.jpg", b"2")
    assert isinstance(first, str) and first != second and first.startswith("evidences/")


def test_fake_ocr_is_an_ocr_service():
    assert isinstance(FakeOcrAdapter(), OcrService)
    assert all(isinstance(line, str) for line in FakeOcrAdapter().read_text(b"x"))
