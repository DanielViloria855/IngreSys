"""Aplicación compartida: página de resultados genérica."""
from dataclasses import dataclass, field
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class Page(Generic[T]):
    """DTO (aplicación): una página de resultados."""

    items: list[T]
    number: int
    num_pages: int
    total: int
    page_size: int = 20
    page_range: list[int | None] = field(default_factory=list)

    @property
    def has_prev(self) -> bool:
        return self.number > 1

    @property
    def has_next(self) -> bool:
        return self.number < self.num_pages
