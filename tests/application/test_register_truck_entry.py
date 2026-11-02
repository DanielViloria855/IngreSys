import pytest

from apps.entries.application.dtos import EvidenceUpload, RegisterEntryCommand
from apps.entries.domain.entities import EntryStatus
from apps.entries.domain.exceptions import EntryValidationError

from .conftest import BOXES, CONTAINER, HAS_CONTAINER, NOV_PHOTO, NOV_TYPE, NOVELTY, PLATE, SEAL, SUPPLIER, valid_answers


def cmd(answers, evidences=None, confirm=False):
    return RegisterEntryCommand(user_id=7, answers=answers, evidences=evidences or [], confirm_iso_override=confirm)


def test_registers_minimal_entry_without_container(register, repo):
    entry_id = register.execute(cmd(valid_answers()))
    entry = repo.get(entry_id)
    assert entry.plate == "SKX482" and entry.status is EntryStatus.REGISTERED and entry.container_code == ""
    assert {a.question_id for a in repo.answers[entry_id]} == {PLATE, SUPPLIER, HAS_CONTAINER, NOVELTY}


def test_missing_required_visible_questions(register):
    with pytest.raises(EntryValidationError) as err:
        register.execute(cmd({HAS_CONTAINER: "true"}))
    assert {PLATE, SUPPLIER, CONTAINER, SEAL, NOVELTY} <= set(err.value.errors)


def test_hidden_questions_are_not_required_nor_saved(register, repo):
    answers = valid_answers()
    answers[SEAL] = "SELLO-OCULTO"  # has_container=false → la pregunta está oculta
    entry_id = register.execute(cmd(answers))
    assert SEAL not in {a.question_id for a in repo.answers[entry_id]}


def test_invalid_plate_is_rejected(register):
    with pytest.raises(EntryValidationError) as err:
        register.execute(cmd(valid_answers(**{})  | {PLATE: "ABCD12"}))
    assert PLATE in err.value.errors


def test_valid_container_is_saved_with_iso_ok(register, repo):
    answers = valid_answers() | {HAS_CONTAINER: "true", CONTAINER: "csqu 305438 3", SEAL: "S1"}
    entry = repo.get(register.execute(cmd(answers)))
    assert entry.container_code == "CSQU3054383" and entry.container_iso_valid and entry.status is EntryStatus.REGISTERED


def test_invalid_iso_requires_confirmation(register):
    answers = valid_answers() | {HAS_CONTAINER: "true", CONTAINER: "CSQU3054384", SEAL: "S1"}
    with pytest.raises(EntryValidationError) as err:
        register.execute(cmd(answers))
    assert "esperado 3" in err.value.errors[CONTAINER]


def test_invalid_iso_confirmed_goes_with_observation(register, repo):
    answers = valid_answers() | {HAS_CONTAINER: "true", CONTAINER: "CSQU3054384", SEAL: "S1"}
    entry = repo.get(register.execute(cmd(answers, confirm=True)))
    assert entry.container_code == "CSQU3054384"
    assert not entry.container_iso_valid and entry.status is EntryStatus.WITH_OBSERVATION


def test_bad_container_format_is_never_saved_even_if_confirmed(register):
    answers = valid_answers() | {HAS_CONTAINER: "true", CONTAINER: "XYZ", SEAL: "S1"}
    with pytest.raises(EntryValidationError) as err:
        register.execute(cmd(answers, confirm=True))
    assert CONTAINER in err.value.errors


def test_multi_choice_and_number_are_typed(register, repo):
    answers = valid_answers() | {BOXES: "12,5", NOVELTY: "true", NOV_TYPE: ["pests", "humidity"]}
    entry_id = register.execute(cmd(answers))
    saved = {a.question_id: a for a in repo.answers[entry_id]}
    assert float(saved[BOXES].value_number) == 12.5
    assert saved[NOV_TYPE].value_text == "Plagas, Humedad" and saved[NOV_TYPE].meta["values"] == ["pests", "humidity"]


def test_invalid_choice_and_negative_number(register):
    with pytest.raises(EntryValidationError) as err:
        register.execute(cmd(valid_answers() | {BOXES: "-3", SUPPLIER: "inexistente"}))
    assert BOXES in err.value.errors and SUPPLIER in err.value.errors


def test_evidence_is_stored_with_kind(register, repo, storage):
    answers = valid_answers() | {NOVELTY: "true", NOV_TYPE: ["pests"]}
    uploads = [EvidenceUpload(PLATE, "placa.jpg", b"x" * 10), EvidenceUpload(NOV_PHOTO, "n.png", b"y" * 10)]
    entry_id = register.execute(cmd(answers, uploads))
    assert sorted(kind for _, _, kind, _ in repo.evidences) == ["novelty", "plate"]
    assert len(storage.files) == 2 and all(e[0] == entry_id for e in repo.evidences)


def test_evidence_rejects_bad_extension_and_size(register):
    with pytest.raises(EntryValidationError) as err:
        register.execute(cmd(valid_answers(), [EvidenceUpload(PLATE, "virus.exe", b"x")]))
    assert PLATE in err.value.errors
    with pytest.raises(EntryValidationError) as err:
        register.execute(cmd(valid_answers(), [EvidenceUpload(PLATE, "grande.jpg", b"x" * 2048)]))
    assert "supera" in err.value.errors[PLATE]


def test_photo_question_optional_ok_but_required_photo_needs_upload(repo, storage):
    from apps.entries.application.use_cases import RegisterTruckEntry
    from apps.questionnaire.infrastructure.in_memory import InMemoryQuestionnaireRepository
    from .conftest import build_questionnaire

    questionnaire = build_questionnaire()
    photo = next(q for q in questionnaire.questions if q.id == NOV_PHOTO)
    answers = valid_answers() | {NOVELTY: "true", NOV_TYPE: ["pests"]}
    register = RegisterTruckEntry(repo, storage, InMemoryQuestionnaireRepository(questionnaire))
    assert register.execute(cmd(answers))  # opcional: se acepta sin foto
    photo.is_required = True
    with pytest.raises(EntryValidationError) as err:
        register.execute(cmd(answers))
    assert err.value.errors[NOV_PHOTO] == "Adjunta una foto."
