"""Dominio (entries): excepciones de negocio."""
from shared.domain.base import DomainError


class InvalidPlate(DomainError):
    """La placa no cumple el formato colombiano."""


class InvalidContainerCode(DomainError):
    """El código de contenedor no es válido.

    `reason` distingue "format" (formato inválido) de "check_digit" (dígito de control incorrecto).
    """

    def __init__(self, message: str, reason: str = "format", expected_check_digit: int | None = None):
        super().__init__(message)
        self.reason = reason
        self.expected_check_digit = expected_check_digit


class OcrUnavailable(DomainError):
    """El servicio de OCR no está disponible (red, credenciales o cuota)."""


class EntryValidationError(DomainError):
    """El formulario de ingreso tiene errores. `errors` va por id de pregunta (o `__all__`)."""

    def __init__(self, errors: dict):
        super().__init__("El ingreso tiene errores de validación.")
        self.errors = errors


class EntryNotFound(DomainError):
    """El ingreso no existe o el usuario no puede verlo."""


class EntryAlreadyReviewed(DomainError):
    """El ingreso ya fue revisado."""


class PermissionDeniedForAction(DomainError):
    """El rol del usuario no permite esta acción."""
