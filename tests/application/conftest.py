import pytest

from apps.entries.application.use_cases import RegisterTruckEntry
from apps.entries.infrastructure.in_memory import InMemoryFileStorage, InMemoryTruckEntryRepository
from apps.questionnaire.domain.entities import ChoiceOption, Question, QuestionType, Questionnaire
from apps.questionnaire.infrastructure.in_memory import InMemoryQuestionnaireRepository

PLATE, HAS_CONTAINER, CONTAINER, SEAL, NOVELTY, NOV_TYPE, NOV_PHOTO, BOXES, SUPPLIER = range(1, 10)


def build_questionnaire() -> Questionnaire:
    qs = [
        Question(id=PLATE, order=1, text="Placa", type=QuestionType.PLATE_OCR, is_required=True, semantic_tag="plate"),
        Question(id=SUPPLIER, order=2, text="Proveedor", type=QuestionType.SINGLE_CHOICE, is_required=True, semantic_tag="supplier",
                 choices=(ChoiceOption(1, "Andina", "andina"), ChoiceOption(2, "Caribe", "caribe"))),
        Question(id=HAS_CONTAINER, order=3, text="¿Contenedor?", type=QuestionType.BOOLEAN, is_required=True, semantic_tag="has_container"),
        Question(id=CONTAINER, order=4, text="Contenedor", type=QuestionType.CONTAINER_OCR, is_required=True, semantic_tag="container_code",
                 depends_on_id=HAS_CONTAINER, depends_on_value="true"),
        Question(id=SEAL, order=5, text="Sello", type=QuestionType.TEXT, is_required=True, semantic_tag="seal_number",
                 depends_on_id=HAS_CONTAINER, depends_on_value="true"),
        Question(id=BOXES, order=6, text="Cajas", type=QuestionType.NUMBER, semantic_tag="boxes_count"),
        Question(id=NOVELTY, order=7, text="¿Novedad?", type=QuestionType.BOOLEAN, is_required=True, semantic_tag="has_novelty"),
        Question(id=NOV_TYPE, order=8, text="Tipo", type=QuestionType.MULTI_CHOICE, is_required=True, semantic_tag="novelty_type",
                 depends_on_id=NOVELTY, depends_on_value="true",
                 choices=(ChoiceOption(3, "Plagas", "pests"), ChoiceOption(4, "Humedad", "humidity"))),
        Question(id=NOV_PHOTO, order=9, text="Foto novedad", type=QuestionType.PHOTO, semantic_tag="novelty_photo",
                 depends_on_id=NOVELTY, depends_on_value="true"),
    ]
    return Questionnaire(id=1, name="Test", questions=qs)


@pytest.fixture
def repo():
    return InMemoryTruckEntryRepository()


@pytest.fixture
def storage():
    return InMemoryFileStorage()


@pytest.fixture
def register(repo, storage):
    return RegisterTruckEntry(repo, storage, InMemoryQuestionnaireRepository(build_questionnaire()), max_upload_bytes=1024)


def valid_answers(**overrides):
    answers = {PLATE: "skx 482", SUPPLIER: "andina", HAS_CONTAINER: "false", NOVELTY: "false"}
    answers.update(overrides)
    return answers
