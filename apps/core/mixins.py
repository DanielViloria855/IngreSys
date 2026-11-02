"""Infraestructura: mixins de vistas compartidos."""
from django.contrib.auth.mixins import AccessMixin
from django.core.exceptions import PermissionDenied

from apps.core.roles import get_role
from shared.domain.roles import Role


class RoleRequiredMixin(AccessMixin):
    """Mixin (infraestructura): restringe una vista a ciertos roles. Úsalo después de LoginRequiredMixin."""

    allowed_roles: tuple[Role, ...] = ()

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if self.allowed_roles and get_role(request.user) not in self.allowed_roles:
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)
