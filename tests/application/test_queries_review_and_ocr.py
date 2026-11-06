"""Unitarias (aplicación): consultas, línea de estado, revisión, OCR y cuestionario activo."""
from datetime import datetime, timezone

import pytest

from apps.entries.application.dtos import EntryDetailDTO, EntryFilters, ListEntriesQuery, ReviewEntryCommand
from apps.entries.application.use_cases import GetEntryDetail, ListEntries, ReadContainerWithAI, ReadPlateWithAI, ReviewEntry
from apps.entries.domain.entities import TruckEntry
from apps.entries.domain.exceptions import OcrUnavailable
from apps.entries.infrastructure.in_memory import InMemoryTruckEntryRepository
from apps.entries.infrastructure.ocr.fake_ocr_adapter import FakeOcrAdapter
from apps.questionnaire.application.use_cases import GetActiveQuestionnaire, NoActiveQuestionnaire
from apps.questionnaire.domain.entities import Questionnaire
from apps.questionnaire.infrastructure.in_memory import InMemoryQuestionnaireRepository
from shared.application.actor import Actor
from shared.domain.roles import Role

NOW = datetime(2026, 11, 5, 8, 0, tzinfo=timezone.utc)


def detail(status, iso_valid=True, reviewed_at=None):
    return EntryDetailDTO(
        id=1, created_at=NOW, created_by_id=1, created_by_name="", plate="ABC123", container_code="X" if iso_valid is not None else "",
        container_iso_valid=iso_valid, iso_read_digit=None, iso_expected_digit=None, status=status, status_label="", status_variant="",
        answers=[], evidences=[], reviewed_at=reviewed_at,
    )


@pytest.mark.parametrize(
    "status,iso_valid,expected",
    [
        ("registrado", True, [("registrado", "current"), ("revisado", "pending")]),
        ("registrado", None, [("registrado", "current"), ("revisado", "pending")]),
        ("con_observacion", False, [("registrado", "done"), ("con_observacion", "current"), ("revisado", "pending")]),
        ("revisado", True, [("registrado", "done"), ("revisado", "done")]),
        ("revisado", False, [("registrado", "done"), ("con_observacion", "done"), ("revisado", "done")]),
    ],
)
def test_timeline(status, iso_valid, expected):
    steps = GetEntryDetail.build_timeline(detail(status, iso_valid))
    assert [(s.key, s.state) for s in steps] == expected
    assert steps[0].at == NOW


def make_repo(*owners):
    repo = InMemoryTruckEntryRepository()
    for owner in owners:
        repo.save(TruckEntry.register(questionnaire_id=1, created_by_id=owner, plate="ABC123", container_code="", container_iso_valid=True), [])
    return repo


def test_operator_list_is_forced_to_own_entries_even_if_asking_for_another_user():
    page = ListEntries(make_repo(1, 2, 2)).execute(ListEntriesQuery(EntryFilters(user_id=2), Actor(1, "op", Role.OPERATOR)))
    assert page.total == 1


@pytest.mark.parametrize("role", [Role.SUPERVISOR, Role.ADMIN])
def test_privileged_list_keeps_filters(role):
    use_case = ListEntries(make_repo(1, 2, 2))
    assert use_case.execute(ListEntriesQuery(EntryFilters(), Actor(9, "s", role))).total == 3
    assert use_case.execute(ListEntriesQuery(EntryFilters(user_id=2), Actor(9, "s", role))).total == 2


def test_in_memory_pagination():
    page = ListEntries(make_repo(*[1] * 5)).execute(ListEntriesQuery(EntryFilters(), Actor(9, "s", Role.ADMIN), page=2, page_size=2))
    assert (page.number, page.num_pages, page.total, len(page.items)) == (2, 3, 5, 2)


def test_admin_can_review_and_default_clock_is_utc_aware():
    repo = make_repo(1)
    ReviewEntry(repo).execute(ReviewEntryCommand(1, Actor(3, "a", Role.ADMIN)))
    reviewed_at = repo.get(1).reviewed_at
    assert reviewed_at.tzinfo is not None and reviewed_at.utcoffset().total_seconds() == 0


def test_review_permission_is_checked_before_lookup():
    """Un operario recibe «sin permiso» aunque el ingreso no exista (no revela existencia)."""
    from apps.entries.domain.exceptions import PermissionDeniedForAction

    with pytest.raises(PermissionDeniedForAction):
        ReviewEntry(make_repo()).execute(ReviewEntryCommand(999, Actor(1, "o", Role.OPERATOR)))


def test_detail_of_missing_entry_is_not_found_for_everyone():
    from apps.entries.application.dtos import GetEntryDetailQuery
    from apps.entries.domain.exceptions import EntryNotFound

    with pytest.raises(EntryNotFound):
        GetEntryDetail(make_repo()).execute(GetEntryDetailQuery(1, Actor(1, "a", Role.ADMIN)))


# -- OCR -----------------------------------------------------------------------------------------
def test_plate_ocr_not_valid_when_nothing_matches():
    result = ReadPlateWithAI(FakeOcrAdapter(["COLOMBIA"])).execute(b"x")
    assert (result.candidate, result.is_valid, result.raw_text) == ("", False, "COLOMBIA")


def test_container_ocr_uses_custom_parser():
    class Always:
        def parse(self, lines):
            from apps.entries.domain.parsers import ParseResult

            return ParseResult("raw", "MSKU9070323", True)

    result = ReadContainerWithAI(FakeOcrAdapter([]), parser=Always()).execute(b"x")
    assert result.expected_check_digit == 3 and result.raw_text == "raw"


def test_ocr_unavailable_propagates():
    class Down:
        def read_text(self, _):
            raise OcrUnavailable("caído")

    for use_case in (ReadPlateWithAI(Down()), ReadContainerWithAI(Down())):
        with pytest.raises(OcrUnavailable):
            use_case.execute(b"x")


def test_fake_ocr_rotates_samples_by_image_and_returns_copies():
    adapter = FakeOcrAdapter()
    assert adapter.read_text(bytes([0])) != adapter.read_text(bytes([1]))
    fixed = FakeOcrAdapter(["A"])
    fixed.read_text(b"").append("mutado")
    assert fixed.read_text(b"") == ["A"]


# -- cuestionario activo -------------------------------------------------------------------------
def test_get_active_questionnaire():
    questionnaire = Questionnaire(id=1, name="x")
    assert GetActiveQuestionnaire(InMemoryQuestionnaireRepository(questionnaire)).execute() is questionnaire
    with pytest.raises(NoActiveQuestionnaire, match="seed_questionnaire"):
        GetActiveQuestionnaire(InMemoryQuestionnaireRepository()).execute()
