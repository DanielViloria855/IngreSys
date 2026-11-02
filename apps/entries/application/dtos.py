"""Aplicación (entries): DTOs de entrada y salida de los casos de uso."""
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Mapping

from shared.application.actor import Actor

STATUS_META = {
    "registrado": ("Registrado", "info"),
    "con_observacion": ("Con observación", "warning"),
    "revisado": ("Revisado", "success"),
}


# -- OCR ------------------------------------------------------------------------------
@dataclass(frozen=True)
class PlateReadResult:
    raw_text: str
    candidate: str
    is_valid: bool


@dataclass(frozen=True)
class ContainerReadResult:
    raw_text: str
    candidate: str
    is_valid: bool
    expected_check_digit: int | None


# -- Registro -------------------------------------------------------------------------
@dataclass(frozen=True)
class EvidenceUpload:
    question_id: int
    filename: str
    content: bytes


@dataclass(frozen=True)
class RegisterEntryCommand:
    """Lo que envía el formulario: respuestas crudas por id de pregunta + fotos + confirmación de ISO."""

    user_id: int
    answers: Mapping[int, Any]
    evidences: list[EvidenceUpload] = field(default_factory=list)
    confirm_iso_override: bool = False


@dataclass(frozen=True)
class AnswerValue:
    """Respuesta ya validada y tipada, lista para persistir."""

    question_id: int
    semantic_tag: str
    value_text: str = ""
    value_number: Decimal | None = None
    value_bool: bool | None = None
    choice_ids: tuple[int, ...] = ()
    meta: Mapping[str, Any] = field(default_factory=dict)


# -- Consulta -------------------------------------------------------------------------
@dataclass(frozen=True)
class EntryFilters:
    date_from: date | None = None
    date_to: date | None = None
    plate: str = ""
    container: str = ""
    status: str = ""
    novelty: str = ""  # "" | "yes" | "no"
    user_id: int | None = None


@dataclass(frozen=True)
class ListEntriesQuery:
    filters: EntryFilters
    actor: Actor
    page: int = 1
    page_size: int = 20


@dataclass(frozen=True)
class EntrySummaryDTO:
    id: int
    created_at: datetime
    plate: str
    container_code: str
    container_iso_valid: bool | None  # None = no trajo contenedor
    supplier: str
    created_by_name: str
    status: str
    status_label: str
    status_variant: str
    has_novelty: bool | None


@dataclass(frozen=True)
class AnswerDisplayDTO:
    question_text: str
    display_value: str
    semantic_tag: str


@dataclass(frozen=True)
class EvidenceDTO:
    url: str
    kind: str
    kind_label: str
    question_text: str


@dataclass(frozen=True)
class TimelineStep:
    key: str
    label: str
    state: str  # done | current | pending
    at: datetime | None = None


@dataclass(frozen=True)
class EntryDetailDTO:
    id: int
    created_at: datetime
    created_by_id: int
    created_by_name: str
    plate: str
    container_code: str
    container_iso_valid: bool | None
    iso_read_digit: int | None
    iso_expected_digit: int | None
    status: str
    status_label: str
    status_variant: str
    answers: list[AnswerDisplayDTO]
    evidences: list[EvidenceDTO]
    reviewed_by_name: str = ""
    reviewed_at: datetime | None = None
    review_comment: str = ""
    timeline: list[TimelineStep] = field(default_factory=list)


@dataclass(frozen=True)
class GetEntryDetailQuery:
    entry_id: int
    actor: Actor


@dataclass(frozen=True)
class ReviewEntryCommand:
    entry_id: int
    actor: Actor
    comment: str = ""
