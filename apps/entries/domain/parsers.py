"""Dominio (entries): parsers de texto OCR → placa / contenedor (patrón Template Method)."""
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass

from apps.entries.domain import iso6346
from apps.entries.domain.value_objects import (
    TRAILER_PLATE,
    VEHICLE_PLATE,
    normalize,
)

# Confusiones típicas del OCR, según la posición esperada.
DIGIT_TO_LETTER = {"0": "O", "1": "I", "5": "S", "8": "B", "2": "Z"}  # en posiciones de letra
LETTER_TO_DIGIT = {v: k for k, v in DIGIT_TO_LETTER.items()}  # en posiciones de dígito


@dataclass(frozen=True)
class ParseResult:
    """Resultado de un parser: texto crudo, mejor candidato y si pasó la validación completa."""

    raw_text: str
    candidate: str
    is_valid: bool


class BaseCodeParser(ABC):
    """Dominio: parser base. `parse()` es el método plantilla (normaliza → candidatos → corrige → valida).

    Las subclases solo definen las plantillas de posición, la validación completa y la de formato.
    """

    @abstractmethod
    def templates(self) -> list[str]:
        """Plantillas de posición: 'L' = letra, 'D' = dígito. Todas del mismo largo."""

    @abstractmethod
    def is_valid(self, candidate: str) -> bool:
        """Validación completa (formato + reglas)."""

    @abstractmethod
    def matches_format(self, candidate: str) -> bool:
        """Solo el formato (sirve de respaldo para mostrar «requiere verificación»)."""

    # -- método plantilla ---------------------------------------------------------------
    def parse(self, lines: list[str]) -> ParseResult:
        raw_text = " ".join(line.strip() for line in lines if line.strip())
        sources = self._sources(lines)                                   # 1. normalizar
        fallback = ""
        # Primero líneas que son el código completo (evita falsos positivos dentro de otros textos),
        # luego ventanas parciales; en cada caso, primero sin corregir y después corrigiendo confusiones.
        for whole_line_only in (True, False):
            for apply_corrections in (False, True):                      # 2-3. candidatos y corrección
                for source in sources:
                    for window in self._windows(source, whole_line_only):
                        for candidate in self._candidates(window, apply_corrections):
                            if self.is_valid(candidate):                 # 4. validar
                                return ParseResult(raw_text, candidate, True)
                            if not fallback and self.matches_format(candidate):
                                fallback = candidate
        return ParseResult(raw_text, fallback, False)

    # -- pasos reutilizables ------------------------------------------------------------
    def _sources(self, lines: list[str]) -> list[str]:
        per_line = [normalize(line) for line in lines if normalize(line)]
        joined = normalize("".join(lines))
        return per_line + ([joined] if joined and joined not in per_line else [])

    def _windows(self, text: str, whole_line_only: bool = False):
        size = len(self.templates()[0])
        if whole_line_only:
            if len(text) == size:
                yield text
            return
        for i in range(len(text) - size + 1):
            yield text[i : i + size]

    def _candidates(self, window: str, apply_corrections: bool):
        for template in self.templates():
            corrected = self._fit(window, template, apply_corrections)
            if corrected is not None:
                yield corrected

    @staticmethod
    def _fit(window: str, template: str, apply_corrections: bool) -> str | None:
        out = []
        for char, kind in zip(window, template):
            if kind == "L":
                if char.isalpha():
                    out.append(char)
                elif apply_corrections and char in DIGIT_TO_LETTER:
                    out.append(DIGIT_TO_LETTER[char])
                else:
                    return None
            else:
                if char.isdigit():
                    out.append(char)
                elif apply_corrections and char in LETTER_TO_DIGIT:
                    out.append(LETTER_TO_DIGIT[char])
                else:
                    return None
        return "".join(out)


class PlateParser(BaseCodeParser):
    """Dominio: lee placas colombianas (vehículo ABC123 o remolque R12345)."""

    def templates(self) -> list[str]:
        return ["LLLDDD", "LDDDDD"]

    def matches_format(self, candidate: str) -> bool:
        return bool(VEHICLE_PLATE.match(candidate) or TRAILER_PLATE.match(candidate))

    def is_valid(self, candidate: str) -> bool:
        return self.matches_format(candidate)


class ContainerCodeParser(BaseCodeParser):
    """Dominio: lee códigos de contenedor ISO 6346 (11 caracteres)."""

    CATEGORY = re.compile(r"^[A-Z]{3}[UJZ]")

    def templates(self) -> list[str]:
        return ["LLLLDDDDDDD"]

    def matches_format(self, candidate: str) -> bool:
        return iso6346.has_valid_format(candidate)

    def is_valid(self, candidate: str) -> bool:
        return iso6346.is_valid(candidate)
