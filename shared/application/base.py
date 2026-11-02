"""Aplicación compartida: base de los casos de uso."""
from abc import ABC, abstractmethod
from typing import Generic, TypeVar

TInput = TypeVar("TInput")
TOutput = TypeVar("TOutput")


class BaseUseCase(ABC, Generic[TInput, TOutput]):
    """Caso de uso (aplicación): una acción del usuario. Orquesta dominio + puertos."""

    @abstractmethod
    def execute(self, data: TInput) -> TOutput:
        """Ejecuta el caso de uso."""
