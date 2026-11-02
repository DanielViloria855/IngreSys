"""Aplicación compartida: quién ejecuta un caso de uso (sin depender de Django)."""
from dataclasses import dataclass

from shared.domain.roles import Role


@dataclass(frozen=True)
class Actor:
    """DTO (aplicación): usuario que ejecuta la acción y su rol."""

    id: int
    display_name: str
    role: Role

    @property
    def can_see_all(self) -> bool:
        return self.role in (Role.ADMIN, Role.SUPERVISOR)

    @property
    def can_review(self) -> bool:
        return self.role in (Role.ADMIN, Role.SUPERVISOR)
