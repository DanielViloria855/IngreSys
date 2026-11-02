"""Infraestructura (adaptador primario): vistas del núcleo."""
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.views import View

from apps.core.roles import get_role
from shared.domain.roles import Role


class HomeView(LoginRequiredMixin, View):
    """Redirige según el rol: tablero para supervisor/admin, nuevo ingreso para operario."""

    def get(self, request):
        if get_role(request.user) in (Role.ADMIN, Role.SUPERVISOR):
            return redirect("analytics:dashboard")
        return redirect("entries:create")
