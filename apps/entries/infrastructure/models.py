"""Infraestructura (entries): modelos ORM. Los repositorios mapean ORM ↔ entidad de dominio."""
from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel
from apps.entries.domain.entities import EntryStatus


class TruckEntry(TimeStampedModel):
    STATUS_CHOICES = [(s.value, s.value.replace("_", " ").capitalize()) for s in EntryStatus]

    questionnaire = models.ForeignKey("questionnaire.Questionnaire", on_delete=models.PROTECT, related_name="entries")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="truck_entries")
    plate = models.CharField(max_length=10, db_index=True)
    container_code = models.CharField(max_length=11, blank=True, db_index=True)
    container_iso_valid = models.BooleanField(default=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=EntryStatus.REGISTERED.value, db_index=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="reviewed_entries"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_comment = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "ingreso"

    def __str__(self) -> str:
        return f"#{self.pk} {self.plate}"


class Answer(models.Model):
    entry = models.ForeignKey(TruckEntry, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey("questionnaire.Question", on_delete=models.PROTECT, related_name="answers")
    value_text = models.TextField(blank=True)
    value_number = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    value_bool = models.BooleanField(null=True, blank=True)
    choices = models.ManyToManyField("questionnaire.Choice", blank=True, related_name="answers")
    meta = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["question__order"]

    def __str__(self) -> str:
        return f"{self.question_id}: {self.value_text or self.value_number or self.value_bool}"


class Evidence(models.Model):
    entry = models.ForeignKey(TruckEntry, on_delete=models.CASCADE, related_name="evidences")
    question = models.ForeignKey("questionnaire.Question", null=True, blank=True, on_delete=models.SET_NULL, related_name="evidences")
    kind = models.CharField(max_length=20, default="photo")
    image = models.ImageField(upload_to="evidences/")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
