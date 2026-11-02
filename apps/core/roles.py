"""Infraestructura: traduce un usuario de Django a un rol del dominio."""
from shared.application.actor import Actor
from shared.domain.roles import Role


def get_role(user) -> Role | None:
    """Rol efectivo del usuario. El superusuario cuenta como Administrador."""
    if not user.is_authenticated:
        return None
    if user.is_superuser:
        return Role.ADMIN
    names = set(user.groups.values_list("name", flat=True))
    for role in (Role.ADMIN, Role.SUPERVISOR, Role.OPERATOR):
        if role.value in names:
            return role
    return None


def build_actor(user) -> Actor:
    """Crea el Actor de aplicación a partir del usuario autenticado."""
    role = get_role(user) or Role.OPERATOR
    return Actor(id=user.id, display_name=user.get_full_name() or user.get_username(), role=role)
