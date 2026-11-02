"""Infraestructura (entries): adaptador secundario con el ORM de Django."""
from decimal import Decimal

from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import BooleanField, OuterRef, Subquery

from apps.entries.application.dtos import (
    STATUS_META,
    AnswerDisplayDTO,
    AnswerValue,
    EntryDetailDTO,
    EntryFilters,
    EntrySummaryDTO,
    EvidenceDTO,
)
from apps.entries.application.ports import TruckEntryRepository
from apps.entries.domain import iso6346
from apps.entries.domain.entities import EntryStatus, TruckEntry
from apps.entries.infrastructure.models import Answer, Evidence
from apps.entries.infrastructure.models import TruckEntry as TruckEntryModel
from shared.application.pagination import Page

KIND_LABELS = {"plate": "Placa", "container": "Contenedor", "novelty": "Novedad", "photo": "Foto"}
HIDDEN_IN_DETAIL = {"plate", "container_code"}  # ya se muestran en el encabezado


def _user_name(user) -> str:
    return (user.get_full_name() or user.get_username()) if user else ""


def _format_number(value: Decimal) -> str:
    return f"{value.normalize():f}"


class DjangoTruckEntryRepository(TruckEntryRepository):
    """Adaptador secundario (infraestructura): implementa el puerto TruckEntryRepository con el ORM."""

    @transaction.atomic
    def save(self, entry: TruckEntry, answers: list[AnswerValue]) -> int:
        model = TruckEntryModel.objects.create(
            questionnaire_id=entry.questionnaire_id,
            created_by_id=entry.created_by_id,
            plate=entry.plate,
            container_code=entry.container_code,
            container_iso_valid=entry.container_iso_valid,
            status=entry.status.value,
        )
        for value in answers:
            answer = Answer.objects.create(
                entry=model,
                question_id=value.question_id,
                value_text=value.value_text,
                value_number=value.value_number,
                value_bool=value.value_bool,
                meta=dict(value.meta),
            )
            if value.choice_ids:
                answer.choices.set(value.choice_ids)
        return model.id

    def add_evidence(self, entry_id: int, question_id: int | None, kind: str, stored_path: str) -> None:
        Evidence.objects.create(entry_id=entry_id, question_id=question_id, kind=kind, image=stored_path)

    def get(self, entry_id: int) -> TruckEntry | None:
        model = TruckEntryModel.objects.filter(pk=entry_id).first()
        if model is None:
            return None
        return TruckEntry(
            id=model.id,
            questionnaire_id=model.questionnaire_id,
            created_by_id=model.created_by_id,
            created_at=model.created_at,
            plate=model.plate,
            container_code=model.container_code,
            container_iso_valid=model.container_iso_valid,
            status=EntryStatus(model.status),
            reviewed_by_id=model.reviewed_by_id,
            reviewed_at=model.reviewed_at,
            review_comment=model.review_comment,
        )

    def get_detail(self, entry_id: int) -> EntryDetailDTO | None:
        model = TruckEntryModel.objects.select_related("created_by", "reviewed_by").filter(pk=entry_id).first()
        if model is None:
            return None
        answers = [
            AnswerDisplayDTO(
                question_text=a.question.text,
                display_value=a.value_text or (_format_number(a.value_number) if a.value_number is not None else "—"),
                semantic_tag=a.question.semantic_tag,
            )
            for a in model.answers.select_related("question").order_by("question__order")
            if a.question.semantic_tag not in HIDDEN_IN_DETAIL
        ]
        evidences = [
            EvidenceDTO(
                url=e.image.url,
                kind=e.kind,
                kind_label=KIND_LABELS.get(e.kind, "Foto"),
                question_text=e.question.text if e.question else "",
            )
            for e in model.evidences.select_related("question")
        ]
        has_container = bool(model.container_code)
        read_digit = int(model.container_code[10]) if has_container and len(model.container_code) == 11 and model.container_code[10].isdigit() else None
        expected = (
            iso6346.compute_check_digit(model.container_code[:10])
            if has_container and iso6346.has_valid_format(model.container_code)
            else None
        )
        label, variant = STATUS_META[model.status]
        return EntryDetailDTO(
            id=model.id,
            created_at=model.created_at,
            created_by_id=model.created_by_id,
            created_by_name=_user_name(model.created_by),
            plate=model.plate,
            container_code=model.container_code,
            container_iso_valid=model.container_iso_valid if has_container else None,
            iso_read_digit=read_digit,
            iso_expected_digit=expected,
            status=model.status,
            status_label=label,
            status_variant=variant,
            answers=answers,
            evidences=evidences,
            reviewed_by_name=_user_name(model.reviewed_by),
            reviewed_at=model.reviewed_at,
            review_comment=model.review_comment,
        )

    def list(self, filters: EntryFilters, page: int, page_size: int) -> Page[EntrySummaryDTO]:
        supplier = Answer.objects.filter(entry=OuterRef("pk"), question__semantic_tag="supplier").values("value_text")[:1]
        novelty = Answer.objects.filter(entry=OuterRef("pk"), question__semantic_tag="has_novelty").values("value_bool")[:1]
        qs = TruckEntryModel.objects.select_related("created_by").annotate(
            supplier_name=Subquery(supplier),
            novelty_flag=Subquery(novelty, output_field=BooleanField()),
        )
        if filters.date_from:
            qs = qs.filter(created_at__date__gte=filters.date_from)
        if filters.date_to:
            qs = qs.filter(created_at__date__lte=filters.date_to)
        if filters.plate:
            qs = qs.filter(plate__icontains=filters.plate.upper().replace(" ", "").replace("-", ""))
        if filters.container:
            qs = qs.filter(container_code__icontains=filters.container.upper().replace(" ", "").replace("-", ""))
        if filters.status:
            qs = qs.filter(status=filters.status)
        if filters.user_id:
            qs = qs.filter(created_by_id=filters.user_id)
        if filters.novelty == "yes":
            qs = qs.filter(novelty_flag=True)
        elif filters.novelty == "no":
            qs = qs.exclude(novelty_flag=True)

        paginator = Paginator(qs.order_by("-created_at", "-id"), page_size)
        current = paginator.get_page(page)
        items = []
        for m in current.object_list:
            label, variant = STATUS_META[m.status]
            items.append(
                EntrySummaryDTO(
                    id=m.id,
                    created_at=m.created_at,
                    plate=m.plate,
                    container_code=m.container_code,
                    container_iso_valid=m.container_iso_valid if m.container_code else None,
                    supplier=m.supplier_name or "—",
                    created_by_name=_user_name(m.created_by),
                    status=m.status,
                    status_label=label,
                    status_variant=variant,
                    has_novelty=m.novelty_flag,
                )
            )
        # los puntos suspensivos se representan con None para que la plantilla no dependa del idioma
        page_range = [p if isinstance(p, int) else None for p in paginator.get_elided_page_range(current.number, on_each_side=1, on_ends=1)]
        return Page(items=items, number=current.number, num_pages=paginator.num_pages, total=paginator.count,
                    page_size=page_size, page_range=page_range)

    def save_review(self, entry: TruckEntry) -> None:
        TruckEntryModel.objects.filter(pk=entry.id).update(
            status=entry.status.value,
            reviewed_by_id=entry.reviewed_by_id,
            reviewed_at=entry.reviewed_at,
            review_comment=entry.review_comment,
        )
