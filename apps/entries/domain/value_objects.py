"""Dominio (entries): value objects Plate y ContainerCode."""
import re
from dataclasses import dataclass

from apps.entries.domain import iso6346
from apps.entries.domain.exceptions import InvalidContainerCode, InvalidPlate
from shared.domain.base import ValueObject

VEHICLE_PLATE = re.compile(r"^[A-Z]{3}\d{3}$")  # ABC123
TRAILER_PLATE = re.compile(r"^[RS]\d{5}$")  # R12345


def normalize(raw: str) -> str:
    """Mayúsculas y sin espacios, guiones ni puntos."""
    return re.sub(r"[\s\-.]", "", (raw or "").upper())


@dataclass(frozen=True)
class Plate(ValueObject):
    """Value object (dominio): placa colombiana de vehículo (ABC123) o remolque (R12345)."""

    value: str

    @classmethod
    def from_raw(cls, raw: str) -> "Plate":
        return cls(normalize(raw))

    def _validate(self) -> None:
        if not (VEHICLE_PLATE.match(self.value) or TRAILER_PLATE.match(self.value)):
            raise InvalidPlate(f"Placa inválida: «{self.value}». Usa ABC123 (vehículo) o R12345 (remolque).")

    @property
    def kind(self) -> str:
        return "vehicle" if VEHICLE_PLATE.match(self.value) else "trailer"

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class ContainerCode(ValueObject):
    """Value object (dominio): código de contenedor ISO 6346 (3 letras + U/J/Z + 6 dígitos + control)."""

    value: str

    @classmethod
    def from_raw(cls, raw: str) -> "ContainerCode":
        return cls(normalize(raw))

    def _validate(self) -> None:
        if not iso6346.has_valid_format(self.value):
            raise InvalidContainerCode(
                f"Formato inválido: «{self.value}». Debe ser 3 letras + U/J/Z + 7 dígitos (p. ej. CSQU3054383).",
                reason="format",
            )
        expected = iso6346.compute_check_digit(self.value[:10])
        if int(self.value[10]) != expected:
            raise InvalidContainerCode(
                f"Dígito de control incorrecto (esperado {expected}).",
                reason="check_digit",
                expected_check_digit=expected,
            )

    @property
    def check_digit(self) -> int:
        return int(self.value[10])

    def __str__(self) -> str:
        return self.value
