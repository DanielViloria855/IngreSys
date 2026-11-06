"""Crea los grupos (roles) del sistema y les asigna sus permisos."""
from django.core.management.base import BaseCommand

from apps.core.permissions import ensure_roles
from shared.domain.roles import Role


class Command(BaseCommand):
    help = "Crea los roles Administrador, Supervisor y Operario con sus permisos."

    def handle(self, *args, **options):
        ensure_roles()
        for role in Role:
            self.stdout.write(f"listo: {role.value}")
