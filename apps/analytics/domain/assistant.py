"""Dominio (analytics): conversación con el asistente del tablero."""
from dataclasses import dataclass
from enum import Enum

from shared.domain.base import DomainError


class ChatRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"


@dataclass(frozen=True)
class ChatTurn:
    """Value object (dominio): un mensaje de la conversación."""

    role: ChatRole
    text: str


class AssistantUnavailable(DomainError):
    """El asistente no pudo responder (red, cuota, respuesta vacía…). Activa el respaldo por reglas."""


class InvalidQuestion(DomainError):
    """La pregunta está vacía o supera el límite permitido."""
