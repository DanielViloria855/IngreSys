"""Infraestructura (entries): OCR falso para pruebas y demos sin credenciales."""
from apps.entries.application.ports import OcrService

SAMPLES = [
    ["REPUBLICA DE COLOMBIA", "SKX 482", "ANTIOQUIA", "CSQU 305438 3"],
    ["COLOMBIA", "TRK-915", "CUNDINAMARCA", "MSKU 907032 3"],
    ["R 12345", "COLOMBIA", "CSQU 305438 4"],  # contenedor con dígito de control incorrecto (demo ISO inválido)
]


class FakeOcrAdapter(OcrService):
    """Adaptador secundario: devuelve texto fijo. Con `lines` fijas es determinista; sin ellas rota entre ejemplos."""

    def __init__(self, lines: list[str] | None = None):
        self._lines = lines

    def read_text(self, image_bytes: bytes) -> list[str]:
        if self._lines is not None:
            return list(self._lines)
        return list(SAMPLES[sum(image_bytes[:64]) % len(SAMPLES)])
