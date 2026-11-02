"""Infraestructura (analytics): caché de insights de IA."""
from django.db import models


class AIInsightCache(models.Model):
    """Guarda el análisis por rango y hash de métricas, para no gastar cuota del LLM en cada clic."""

    range_key = models.CharField(max_length=40, db_index=True)
    metrics_hash = models.CharField(max_length=64)
    payload = models.JSONField(default=list)
    model_used = models.CharField(max_length=120)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["range_key", "metrics_hash"], name="uniq_insight_range_hash")]
        verbose_name = "caché de insight"

    def __str__(self) -> str:
        return f"{self.range_key} · {self.model_used}"
