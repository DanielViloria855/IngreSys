"""Dominio (questionnaire): preguntas, opciones y cuestionario."""
from dataclasses import dataclass, field
from enum import Enum

from shared.domain.base import DomainError, Entity, ValueObject


class QuestionType(str, Enum):
    """Tipos de pregunta del formulario dinámico."""

    TEXT = "text"
    NUMBER = "number"
    BOOLEAN = "boolean"
    SINGLE_CHOICE = "single_choice"
    MULTI_CHOICE = "multi_choice"
    DATE = "date"
    PHOTO = "photo"
    PLATE_OCR = "plate_ocr"
    CONTAINER_OCR = "container_ocr"

    @property
    def has_photo_input(self) -> bool:
        return self in (QuestionType.PHOTO, QuestionType.PLATE_OCR, QuestionType.CONTAINER_OCR)

    @property
    def is_ocr(self) -> bool:
        return self in (QuestionType.PLATE_OCR, QuestionType.CONTAINER_OCR)


@dataclass(frozen=True)
class ChoiceOption(ValueObject):
    """Value object (dominio): una opción de una pregunta de selección."""

    id: int | None
    label: str
    value: str

    def _validate(self) -> None:
        if not self.label.strip() or not self.value.strip():
            raise DomainError("Una opción necesita etiqueta y valor.")


@dataclass(eq=False, kw_only=True)
class Question(Entity):
    """Entidad (dominio): una pregunta del cuestionario, con su regla de visibilidad opcional."""

    id: int | None = None
    order: int = 0
    text: str
    help_text: str = ""
    type: QuestionType
    is_required: bool = False
    semantic_tag: str = ""
    depends_on_id: int | None = None
    depends_on_value: str = ""
    choices: tuple[ChoiceOption, ...] = ()

    def choice_by_value(self, value: str) -> ChoiceOption | None:
        return next((c for c in self.choices if c.value == value), None)


@dataclass(eq=False, kw_only=True)
class Questionnaire(Entity):
    """Entidad (dominio): conjunto ordenado de preguntas activas."""

    id: int | None = None
    name: str
    questions: list[Question] = field(default_factory=list)

    def question_by_tag(self, tag: str) -> Question | None:
        return next((q for q in self.questions if q.semantic_tag == tag), None)
