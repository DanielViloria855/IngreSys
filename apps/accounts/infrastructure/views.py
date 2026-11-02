"""Infraestructura (adaptador primario): login/logout y gestión de personal.

La autenticación NO se abstrae: se usa `django.contrib.auth` directamente.
"""
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.contrib.auth.views import LoginView, LogoutView
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from apps.accounts.infrastructure.forms import StaffForm
from apps.core.mixins import RoleRequiredMixin
from apps.core.roles import get_role
from shared.domain.roles import Role


class IngreLoginView(LoginView):
    template_name = "pages/auth/login.html"
    redirect_authenticated_user = True


class IngreLogoutView(LogoutView):
    """Cierra sesión (solo POST, como exige Django 5)."""


class StaffAdminMixin(LoginRequiredMixin, RoleRequiredMixin):
    allowed_roles = (Role.ADMIN,)


class StaffListView(StaffAdminMixin, View):
    def get(self, request):
        users = User.objects.select_related("profile").prefetch_related("groups").order_by("-is_active", "first_name", "username")
        rows = []
        for u in users:
            profile = getattr(u, "profile", None)
            rows.append(
                {
                    "id": u.id,
                    "name": u.get_full_name() or u.username,
                    "username": u.username,
                    "role": (get_role(u) or Role.OPERATOR).value,
                    "position": getattr(profile, "position", ""),
                    "document_id": getattr(profile, "document_id", ""),
                    "is_active": u.is_active,
                }
            )
        return render(request, "pages/staff/list.html", {"rows": rows})


class StaffFormView(StaffAdminMixin, View):
    """Crea (sin pk) o edita (con pk) un empleado."""

    def _instance(self, pk):
        return get_object_or_404(User, pk=pk) if pk else None

    def get(self, request, pk=None):
        instance = self._instance(pk)
        return render(request, "pages/staff/form.html", {"form": StaffForm(instance=instance), "editing": instance})

    def post(self, request, pk=None):
        instance = self._instance(pk)
        form = StaffForm(request.POST, instance=instance)
        if form.is_valid():
            if instance is not None and instance.pk == request.user.pk and not form.cleaned_data["is_active"]:
                form.add_error("is_active", "No puedes desactivar tu propio usuario.")
            else:
                user = form.save()
                messages.success(request, f"Personal guardado: {user.get_full_name() or user.username}.")
                return redirect("staff:list")
        return render(request, "pages/staff/form.html", {"form": form, "editing": instance})
