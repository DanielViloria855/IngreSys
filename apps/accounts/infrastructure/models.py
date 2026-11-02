"""Infraestructura: perfil de personal (1:1 con User; no se crea un User personalizado)."""
from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel


class Profile(TimeStampedModel):
    """Datos del empleado que Django no trae: documento, cargo y teléfono."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    document_id = models.CharField("Documento", max_length=20, blank=True)
    position = models.CharField("Cargo", max_length=80, blank=True)
    phone = models.CharField("Teléfono", max_length=20, blank=True)

    class Meta:
        verbose_name = "perfil"

    def __str__(self) -> str:
        return f"Perfil de {self.user}"
