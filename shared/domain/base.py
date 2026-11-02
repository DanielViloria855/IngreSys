"""Dominio compartido: clases base de la jerarquía POO (Entity, ValueObject, DomainError)."""
from abc import ABC, abstractmethod


class DomainError(Exception):
    """Dominio: base de todas las excepciones de negocio."""


class Entity(ABC):
    """Dominio: base de las entidades. Se identifican por `id`, no por el valor de sus atributos."""

    id: int | None = None

    def __eq__(self, other: object) -> bool:
        if self is other:
            return True
        if type(self) is not type(other):
            return False
        return self.id is not None and self.id == other.id  # type: ignore[attr-defined]

    def __hash__(self) -> int:
        return hash((type(self).__name__, self.id)) if self.id is not None else id(self)


class ValueObject(ABC):
    """Dominio: base de los value objects. Inmutables (dataclass frozen), iguales por valor.

    Las subclases se declaran con `@dataclass(frozen=True)` y validan en `_validate`.
    """

    def __post_init__(self) -> None:
        self._validate()

    @abstractmethod
    def _validate(self) -> None:
        """Lanza una DomainError si el valor no cumple la regla."""
