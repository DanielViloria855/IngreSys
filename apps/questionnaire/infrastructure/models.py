"""Infraestructura (questionnaire): modelos ORM del formulario dinámico."""
from django.db import models

from apps.core.models import TimeStampedModel
from apps.questionnaire.domain.entities import QuestionType


class Questionnaire(TimeStampedModel):
    name = models.CharField("Nombre", max_length=120)
    is_active = models.BooleanField("Activo", default=True)

    class Meta:
        verbose_name = "cuestionario"

    def __str__(self) -> str:
        return self.name


class Question(TimeStampedModel):
    TYPE_CHOICES = [(t.value, t.name.replace("_", " ").title()) for t in QuestionType]

    questionnaire = models.ForeignKey(Questionnaire, on_delete=models.CASCADE, related_name="questions")
    order = models.PositiveIntegerField("Orden", default=0)
    text = models.CharField("Pregunta", max_length=200)
    help_text = models.CharField("Ayuda", max_length=200, blank=True)
    type = models.CharField("Tipo", max_length=20, choices=TYPE_CHOICES)
    is_required = models.BooleanField("Obligatoria", default=False)
    semantic_tag = models.SlugField(
        "Etiqueta semántica",
        max_length=40,
        blank=True,
        help_text="Identificador estable (plate, boxes_count…). El registro y el tablero la usan en vez del texto.",
    )
    is_active = models.BooleanField("Activa", default=True)
    depends_on = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="dependents", verbose_name="Depende de"
    )
    depends_on_value = models.CharField("Valor requerido", max_length=60, blank=True, help_text="p. ej. true, o el valor de una opción")

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "pregunta"

    def __str__(self) -> str:
        return f"{self.order}. {self.text}"


class Choice(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="choices")
    label = models.CharField("Etiqueta", max_length=80)
    value = models.CharField("Valor", max_length=60)
    order = models.PositiveIntegerField("Orden", default=0)

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "opción"

    def __str__(self) -> str:
        return self.label
