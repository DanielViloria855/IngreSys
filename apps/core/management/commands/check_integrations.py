"""Comprueba las integraciones de IA configuradas en .env (no imprime secretos)."""
import io
import re

from django.conf import settings
from django.core.management.base import BaseCommand
from PIL import Image, ImageDraw, ImageFont

from apps.analytics.application.dtos import ChartPoint, DashboardMetricsDTO
from apps.analytics.domain.insight import InsightUnavailable
from apps.analytics.infrastructure.container import get_insight_generator
from apps.entries.application.use_cases import ReadPlateWithAI
from apps.entries.domain.exceptions import OcrUnavailable
from apps.entries.infrastructure.container import get_ocr_service


def _mask(text: str) -> str:
    """Oculta posibles llaves (Google AIza..., Groq gsk_...) antes de mostrar un mensaje."""
    return re.sub(r"(AIza[\w-]{10,}|gsk_[\w]{10,})", "[llave oculta]", text)


def _sample_image(text: str) -> bytes:
    image = Image.new("RGB", (900, 300), "white")
    try:
        font = ImageFont.truetype("arial.ttf", 160)
    except OSError:
        font = ImageFont.load_default()
    ImageDraw.Draw(image).text((60, 60), text, fill="black", font=font)
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


class Command(BaseCommand):
    help = "Prueba Google Cloud Vision (OCR) y Groq (LLM) con el proveedor elegido en .env."

    def handle(self, *args, **options):
        self.stdout.write(f"OCR_PROVIDER={settings.OCR_PROVIDER} · INSIGHT_PROVIDER={settings.INSIGHT_PROVIDER}")
        import os

        creds = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
        self.stdout.write(
            "Configuración (solo presencia, sin valores): "
            f"GOOGLE_VISION_API_KEY={'definida' if settings.GOOGLE_VISION_API_KEY else 'vacía'} · "
            f"GOOGLE_APPLICATION_CREDENTIALS={'definida' if creds else 'vacía'}"
            f"{' (el archivo existe)' if creds and os.path.isfile(creds) else (' (el archivo NO existe)' if creds else '')} · "
            f"GROQ_API_KEY={'definida' if settings.GROQ_API_KEY else 'vacía'}"
        )
        self._ocr()
        self._llm()

    def _ocr(self):
        if settings.OCR_PROVIDER != "google":
            self.stdout.write(self.style.WARNING("OCR: usando el adaptador falso (OCR_PROVIDER no es 'google')."))
        try:
            result = ReadPlateWithAI(get_ocr_service()).execute(_sample_image("ABC123"))
        except OcrUnavailable as exc:
            self.stdout.write(self.style.ERROR(f"OCR: FALLÓ -> {_mask(str(exc))}"))
            if exc.__cause__ is not None:
                self.stdout.write(f"   Causa: {type(exc.__cause__).__name__}: {_mask(str(exc.__cause__))[:400]}")
            return
        ok = result.candidate == "ABC123"
        style = self.style.SUCCESS if ok else self.style.WARNING
        self.stdout.write(style(f"OCR: respondió. Texto leído de la imagen de prueba: «{result.raw_text}» -> placa «{result.candidate or '—'}»"))

    def _llm(self):
        if settings.INSIGHT_PROVIDER != "groq":
            self.stdout.write(self.style.WARNING("LLM: usando reglas (INSIGHT_PROVIDER no es 'groq')."))
            return
        metrics = DashboardMetricsDTO(
            range_key="check", range_label="Prueba", days=1, trucks=10, boxes=500, pallets=40, witness_samples=6,
            novelty_entries=3, containers_total=4, containers_iso_valid=3, iso_valid_pct=75.0, seals_not_ok=1,
            pending_review=6, by_hour=[ChartPoint(f"{h:02d}h", 2 if h in (8, 9) else 0) for h in range(24)],
        )
        try:
            insights = get_insight_generator().generate(metrics)
        except InsightUnavailable as exc:
            self.stdout.write(self.style.ERROR(f"LLM: FALLÓ -> {_mask(str(exc))}"))
            return
        self.stdout.write(self.style.SUCCESS(f"LLM: respondió con {len(insights)} insight(s):"))
        for item in insights:
            line = f"   [{item.level.value}] {item.title}: {item.message}"
            self.stdout.write(line.encode("cp1252", "replace").decode("cp1252"))
