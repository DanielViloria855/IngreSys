"""Crea los grupos (roles) del sistema."""
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand

from shared.domain.roles import Role


class Command(BaseCommand):
    help = "Crea los roles Administrador, Supervisor y Operario."

    def handle(self, *args, **options):
        for role in Role:
            _, created = Group.objects.get_or_create(name=role.value)
            self.stdout.write(f"{'creado' if created else 'existe'}: {role.value}")
