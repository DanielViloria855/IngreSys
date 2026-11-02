"""Dominio (analytics): rango de fechas del tablero."""
from dataclasses import dataclass
from datetime import date, timedelta

from shared.domain.base import DomainError, ValueObject

PRESETS = {"today": "Hoy", "7d": "Últimos 7 días", "30d": "Últimos 30 días", "custom": "Rango personalizado"}
MAX_DAYS = 366


class InvalidDateRange(DomainError):
    """El rango de fechas no es válido."""


@dataclass(frozen=True)
class DateRange(ValueObject):
    """Value object (dominio): rango de fechas inclusivo."""

    start: date
    end: date

    def _validate(self) -> None:
        if self.start > self.end:
            raise InvalidDateRange("La fecha inicial no puede ser posterior a la final.")
        if self.days > MAX_DAYS:
            raise InvalidDateRange(f"El rango no puede superar {MAX_DAYS} días.")

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    @property
    def key(self) -> str:
        return f"{self.start.isoformat()}_{self.end.isoformat()}"

    def previous(self) -> "DateRange":
        """Periodo inmediatamente anterior de la misma duración."""
        end = self.start - timedelta(days=1)
        return DateRange(end - timedelta(days=self.days - 1), end)

    def each_day(self):
        for offset in range(self.days):
            yield self.start + timedelta(days=offset)

    @classmethod
    def from_preset(cls, preset: str, today: date, start: str = "", end: str = "") -> "DateRange":
        if preset == "7d":
            return cls(today - timedelta(days=6), today)
        if preset == "30d":
            return cls(today - timedelta(days=29), today)
        if preset == "custom":
            try:
                return cls(date.fromisoformat(start), date.fromisoformat(end))
            except ValueError as exc:
                raise InvalidDateRange("Fechas inválidas para el rango personalizado.") from exc
        return cls(today, today)
