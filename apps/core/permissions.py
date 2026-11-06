"""Infraestructura: permisos de Django que recibe cada rol (grupo).

El panel `/admin/` solo muestra a un usuario no superusuario los modelos sobre los que tiene
permisos explícitos. Por eso el rol Administrador necesita permisos de edición del cuestionario.
"""
from django.contrib.auth.models import Group, Permission

from shared.domain.roles import Role

FULL = ("add", "change", "delete", "view")
READ = ("view",)

# rol -> {app: {modelo: acciones}}
ROLE_PERMISSIONS: dict[Role, dict[str, dict[str, tuple[str, ...]]]] = {
    Role.ADMIN: {
        "questionnaire": {"questionnaire": FULL, "question": FULL, "choice": FULL},
        "entries": {"truckentry": READ, "answer": READ, "evidence": READ},
    },
    Role.SUPERVISOR: {},
    Role.OPERATOR: {},
}


def ensure_roles() -> None:
    """Crea los grupos y deja sus permisos exactamente como indica ROLE_PERMISSIONS (idempotente)."""
    for role, apps in ROLE_PERMISSIONS.items():
        group, _ = Group.objects.get_or_create(name=role.value)
        codenames = {f"{action}_{model}" for models in apps.values() for model, actions in models.items() for action in actions}
        permissions = Permission.objects.filter(
            content_type__app_label__in=list(apps), codename__in=codenames
        ) if apps else Permission.objects.none()
        group.permissions.set(permissions)
