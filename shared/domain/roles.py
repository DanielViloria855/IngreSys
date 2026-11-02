"""Dominio compartido: roles del sistema."""
from enum import Enum


class Role(str, Enum):
    """Dominio: roles de usuario (coinciden con los `Group` de Django)."""

    ADMIN = "Administrador"
    SUPERVISOR = "Supervisor"
    OPERATOR = "Operario"
