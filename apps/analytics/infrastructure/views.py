"""Infraestructura (adaptadores primarios) de analytics: tablero y endpoints JSON."""
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views import View

from apps.analytics.application.dtos import DashboardMetricsDTO
from apps.analytics.domain.metrics import PRESETS, DateRange, InvalidDateRange
from apps.analytics.infrastructure import container
from apps.core.mixins import RoleRequiredMixin
from shared.domain.roles import Role


class AnalyticsAccessMixin(LoginRequiredMixin, RoleRequiredMixin):
    allowed_roles = (Role.ADMIN, Role.SUPERVISOR)


def _parse_range(params) -> tuple[str, DateRange, str]:
    """Lee preset/fechas del request. Si son inválidas cae a «hoy» y devuelve el mensaje de error."""
    preset = params.get("range", "today")
    if preset not in PRESETS:
        preset = "today"
    today = timezone.localdate()
    try:
        return preset, DateRange.from_preset(preset, today, params.get("start", ""), params.get("end", "")), ""
    except InvalidDateRange as exc:
        return "today", DateRange(today, today), str(exc)


def _fmt_delta(value: float | None) -> tuple[str, str]:
    if value is None:
        return "", "none"
    if abs(value) < 0.5:
        return "= 0 %", "flat"
    return f"{value:+.0f} %".replace("+", "+ ").replace("-", "− "), "up" if value > 0 else "down"


def build_kpis(m: DashboardMetricsDTO) -> list[dict]:
    """Tarjetas KPI listas para mostrar (el template no calcula nada)."""

    def card(icon, title, value, key=None, tone="default", hint="", bad_when_up=False):
        delta_text, direction = _fmt_delta(m.deltas.get(key)) if key else ("", "none")
        delta_tone = "neutral"
        if bad_when_up and direction == "up":
            delta_tone = "bad"
        elif bad_when_up and direction == "down":
            delta_tone = "good"
        return {"icon": icon, "title": title, "value": value, "tone": tone, "hint": hint,
                "delta": delta_text, "delta_dir": direction, "delta_tone": delta_tone}

    iso_value = "—" if m.iso_valid_pct is None else f"{m.iso_valid_pct:.0f} %"
    iso_tone = "default" if m.iso_valid_pct is None or m.iso_valid_pct >= 90 else "danger"
    return [
        card("truck-front", "Camiones ingresados", f"{m.trucks:,}".replace(",", "."), "trucks"),
        card("box-seam", "Total de cajas", f"{m.boxes:,}".replace(",", "."), "boxes"),
        card("boxes", "Total de estibas", f"{m.pallets:,}".replace(",", "."), "pallets"),
        card("eyedropper", "Muestras testigo", f"{m.witness_samples:,}".replace(",", "."), "witness_samples"),
        card("exclamation-triangle", "Ingresos con novedad", m.novelty_entries, "novelty_entries",
             tone="warning" if m.novelty_entries else "default", bad_when_up=True,
             hint=f"{m.novelty_entries / m.trucks * 100:.0f} % de los ingresos" if m.trucks else ""),
        card("shield-check", "Contenedores ISO válidos", iso_value, tone=iso_tone,
             hint=f"{m.containers_iso_valid} de {m.containers_total} contenedores" if m.containers_total else "Sin contenedores"),
        card("unlock", "Sellos no intactos", m.seals_not_ok, tone="danger" if m.seals_not_ok else "default",
             hint="Requiere inspección" if m.seals_not_ok else "Todo en orden"),
        card("hourglass-split", "Pendientes de revisión", m.pending_review, tone="warning" if m.pending_review else "default",
             hint="Estado distinto de «revisado»"),
    ]


class DashboardView(AnalyticsAccessMixin, View):
    def get(self, request):
        preset, date_range, error = _parse_range(request.GET)
        if error:
            messages.warning(request, error)
        metrics = container.get_dashboard_metrics().execute(date_range)
        query = {"range": preset}
        if preset == "custom":
            query.update(start=date_range.start.isoformat(), end=date_range.end.isoformat())
        context = {
            "metrics": metrics,
            "kpis": build_kpis(metrics),
            "presets": [(key, label) for key, label in PRESETS.items()],
            "preset": preset,
            "start": date_range.start.isoformat(),
            "end": date_range.end.isoformat(),
            "metrics_url": f"{reverse('analytics:metrics')}?{urlencode(query)}",
            "insights_url": reverse("analytics:insights"),
            "insights_query": urlencode(query),
            "insight_mode": "IA (Groq)" if container.get_insight_generator().model_name.startswith("Groq") else "reglas automáticas",
        }
        return render(request, "pages/analytics/dashboard.html", context)


class MetricsJsonView(AnalyticsAccessMixin, View):
    def get(self, request):
        _, date_range, error = _parse_range(request.GET)
        if error:
            return JsonResponse({"error": error}, status=400)
        return JsonResponse(container.get_dashboard_metrics().execute(date_range).to_dict())


class InsightsView(AnalyticsAccessMixin, View):
    """POST: interpreta las métricas del rango con IA (con caché y respaldo por reglas)."""

    def post(self, request):
        _, date_range, error = _parse_range(request.POST)
        if error:
            return JsonResponse({"error": error}, status=400)
        metrics = container.get_dashboard_metrics().execute(date_range)
        result = container.generate_ai_insights().execute(metrics)
        return JsonResponse(result.to_dict())
