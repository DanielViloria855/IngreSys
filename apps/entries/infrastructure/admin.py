"""Infraestructura (entries): administración de ingresos (solo lectura de respuestas)."""
from django.contrib import admin

from apps.entries.infrastructure.models import Answer, Evidence, TruckEntry


class AnswerInline(admin.TabularInline):
    model = Answer
    extra = 0
    readonly_fields = ("question", "value_text", "value_number", "value_bool", "meta")
    can_delete = False


class EvidenceInline(admin.TabularInline):
    model = Evidence
    extra = 0
    readonly_fields = ("question", "kind", "image")
    can_delete = False


@admin.register(TruckEntry)
class TruckEntryAdmin(admin.ModelAdmin):
    list_display = ("id", "plate", "container_code", "container_iso_valid", "status", "created_by", "created_at")
    list_filter = ("status", "container_iso_valid")
    search_fields = ("plate", "container_code")
    inlines = [AnswerInline, EvidenceInline]
