"""Infraestructura (questionnaire): el administrador edita el cuestionario sin tocar código."""
from django.contrib import admin

from apps.questionnaire.infrastructure.models import Choice, Question, Questionnaire


class ChoiceInline(admin.TabularInline):
    model = Choice
    extra = 1


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("order", "text", "type", "is_required", "semantic_tag", "depends_on", "is_active")
    list_display_links = ("text",)
    list_filter = ("questionnaire", "type", "is_active", "is_required")
    search_fields = ("text", "semantic_tag")
    inlines = [ChoiceInline]


class QuestionInline(admin.TabularInline):
    model = Question
    extra = 0
    fields = ("order", "text", "type", "is_required", "semantic_tag", "is_active")
    show_change_link = True
    fk_name = "questionnaire"


@admin.register(Questionnaire)
class QuestionnaireAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "updated_at")
    inlines = [QuestionInline]
