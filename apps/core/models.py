"""Infraestructura: modelo base abstracto con marcas de tiempo."""
from django.db import models


class TimeStampedModel(models.Model):
    """Infraestructura: modelo abstracto con `created_at` / `updated_at`; los demás heredan de él."""

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
