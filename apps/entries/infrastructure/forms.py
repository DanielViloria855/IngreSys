"""Infraestructura (entries): construcción dinámica del formulario a partir del cuestionario.

- `build_field_viewmodels`: de las preguntas a datos listos para las plantillas (sin lógica en el template).
- `parse_entry_command`: del POST/FILES al comando que entiende el caso de uso.
"""
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from django.http import QueryDict
from django.urls import reverse

from apps.entries.application.dtos import EntryFilters, EvidenceUpload, RegisterEntryCommand
from apps.entries.domain.exceptions import InvalidContainerCode
from apps.entries.domain.value_objects import ContainerCode
from apps.questionnaire.domain.entities import Question, Questionnaire, QuestionType
from apps.questionnaire.domain.visibility import VisibilityRule


@dataclass
class ChoiceVM:
    label: str
    value: str
    selected: bool = False


@dataclass
class FieldVM:
    """View-model (infraestructura): una pregunta lista para pintarse."""

    id: int
    type: str
    text: str
    help_text: str
    required: bool
    name: str
    photo_name: str
    value: str = ""
    error: str = ""
    hidden: bool = False
    depends_on_id: int | None = None
    depends_on_value: str = ""
    choices: list[ChoiceVM] = field(default_factory=list)
    ocr_kind: str = ""
    ocr_url: str = ""
    show_confirm: bool = False
    confirm_checked: bool = False
    bool_yes: bool = False
    bool_no: bool = False


def _raw_for_visibility(question: Question, post) -> Any:
    name = f"q_{question.id}"
    if question.type is QuestionType.MULTI_CHOICE:
        return post.getlist(name)
    value = (post.get(name) or "").strip()
    if question.type is QuestionType.BOOLEAN:
        return True if value.lower() == "true" else False if value.lower() == "false" else None
    return value or None


def build_field_viewmodels(questionnaire: Questionnaire, post=None, errors: dict | None = None) -> list[FieldVM]:
    post = post if post is not None else QueryDict()
    errors = errors or {}
    getlist, get = post.getlist, post.get

    raw = {q.id: _raw_for_visibility(q, post) for q in questionnaire.questions}
    visible_ids = {q.id for q in VisibilityRule.visible_questions(questionnaire.questions, raw)}
    confirm_posted = bool(get("confirm_iso"))

    vms: list[FieldVM] = []
    for q in questionnaire.questions:
        name = f"q_{q.id}"
        vm = FieldVM(
            id=q.id, type=q.type.value, text=q.text, help_text=q.help_text, required=q.is_required,
            name=name, photo_name=f"photo_{q.id}", error=errors.get(q.id, ""),
            hidden=q.id not in visible_ids, depends_on_id=q.depends_on_id, depends_on_value=q.depends_on_value,
        )
        if q.type is QuestionType.MULTI_CHOICE:
            selected = set(getlist(name))
            vm.choices = [ChoiceVM(c.label, c.value, c.value in selected) for c in q.choices]
        elif q.type is QuestionType.SINGLE_CHOICE:
            current = (get(name) or "").strip()
            vm.value = current
            vm.choices = [ChoiceVM(c.label, c.value, c.value == current) for c in q.choices]
        else:
            vm.value = (get(name) or "").strip()
        if q.type is QuestionType.BOOLEAN:
            vm.bool_yes = vm.value.lower() == "true"
            vm.bool_no = vm.value.lower() == "false"
        if q.type.is_ocr:
            vm.ocr_kind = "plate" if q.type is QuestionType.PLATE_OCR else "container"
            vm.ocr_url = reverse("entries:ocr_plate" if vm.ocr_kind == "plate" else "entries:ocr_container")
        if q.type is QuestionType.CONTAINER_OCR and vm.value:
            try:
                ContainerCode.from_raw(vm.value)
            except InvalidContainerCode as exc:
                vm.show_confirm = exc.reason == "check_digit"
        vm.confirm_checked = confirm_posted
        vms.append(vm)
    return vms


def parse_entry_command(post, files, questionnaire: Questionnaire, user_id: int) -> RegisterEntryCommand:
    """Convierte el POST + FILES del formulario en el comando del caso de uso."""
    answers: dict[int, Any] = {}
    evidences: list[EvidenceUpload] = []
    for q in questionnaire.questions:
        name = f"q_{q.id}"
        answers[q.id] = post.getlist(name) if q.type is QuestionType.MULTI_CHOICE else post.get(name)
        if q.type.has_photo_input:
            upload = files.get(f"photo_{q.id}")
            if upload is not None and upload.size:
                evidences.append(EvidenceUpload(q.id, upload.name or "foto.jpg", upload.read()))
    return RegisterEntryCommand(
        user_id=user_id, answers=answers, evidences=evidences, confirm_iso_override=bool(post.get("confirm_iso"))
    )


def parse_filters(get) -> tuple[EntryFilters, dict]:
    """Convierte los parámetros GET del histórico en filtros y valores crudos para el formulario."""

    def as_date(value: str) -> date | None:
        try:
            return date.fromisoformat(value) if value else None
        except ValueError:
            return None

    raw = {k: (get.get(k) or "").strip() for k in ("date_from", "date_to", "plate", "container", "status", "novelty", "user")}
    user_id = int(raw["user"]) if raw["user"].isdigit() else None
    filters = EntryFilters(
        date_from=as_date(raw["date_from"]), date_to=as_date(raw["date_to"]), plate=raw["plate"],
        container=raw["container"], status=raw["status"], novelty=raw["novelty"], user_id=user_id,
    )
    return filters, raw
