"""Infraestructura (adaptadores primarios) de entries: vistas delgadas.

Cada vista lee el request, toma el caso de uso de `container.py`, lo ejecuta y renderiza.
"""
import csv
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View

from apps.core.mixins import RoleRequiredMixin
from apps.core.roles import build_actor
from apps.entries.application.dtos import GetEntryDetailQuery, ListEntriesQuery, ReviewEntryCommand
from apps.entries.domain.exceptions import (
    EntryAlreadyReviewed,
    EntryNotFound,
    EntryValidationError,
    OcrUnavailable,
)
from apps.entries.infrastructure import container
from apps.entries.infrastructure.forms import build_field_viewmodels, parse_entry_command, parse_filters
from apps.questionnaire.application.use_cases import NoActiveQuestionnaire
from apps.questionnaire.infrastructure.container import get_active_questionnaire_use_case
from shared.domain.roles import Role

ALL_ROLES = (Role.ADMIN, Role.SUPERVISOR, Role.OPERATOR)
PRIVILEGED = (Role.ADMIN, Role.SUPERVISOR)
STATUS_OPTIONS = [("", "Todos"), ("registrado", "Registrado"), ("con_observacion", "Con observación"), ("revisado", "Revisado")]
NOVELTY_OPTIONS = [("", "Todas"), ("yes", "Con novedad"), ("no", "Sin novedad")]


class EntryCreateView(LoginRequiredMixin, RoleRequiredMixin, View):
    """Nuevo ingreso: arma el formulario dinámico y registra."""

    allowed_roles = ALL_ROLES
    template_name = "pages/entries/create.html"

    def _questionnaire(self):
        return get_active_questionnaire_use_case().execute()

    def get(self, request):
        try:
            questionnaire = self._questionnaire()
        except NoActiveQuestionnaire as exc:
            return render(request, self.template_name, {"fields": [], "setup_error": str(exc)})
        return render(request, self.template_name, {"fields": build_field_viewmodels(questionnaire), "questionnaire": questionnaire})

    def post(self, request):
        try:
            questionnaire = self._questionnaire()
        except NoActiveQuestionnaire as exc:
            return render(request, self.template_name, {"fields": [], "setup_error": str(exc)})
        command = parse_entry_command(request.POST, request.FILES, questionnaire, request.user.id)
        try:
            entry_id = container.register_truck_entry().execute(command)
        except EntryValidationError as exc:
            general = exc.errors.get("__all__", "")
            fields = build_field_viewmodels(questionnaire, request.POST, exc.errors)
            context = {
                "fields": fields,
                "questionnaire": questionnaire,
                "error_count": len([k for k in exc.errors if k != "__all__"]),
                "general_error": general,
                "lost_photos": any(f.error for f in fields) and bool(request.FILES),
            }
            return render(request, self.template_name, context, status=422)
        messages.success(request, "Ingreso registrado correctamente.")
        return redirect("entries:detail", pk=entry_id)


class EntryListView(LoginRequiredMixin, RoleRequiredMixin, View):
    """Histórico con filtros y paginación."""

    allowed_roles = ALL_ROLES

    def get(self, request):
        actor = build_actor(request.user)
        filters, raw = parse_filters(request.GET)
        try:
            page_number = max(int(request.GET.get("page", 1)), 1)
        except ValueError:
            page_number = 1
        page = container.list_entries().execute(ListEntriesQuery(filters, actor, page_number))
        query = {k: v for k, v in raw.items() if v}
        user_options = [("", "Todos")]
        if actor.can_see_all:
            user_options += [(str(u.id), u.get_full_name() or u.username) for u in User.objects.order_by("first_name", "username")]
        querystring = urlencode(query)
        context = {
            "page": page,
            "filters": raw,
            "status_options": STATUS_OPTIONS,
            "novelty_options": NOVELTY_OPTIONS,
            "user_options": user_options,
            "can_filter_users": actor.can_see_all,
            "querystring": querystring,
            "export_href": f"{reverse('entries:export')}?{querystring}" if querystring else reverse("entries:export"),
            "has_filters": bool(query),
        }
        return render(request, "pages/entries/list.html", context)


class EntryExportCsvView(LoginRequiredMixin, RoleRequiredMixin, View):
    """Exporta a CSV lo filtrado (supervisor/admin)."""

    allowed_roles = PRIVILEGED

    def get(self, request):
        actor = build_actor(request.user)
        filters, _ = parse_filters(request.GET)
        page = container.list_entries().execute(ListEntriesQuery(filters, actor, 1, 100000))
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="ingresos.csv"'
        response.write("﻿")  # BOM para que Excel respete las tildes
        writer = csv.writer(response)
        writer.writerow(["ID", "Fecha", "Placa", "Contenedor", "ISO válido", "Proveedor", "Registrado por", "Estado", "Novedad"])
        for e in page.items:
            writer.writerow([
                e.id, timezone.localtime(e.created_at).strftime("%Y-%m-%d %H:%M"), e.plate, e.container_code,
                "" if e.container_iso_valid is None else ("Sí" if e.container_iso_valid else "No"),
                e.supplier, e.created_by_name, e.status_label,
                "" if e.has_novelty is None else ("Sí" if e.has_novelty else "No"),
            ])
        return response


class EntryDetailView(LoginRequiredMixin, RoleRequiredMixin, View):
    allowed_roles = ALL_ROLES

    def get(self, request, pk: int):
        actor = build_actor(request.user)
        try:
            detail = container.get_entry_detail().execute(GetEntryDetailQuery(pk, actor))
        except EntryNotFound as exc:
            raise Http404(str(exc)) from exc
        return render(request, "pages/entries/detail.html", {"entry": detail})


class EntryReviewView(LoginRequiredMixin, RoleRequiredMixin, View):
    """Marca un ingreso como revisado (solo POST, supervisor/admin)."""

    allowed_roles = PRIVILEGED

    def post(self, request, pk: int):
        actor = build_actor(request.user)
        try:
            container.review_entry().execute(ReviewEntryCommand(pk, actor, request.POST.get("comment", "")))
            messages.success(request, "Ingreso marcado como revisado.")
        except EntryNotFound as exc:
            raise Http404(str(exc)) from exc
        except EntryAlreadyReviewed as exc:
            messages.warning(request, str(exc))
        return redirect("entries:detail", pk=pk)


class _OcrView(LoginRequiredMixin, RoleRequiredMixin, View):
    """Base de los endpoints JSON de OCR (recibe `image`, responde JSON)."""

    allowed_roles = ALL_ROLES

    def post(self, request):
        upload = request.FILES.get("image")
        if upload is None or not upload.size:
            return JsonResponse({"error": "Adjunta una foto."}, status=400)
        try:
            return JsonResponse(self.read(upload.read()))
        except OcrUnavailable as exc:
            return JsonResponse({"error": str(exc)}, status=503)

    def read(self, image_bytes: bytes) -> dict:  # pragma: no cover - lo implementan las subclases
        raise NotImplementedError


class OcrPlateView(_OcrView):
    def read(self, image_bytes: bytes) -> dict:
        result = container.read_plate_with_ai().execute(image_bytes)
        return {
            "raw_text": result.raw_text,
            "candidate": result.candidate,
            "is_valid": result.is_valid,
            "status": "valid" if result.is_valid else "verify",
        }


class OcrContainerView(_OcrView):
    def read(self, image_bytes: bytes) -> dict:
        result = container.read_container_with_ai().execute(image_bytes)
        status = "valid" if result.is_valid else ("invalid" if result.candidate else "verify")
        return {
            "raw_text": result.raw_text,
            "candidate": result.candidate,
            "is_valid": result.is_valid,
            "expected_check_digit": result.expected_check_digit,
            "status": status,
        }
