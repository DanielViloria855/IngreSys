"""Unitarias (aplicación): RegisterTruckEntry — interpretación de cada tipo de respuesta y casos límite."""
import pytest

from apps.entries.application.dtos import EvidenceUpload, RegisterEntryCommand
from apps.entries.application.use_cases import REQUIRED_MSG, RegisterTruckEntry
from apps.entries.domain.exceptions import EntryValidationError
from apps.questionnaire.domain.entities import Question, QuestionType, Questionnaire
from apps.questionnaire.infrastructure.in_memory import InMemoryQuestionnaireRepository

from .conftest import BOXES, CONTAINER, HAS_CONTAINER, NOV_TYPE, NOVELTY, PLATE, SEAL, SUPPLIER, build_questionnaire, valid_answers

DATE_Q = 50


def cmd(answers, evidences=None, confirm=False):
    return RegisterEntryCommand(user_id=7, answers=answers, evidences=evidences or [], confirm_iso_override=confirm)


def errors_of(register, answers, **kw):
    with pytest.raises(EntryValidationError) as err:
        register.execute(cmd(answers, **kw))
    return err.value.errors


def saved_answers(repo, entry_id):
    return {a.question_id: a for a in repo.answers[entry_id]}


@pytest.fixture
def register_with_date(repo, storage):
    questionnaire = build_questionnaire()
    questionnaire.questions.append(Question(id=DATE_Q, order=99, text="Fecha", type=QuestionType.DATE, semantic_tag="arrival"))
    return RegisterTruckEntry(repo, storage, InMemoryQuestionnaireRepository(questionnaire), max_upload_bytes=1024)


# -- configuración del cuestionario ---------------------------------------------------------------
def test_no_active_questionnaire(repo, storage):
    use_case = RegisterTruckEntry(repo, storage, InMemoryQuestionnaireRepository(None))
    assert errors_of(use_case, {}) == {"__all__": "No hay un cuestionario activo."}


def test_questionnaire_without_plate_question(repo, storage):
    questionnaire = Questionnaire(id=1, name="x", questions=[Question(id=1, order=1, text="Nota", type=QuestionType.TEXT)])
    use_case = RegisterTruckEntry(repo, storage, InMemoryQuestionnaireRepository(questionnaire))
    assert "placa" in errors_of(use_case, {1: "hola"})["__all__"]
    assert repo.entries == {}


# -- booleanos -----------------------------------------------------------------------------------
@pytest.mark.parametrize("raw,flag", [("true", True), ("TRUE", True), ("1", True), ("on", True), ("si", True), ("Sí", True),
                                      ("false", False), ("0", False), ("No", False)])
def test_boolean_variants(register, repo, raw, flag):
    entry_id = register.execute(cmd(valid_answers(**{}) | {NOVELTY: raw, NOV_TYPE: ["pests"]}))
    saved = saved_answers(repo, entry_id)[NOVELTY]
    assert saved.value_bool is flag and saved.value_text == ("Sí" if flag else "No")


def test_boolean_garbage(register):
    assert errors_of(register, valid_answers(**{}) | {NOVELTY: "tal vez"})[NOVELTY] == "Responde Sí o No."


# -- números -------------------------------------------------------------------------------------
@pytest.mark.parametrize("raw,expected", [("12", "12"), ("12,5", "12.5"), (" 3.25 ", "3.25"), ("0", "0")])
def test_numbers_accept_comma_and_dot(register, repo, raw, expected):
    entry_id = register.execute(cmd(valid_answers(**{}) | {BOXES: raw}))
    assert str(saved_answers(repo, entry_id)[BOXES].value_number) == expected


@pytest.mark.parametrize("raw,msg", [("abc", "Ingresa un número válido."), ("1,2,3", "Ingresa un número válido."), ("-0.01", "El número no puede ser negativo.")])
def test_numbers_rejected(register, raw, msg):
    assert errors_of(register, valid_answers(**{}) | {BOXES: raw})[BOXES] == msg


@pytest.mark.xfail(strict=True, reason="BUG: Decimal('NaN') < 0 lanza InvalidOperation sin capturar → error 500 en la vista")
@pytest.mark.parametrize("raw", ["NaN", "sNaN"])
def test_nan_is_a_validation_error_not_a_crash(register, raw):
    assert BOXES in errors_of(register, valid_answers(**{}) | {BOXES: raw})


@pytest.mark.xfail(strict=True, reason="BUG: 'Infinity' se acepta como número y luego no cabe en DecimalField(max_digits=14)")
def test_infinity_is_rejected(register):
    assert BOXES in errors_of(register, valid_answers(**{}) | {BOXES: "Infinity"})


# -- fechas, texto, opciones ---------------------------------------------------------------------
def test_date_is_stored_in_iso_format(register_with_date, repo):
    entry_id = register_with_date.execute(cmd(valid_answers(**{}) | {DATE_Q: "2026-11-05"}))
    assert saved_answers(repo, entry_id)[DATE_Q].value_text == "2026-11-05"


@pytest.mark.parametrize("raw", ["05/11/2026", "2026-02-30", "mañana"])
def test_invalid_dates(register_with_date, raw):
    assert errors_of(register_with_date, valid_answers(**{}) | {DATE_Q: raw})[DATE_Q] == "Fecha no válida (AAAA-MM-DD)."


def test_whitespace_only_counts_as_empty(register):
    assert errors_of(register, valid_answers(**{}) | {PLATE: "   "})[PLATE] == REQUIRED_MSG


def test_non_string_raw_value_counts_as_empty(register):
    assert errors_of(register, valid_answers(**{}) | {PLATE: 12345})[PLATE] == REQUIRED_MSG


def test_single_choice_stores_label_choice_id_and_value(register, repo):
    entry_id = register.execute(cmd(valid_answers(**{}) | {SUPPLIER: "caribe"}))
    saved = saved_answers(repo, entry_id)[SUPPLIER]
    assert (saved.value_text, saved.choice_ids, saved.meta) == ("Caribe", (2,), {"values": ["caribe"]})


def test_multi_choice_accepts_a_single_string(register, repo):
    entry_id = register.execute(cmd(valid_answers(**{}) | {NOVELTY: "true", NOV_TYPE: "pests"}))
    assert saved_answers(repo, entry_id)[NOV_TYPE].choice_ids == (3,)


def test_multi_choice_with_one_invalid_option(register):
    assert errors_of(register, valid_answers(**{}) | {NOVELTY: "true", NOV_TYPE: ["pests", "fuego"]})[NOV_TYPE] == "Opción no válida."


def test_multi_choice_ignores_blank_items_and_requires_one(register):
    assert errors_of(register, valid_answers(**{}) | {NOVELTY: "true", NOV_TYPE: ["", "  "]})[NOV_TYPE] == REQUIRED_MSG


# -- placa y contenedor --------------------------------------------------------------------------
def test_plate_answer_is_saved_normalized(register, repo):
    entry_id = register.execute(cmd(valid_answers(**{}) | {PLATE: "skx-482"}))
    assert saved_answers(repo, entry_id)[PLATE].value_text == "SKX482"


def test_trailer_plate(register, repo):
    entry_id = register.execute(cmd(valid_answers(**{}) | {PLATE: "r 12345"}))
    assert repo.get(entry_id).plate == "R12345"


def test_container_answer_is_saved_normalized(register, repo):
    answers = valid_answers(**{}) | {HAS_CONTAINER: "true", CONTAINER: "csqu-305438-3", SEAL: "S1"}
    entry_id = register.execute(cmd(answers))
    assert saved_answers(repo, entry_id)[CONTAINER].value_text == "CSQU3054383"


def test_bad_iso_message_explains_how_to_confirm(register):
    answers = valid_answers(**{}) | {HAS_CONTAINER: "true", CONTAINER: "CSQU3054384", SEAL: "S1"}
    assert "Marca la casilla" in errors_of(register, answers)[CONTAINER]


def test_confirm_flag_is_irrelevant_without_container(register, repo):
    entry = repo.get(register.execute(cmd(valid_answers(**{}), confirm=True)))
    assert entry.container_iso_valid and entry.container_code == ""


def test_all_errors_are_reported_together(register):
    answers = {PLATE: "XX", SUPPLIER: "nope", HAS_CONTAINER: "true", CONTAINER: "BAD", NOVELTY: "quizas", BOXES: "-1"}
    assert {PLATE, SUPPLIER, CONTAINER, SEAL, NOVELTY, BOXES} <= set(errors_of(register, answers))


# -- evidencias ----------------------------------------------------------------------------------
def test_nothing_is_stored_when_validation_fails(register, repo, storage):
    errors_of(register, {PLATE: "XX"}, evidences=[EvidenceUpload(PLATE, "p.jpg", b"x")])
    assert storage.files == {} and repo.entries == {} and repo.evidences == []


@pytest.mark.parametrize("filename", ["FOTO.JPG", "a.b.jpeg", "x.webp", "y.PNG"])
def test_allowed_extensions_any_case(register, storage, filename):
    register.execute(cmd(valid_answers(**{}), [EvidenceUpload(PLATE, filename, b"x")]))
    assert len(storage.files) == 1


@pytest.mark.parametrize("filename", ["sin_extension", "foto.gif", "foto.jpg.exe", ".jpg."])
def test_rejected_extensions(register, filename):
    assert errors_of(register, valid_answers(**{}), evidences=[EvidenceUpload(PLATE, filename, b"x")])[PLATE].startswith("Formato no permitido")


def test_uploads_for_hidden_non_photo_or_empty_are_ignored(register, repo, storage):
    uploads = [
        EvidenceUpload(CONTAINER, "c.jpg", b"x"),  # pregunta oculta (sin contenedor)
        EvidenceUpload(SUPPLIER, "s.jpg", b"x"),   # pregunta sin foto
        EvidenceUpload(PLATE, "p.jpg", b""),        # archivo vacío
        EvidenceUpload(999, "z.jpg", b"x"),         # pregunta inexistente
    ]
    register.execute(cmd(valid_answers(**{}), uploads))
    assert storage.files == {} and repo.evidences == []


def test_upload_exactly_at_limit_is_accepted(register, storage):
    register.execute(cmd(valid_answers(**{}), [EvidenceUpload(PLATE, "p.jpg", b"x" * 1024)]))
    assert len(storage.files) == 1


def test_container_photo_kind(register, repo):
    answers = valid_answers(**{}) | {HAS_CONTAINER: "true", CONTAINER: "CSQU3054383", SEAL: "S1"}
    register.execute(cmd(answers, [EvidenceUpload(CONTAINER, "c.jpg", b"x")]))
    assert [kind for _, _, kind, _ in repo.evidences] == ["container"]
