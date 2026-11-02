"""Dominio (entries): entidad TruckEntry y su estado."""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from apps.entries.domain.exceptions import EntryAlreadyReviewed
from shared.domain.base import Entity


class EntryStatus(str, Enum):
    """Fases del registro: registrado → con_observacion (si aplica) → revisado."""

    REGISTERED = "registrado"
    WITH_OBSERVATION = "con_observacion"
    REVIEWED = "revisado"


@dataclass(eq=False, kw_only=True)
class TruckEntry(Entity):
    """Entidad (dominio): un ingreso de camión."""

    id: int | None = None
    questionnaire_id: int
    created_by_id: int
    created_at: datetime | None = None
    plate: str
    container_code: str = ""
    container_iso_valid: bool = True
    status: EntryStatus = EntryStatus.REGISTERED
    reviewed_by_id: int | None = None
    reviewed_at: datetime | None = None
    review_comment: str = ""

    @classmethod
    def register(
        cls, *, questionnaire_id: int, created_by_id: int, plate: str, container_code: str, container_iso_valid: bool
    ) -> "TruckEntry":
        """Crea un ingreso nuevo. Regla: un ISO inválido se guarda, pero queda «con observación»."""
        status = EntryStatus.REGISTERED if container_iso_valid else EntryStatus.WITH_OBSERVATION
        return cls(
            questionnaire_id=questionnaire_id,
            created_by_id=created_by_id,
            plate=plate,
            container_code=container_code,
            container_iso_valid=container_iso_valid,
            status=status,
        )

    @property
    def had_observation(self) -> bool:
        return not self.container_iso_valid

    def mark_reviewed(self, reviewer_id: int, comment: str, when: datetime) -> None:
        if self.status is EntryStatus.REVIEWED:
            raise EntryAlreadyReviewed("Este ingreso ya fue revisado.")
        self.status = EntryStatus.REVIEWED
        self.reviewed_by_id = reviewer_id
        self.reviewed_at = when
        self.review_comment = comment.strip()
