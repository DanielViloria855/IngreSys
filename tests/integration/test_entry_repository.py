"""Integración: DjangoTruckEntryRepository contra la base de datos (guardar, mapear, detallar, filtrar, paginar)."""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.entries.application.dtos import EntryFilters
from apps.entries.domain.entities import EntryStatus
from apps.entries.infrastructure.models import Answer, Evidence
from apps.entries.infrastructure.models import TruckEntry as TruckEntryModel
from apps.entries.infrastructure.repositories import DjangoTruckEntryRepository
from tests.factories import BAD_DIGIT_CONTAINER, VALID_CONTAINER, jpeg_bytes, register

pytestmark = pytest.mark.django_db
repo = DjangoTruckEntryRepository()


def test_save_persists_entry_answers_and_choices(operator):
    entry_id = register(operator, boxes_count="12,50", has_novelty="true", novelty_type=["pests", "humidity"], novelty_description="x")
    model = TruckEntryModel.objects.get(pk=entry_id)
    assert (model.plate, model.status, model.created_by_id) == ("SKX482", "registrado", operator.id)
    novelty = Answer.objects.get(entry=model, question__semantic_tag="novelty_type")
    assert sorted(novelty.choices.values_list("value", flat=True)) == ["humidity", "pests"]
    assert novelty.meta == {"values": ["pests", "humidity"]}
    assert Answer.objects.get(entry=model, question__semantic_tag="boxes_count").value_number == Decimal("12.50")


def test_hidden_answers_are_not_persisted(operator):
    entry_id = register(operator, seal_number="OCULTO")  # has_container=false
    assert not Answer.objects.filter(entry_id=entry_id, question__semantic_tag="seal_number").exists()


@pytest.mark.xfail(strict=True, reason="BUG: un número que no cabe en DecimalField(14, 2) pasa la validación y revienta al guardar")
def test_huge_number_is_rejected_before_saving(operator):
    from apps.entries.domain.exceptions import EntryValidationError

    with pytest.raises(EntryValidationError):
        register(operator, boxes_count="1e20")


def test_get_maps_model_to_entity(operator):
    entity = repo.get(register(operator, has_container="true", container_code=BAD_DIGIT_CONTAINER, seal_number="1",
                               seal_ok="true", confirm=True))
    assert entity.status is EntryStatus.WITH_OBSERVATION and not entity.container_iso_valid
    assert entity.created_at is not None and entity.questionnaire_id
    assert repo.get(999_999) is None and repo.get_detail(999_999) is None


def test_detail_hides_header_answers_and_formats_numbers(operator):
    entry_id = register(operator, boxes_count="100", pallets_count="2,5", photos={"plate": jpeg_bytes()})
    detail = repo.get_detail(entry_id)
    tags = {a.semantic_tag: a.display_value for a in detail.answers}
    assert "plate" not in tags and "container_code" not in tags
    assert tags["boxes_count"] == "100" and tags["pallets_count"] == "2.5" and tags["supplier"] == "Otro"
    assert tags["has_container"] == "No"
    assert [(e.kind, e.kind_label) for e in detail.evidences] == [("plate", "Placa")]
    assert detail.evidences[0].url.startswith("/media/evidences/")
    assert detail.created_by_name == "Olga Pérez" and detail.container_iso_valid is None


def test_detail_iso_digits(operator):
    entry_id = register(operator, has_container="true", container_code=BAD_DIGIT_CONTAINER, seal_number="1", seal_ok="true", confirm=True)
    detail = repo.get_detail(entry_id)
    assert (detail.iso_read_digit, detail.iso_expected_digit, detail.container_iso_valid) == (4, 3, False)
    assert (detail.status_label, detail.status_variant) == ("Con observación", "warning")


def test_evidence_without_question_still_lists(operator):
    entry_id = register(operator)
    repo.add_evidence(entry_id, None, "otra", "evidences/x.jpg")
    [evidence] = repo.get_detail(entry_id).evidences
    assert evidence.kind_label == "Foto" and evidence.question_text == ""
    assert Evidence.objects.filter(entry_id=entry_id).count() == 1


def test_save_review_persists(operator, supervisor):
    entry_id = register(operator)
    entity = repo.get(entry_id)
    entity.mark_reviewed(supervisor.id, "ok", timezone.now())
    repo.save_review(entity)
    detail = repo.get_detail(entry_id)
    assert detail.status == "revisado" and detail.reviewed_by_name == "Sara Gil" and detail.review_comment == "ok"


# -- listado con filtros -----------------------------------------------------------------------------
@pytest.fixture
def three_entries(operator, operator2):
    a = register(operator, plate="AAA111", has_novelty="true", novelty_type=["pests"], novelty_description="x", supplier="carga_express")
    b = register(operator2, plate="BBB222", has_container="true", container_code=VALID_CONTAINER, seal_number="1", seal_ok="true")
    c = register(operator2, plate="R12345", has_container="true", container_code=BAD_DIGIT_CONTAINER, seal_number="1", seal_ok="false", confirm=True)
    TruckEntryModel.objects.filter(pk=a).update(created_at=timezone.now() - timedelta(days=3))
    return a, b, c


def ids(filters: EntryFilters, page=1, size=20):
    return [e.id for e in repo.list(filters, page, size).items]


@pytest.mark.parametrize(
    "filters,expected_idx",
    [
        (EntryFilters(), [2, 1, 0]),
        (EntryFilters(plate="aaa-1"), [0]),
        (EntryFilters(plate="r 123"), [2]),
        (EntryFilters(container="csqu 305438"), [2, 1]),
        (EntryFilters(status="con_observacion"), [2]),
        (EntryFilters(novelty="yes"), [0]),
        (EntryFilters(novelty="no"), [2, 1]),
        (EntryFilters(status="inexistente"), []),
    ],
)
def test_list_filters(three_entries, filters, expected_idx):
    assert ids(filters) == [three_entries[i] for i in expected_idx]


def test_list_filters_by_user_and_dates(three_entries, operator2):
    a, b, c = three_entries
    today = timezone.localdate()
    assert ids(EntryFilters(user_id=operator2.id)) == [c, b]
    assert ids(EntryFilters(date_to=today - timedelta(days=1))) == [a]
    assert ids(EntryFilters(date_from=today)) == [c, b]


def test_list_summary_fields(three_entries):
    rows = {e.id: e for e in repo.list(EntryFilters(), 1, 20).items}
    a, b, c = three_entries
    assert rows[a].supplier == "Carga Express" and rows[a].has_novelty is True and rows[a].container_iso_valid is None
    assert rows[b].container_iso_valid is True and rows[c].container_iso_valid is False
    assert rows[c].status_label == "Con observación"


def test_pagination_with_ellipsis(operator):
    for _ in range(9):
        register(operator)
    page = repo.list(EntryFilters(), 5, 1)
    assert (page.number, page.num_pages, page.total, len(page.items)) == (5, 9, 9, 1)
    assert None in page.page_range and page.page_range[0] == 1 and page.page_range[-1] == 9
    assert repo.list(EntryFilters(), 99, 4).number == 3  # página fuera de rango → última
