"""Aplicación (entries): casos de uso. Uno por acción del usuario."""
from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

from apps.entries.application.dtos import (
    AnswerValue,
    ContainerReadResult,
    EntryDetailDTO,
    EntrySummaryDTO,
    EvidenceUpload,
    GetEntryDetailQuery,
    ListEntriesQuery,
    PlateReadResult,
    RegisterEntryCommand,
    ReviewEntryCommand,
    TimelineStep,
)
from apps.entries.application.ports import FileStorage, OcrService, TruckEntryRepository
from apps.entries.domain import iso6346
from apps.entries.domain.entities import EntryStatus, TruckEntry
from apps.entries.domain.exceptions import (
    EntryNotFound,
    EntryValidationError,
    InvalidContainerCode,
    InvalidPlate,
    PermissionDeniedForAction,
)
from apps.entries.domain.parsers import ContainerCodeParser, PlateParser
from apps.entries.domain.value_objects import ContainerCode, Plate, normalize
from apps.questionnaire.application.ports import QuestionnaireRepository
from apps.questionnaire.domain.entities import Question, QuestionType
from apps.questionnaire.domain.visibility import VisibilityRule
from shared.application.base import BaseUseCase
from shared.application.pagination import Page

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
REQUIRED_MSG = "Este campo es obligatorio."


# -- OCR con IA --------------------------------------------------------------------------
class ReadPlateWithAI(BaseUseCase[bytes, PlateReadResult]):
    """Caso de uso (aplicación): lee la placa de una foto usando el puerto OcrService."""

    def __init__(self, ocr: OcrService, parser: PlateParser | None = None):
        self._ocr = ocr
        self._parser = parser or PlateParser()

    def execute(self, image_bytes: bytes) -> PlateReadResult:
        result = self._parser.parse(self._ocr.read_text(image_bytes))
        return PlateReadResult(result.raw_text, result.candidate, result.is_valid)


class ReadContainerWithAI(BaseUseCase[bytes, ContainerReadResult]):
    """Caso de uso (aplicación): lee el código de contenedor y verifica ISO 6346."""

    def __init__(self, ocr: OcrService, parser: ContainerCodeParser | None = None):
        self._ocr = ocr
        self._parser = parser or ContainerCodeParser()

    def execute(self, image_bytes: bytes) -> ContainerReadResult:
        result = self._parser.parse(self._ocr.read_text(image_bytes))
        expected = iso6346.compute_check_digit(result.candidate[:10]) if result.candidate else None
        return ContainerReadResult(result.raw_text, result.candidate, result.is_valid, expected)


# -- Registro ---------------------------------------------------------------------------
@dataclass
class _Coerced:
    """Resultado interno de interpretar la respuesta cruda de una pregunta."""

    visibility_value: Any = None
    answer: AnswerValue | None = None
    error: str | None = None

    @property
    def is_empty(self) -> bool:
        return self.answer is None and self.error is None


class RegisterTruckEntry(BaseUseCase[RegisterEntryCommand, int]):
    """Caso de uso (aplicación): valida y registra un ingreso de camión.

    Valida requeridos *visibles*, placa, ISO 6346 y evidencias; guarda respuestas y fotos.
    Un ISO inválido se puede guardar si el usuario lo confirma → estado «con observación».
    """

    def __init__(
        self,
        repository: TruckEntryRepository,
        storage: FileStorage,
        questionnaires: QuestionnaireRepository,
        max_upload_bytes: int = 8 * 1024 * 1024,
    ):
        self._repository = repository
        self._storage = storage
        self._questionnaires = questionnaires
        self._max_bytes = max_upload_bytes

    def execute(self, cmd: RegisterEntryCommand) -> int:
        questionnaire = self._questionnaires.get_active()
        if questionnaire is None:
            raise EntryValidationError({"__all__": "No hay un cuestionario activo."})

        questions = questionnaire.questions
        # Paso 1: valores «tolerantes» solo para decidir qué preguntas son visibles.
        lenient = {q.id: self._coerce(q, cmd.answers.get(q.id)).visibility_value for q in questions}
        visible = VisibilityRule.visible_questions(questions, lenient)

        errors: dict[Any, str] = {}
        answers: list[AnswerValue] = []
        typed: dict[int, Any] = {}
        uploads = self._valid_uploads(cmd.evidences, visible, errors)
        has_upload = {u.question_id for u in uploads}

        # Paso 2: validación estricta solo de las visibles.
        for question in visible:
            coerced = self._coerce(question, cmd.answers.get(question.id))
            if coerced.error:
                errors[question.id] = coerced.error
                continue
            if question.type is QuestionType.PHOTO:
                if question.is_required and question.id not in has_upload:
                    errors.setdefault(question.id, "Adjunta una foto.")
                continue
            if coerced.is_empty:
                if question.is_required:
                    errors[question.id] = REQUIRED_MSG
                continue
            typed[question.id] = coerced.visibility_value
            answers.append(coerced.answer)  # type: ignore[arg-type]

        plate = self._extract_plate(questionnaire, visible, typed, errors)
        container_code, iso_valid = self._extract_container(questionnaire, visible, typed, errors, cmd.confirm_iso_override)

        if errors:
            raise EntryValidationError(errors)

        answers = self._normalize_semantic_values(answers, questionnaire, plate, container_code)
        entry = TruckEntry.register(
            questionnaire_id=questionnaire.id,  # type: ignore[arg-type]
            created_by_id=cmd.user_id,
            plate=plate,
            container_code=container_code,
            container_iso_valid=iso_valid,
        )
        entry_id = self._repository.save(entry, answers)
        by_id = {q.id: q for q in visible}
        for upload in uploads:
            path = self._storage.save(entry_id, upload.filename, upload.content)
            self._repository.add_evidence(entry_id, upload.question_id, self._kind(by_id[upload.question_id]), path)
        return entry_id

    # -- interpretación de respuestas --------------------------------------------------
    def _coerce(self, q: Question, raw: Any) -> _Coerced:
        text = raw.strip() if isinstance(raw, str) else ""
        tag = q.semantic_tag
        qtype = q.type
        if qtype is QuestionType.PHOTO:
            return _Coerced()
        if qtype is QuestionType.MULTI_CHOICE:
            values = [v for v in (raw if isinstance(raw, (list, tuple)) else [raw]) if isinstance(v, str) and v.strip()]
            if not values:
                return _Coerced()
            chosen = [q.choice_by_value(v) for v in values]
            if any(c is None for c in chosen):
                return _Coerced(visibility_value=values, error="Opción no válida.")
            return _Coerced(
                visibility_value=values,
                answer=AnswerValue(
                    q.id, tag, value_text=", ".join(c.label for c in chosen),  # type: ignore[union-attr]
                    choice_ids=tuple(c.id for c in chosen), meta={"values": values},  # type: ignore[union-attr]
                ),
            )
        if text == "":
            return _Coerced()
        if qtype in (QuestionType.TEXT, QuestionType.PLATE_OCR, QuestionType.CONTAINER_OCR):
            value = normalize(text) if qtype.is_ocr else text
            return _Coerced(visibility_value=value, answer=AnswerValue(q.id, tag, value_text=value))
        if qtype is QuestionType.NUMBER:
            try:
                number = Decimal(text.replace(",", "."))
            except InvalidOperation:
                return _Coerced(error="Ingresa un número válido.")
            if number < 0:
                return _Coerced(error="El número no puede ser negativo.")
            return _Coerced(visibility_value=number, answer=AnswerValue(q.id, tag, value_number=number))
        if qtype is QuestionType.BOOLEAN:
            lowered = text.lower()
            if lowered in {"true", "1", "on", "si", "sí"}:
                flag = True
            elif lowered in {"false", "0", "no"}:
                flag = False
            else:
                return _Coerced(error="Responde Sí o No.")
            return _Coerced(visibility_value=flag, answer=AnswerValue(q.id, tag, value_bool=flag, value_text="Sí" if flag else "No"))
        if qtype is QuestionType.DATE:
            try:
                day = date.fromisoformat(text)
            except ValueError:
                return _Coerced(error="Fecha no válida (AAAA-MM-DD).")
            return _Coerced(visibility_value=text, answer=AnswerValue(q.id, tag, value_text=day.isoformat()))
        if qtype is QuestionType.SINGLE_CHOICE:
            choice = q.choice_by_value(text)
            if choice is None:
                return _Coerced(error="Opción no válida.")
            return _Coerced(
                visibility_value=choice.value,
                answer=AnswerValue(q.id, tag, value_text=choice.label, choice_ids=(choice.id,), meta={"values": [choice.value]}),  # type: ignore[arg-type]
            )
        return _Coerced(error="Tipo de pregunta no soportado.")

    # -- reglas de negocio -----------------------------------------------------------
    @staticmethod
    def _extract_plate(questionnaire, visible, typed, errors) -> str:
        question = questionnaire.question_by_tag("plate")
        value = typed.get(question.id, "") if question else ""
        if question and question.id in errors:
            return ""
        if not value:
            if question is None:
                errors["__all__"] = "El cuestionario no tiene una pregunta de placa."
            else:
                errors.setdefault(question.id, REQUIRED_MSG)
            return ""
        try:
            return Plate.from_raw(value).value
        except InvalidPlate as exc:
            errors[question.id] = str(exc)
            return ""

    @staticmethod
    def _extract_container(questionnaire, visible, typed, errors, confirmed: bool) -> tuple[str, bool]:
        question = questionnaire.question_by_tag("container_code")
        if question is None or question.id not in typed or question.id in errors:
            return "", True
        raw = typed[question.id]
        try:
            return ContainerCode.from_raw(raw).value, True
        except InvalidContainerCode as exc:
            if exc.reason == "check_digit" and confirmed:
                return normalize(raw), False
            if exc.reason == "check_digit":
                errors[question.id] = f"{exc} Marca la casilla de confirmación para guardarlo con observación."
            else:
                errors[question.id] = str(exc)
            return "", True

    @staticmethod
    def _normalize_semantic_values(answers, questionnaire, plate: str, container: str) -> list[AnswerValue]:
        plate_q = questionnaire.question_by_tag("plate")
        container_q = questionnaire.question_by_tag("container_code")
        fixed = []
        for answer in answers:
            if plate_q and answer.question_id == plate_q.id:
                answer = replace(answer, value_text=plate)
            elif container_q and answer.question_id == container_q.id and container:
                answer = replace(answer, value_text=container)
            fixed.append(answer)
        return fixed

    def _valid_uploads(self, evidences: list[EvidenceUpload], visible: list[Question], errors: dict) -> list[EvidenceUpload]:
        photo_questions = {q.id: q for q in visible if q.type.has_photo_input}
        valid: list[EvidenceUpload] = []
        for upload in evidences:
            if upload.question_id not in photo_questions or not upload.content:
                continue
            extension = upload.filename.rsplit(".", 1)[-1].lower() if "." in upload.filename else ""
            if extension not in ALLOWED_EXTENSIONS:
                errors[upload.question_id] = "Formato no permitido (usa JPG, PNG o WEBP)."
            elif len(upload.content) > self._max_bytes:
                errors[upload.question_id] = f"La foto supera {self._max_bytes // (1024 * 1024)} MB."
            else:
                valid.append(upload)
        return valid

    @staticmethod
    def _kind(question: Question) -> str:
        if question.type is QuestionType.PLATE_OCR:
            return "plate"
        if question.type is QuestionType.CONTAINER_OCR:
            return "container"
        return "novelty" if question.semantic_tag == "novelty_photo" else "photo"


# -- Consulta ---------------------------------------------------------------------------
class ListEntries(BaseUseCase[ListEntriesQuery, Page[EntrySummaryDTO]]):
    """Caso de uso (aplicación): histórico paginado. El operario solo ve lo suyo."""

    def __init__(self, repository: TruckEntryRepository):
        self._repository = repository

    def execute(self, query: ListEntriesQuery) -> Page[EntrySummaryDTO]:
        filters = query.filters if query.actor.can_see_all else replace(query.filters, user_id=query.actor.id)
        return self._repository.list(filters, query.page, query.page_size)


class GetEntryDetail(BaseUseCase[GetEntryDetailQuery, EntryDetailDTO]):
    """Caso de uso (aplicación): detalle de un ingreso con su línea de estado."""

    def __init__(self, repository: TruckEntryRepository):
        self._repository = repository

    def execute(self, query: GetEntryDetailQuery) -> EntryDetailDTO:
        detail = self._repository.get_detail(query.entry_id)
        if detail is None or (not query.actor.can_see_all and detail.created_by_id != query.actor.id):
            raise EntryNotFound("El ingreso no existe.")  # no se revela si pertenece a otro usuario
        return replace(detail, timeline=self.build_timeline(detail))

    @staticmethod
    def build_timeline(detail: EntryDetailDTO) -> list[TimelineStep]:
        sequence = [("registrado", "Registrado", detail.created_at)]
        if detail.container_iso_valid is False:
            sequence.append(("con_observacion", "Con observación", None))
        sequence.append(("revisado", "Revisado", detail.reviewed_at))
        keys = [key for key, _, _ in sequence]
        current = len(keys) - 1 if detail.status == EntryStatus.REVIEWED.value else keys.index(detail.status)
        steps = []
        for index, (key, label, at) in enumerate(sequence):
            if detail.status == EntryStatus.REVIEWED.value or index < current:
                state = "done"
            elif index == current:
                state = "current"
            else:
                state = "pending"
            steps.append(TimelineStep(key, label, state, at))
        return steps


class ReviewEntry(BaseUseCase[ReviewEntryCommand, None]):
    """Caso de uso (aplicación): el supervisor marca un ingreso como revisado."""

    def __init__(self, repository: TruckEntryRepository, clock: Callable[[], datetime] | None = None):
        self._repository = repository
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def execute(self, cmd: ReviewEntryCommand) -> None:
        if not cmd.actor.can_review:
            raise PermissionDeniedForAction("Tu rol no puede revisar ingresos.")
        entry = self._repository.get(cmd.entry_id)
        if entry is None:
            raise EntryNotFound("El ingreso no existe.")
        entry.mark_reviewed(cmd.actor.id, cmd.comment, self._clock())
        self._repository.save_review(entry)
