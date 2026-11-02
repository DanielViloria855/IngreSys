"""Infraestructura: variables de rol disponibles en todas las plantillas."""
from apps.core.roles import get_role
from shared.domain.roles import Role


def user_role(request):
    role = get_role(request.user) if hasattr(request, "user") else None
    return {
        "user_role": role.value if role else "",
        "role_is_admin": role == Role.ADMIN,
        "role_is_supervisor": role == Role.SUPERVISOR,
        "role_is_operator": role == Role.OPERATOR,
        "can_see_dashboard": role in (Role.ADMIN, Role.SUPERVISOR),
        "can_review": role in (Role.ADMIN, Role.SUPERVISOR),
    }
