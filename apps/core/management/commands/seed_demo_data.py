"""Datos de demostración: roles, usuarios, cuestionario y ~60 ingresos repartidos en 14 días.

Los ingresos se crean con el caso de uso real `RegisterTruckEntry`, así la demo ejercita todo el flujo.
"""
import random
from datetime import datetime, time, timedelta

from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.accounts.infrastructure.models import Profile
from apps.entries.application.dtos import RegisterEntryCommand, ReviewEntryCommand
from apps.entries.domain import iso6346
from apps.entries.infrastructure import container
from apps.entries.infrastructure.models import TruckEntry as TruckEntryModel
from apps.questionnaire.infrastructure.container import get_questionnaire_repository
from shared.application.actor import Actor
from shared.domain.roles import Role

DEMO_PASSWORD = "Ingresys2026!"
DRIVERS = ["Carlos Restrepo", "Luis Gómez", "Andrés Muñoz", "Jorge Salazar", "Camilo Ríos", "Mauricio Zapata", "Fabio Henao", "Óscar Villa"]
USERS = [
    ("admin", "Daniela", "Arango", Role.ADMIN, "Coordinadora de sistemas"),
    ("supervisor", "Sergio", "Cardona", Role.SUPERVISOR, "Supervisor de recibo"),
    ("operario1", "Natalia", "Osorio", Role.OPERATOR, "Operaria de portería"),
    ("operario2", "Julián", "Pérez", Role.OPERATOR, "Operario de portería"),
    ("operario3", "Marta", "Londoño", Role.OPERATOR, "Operaria de portería"),
]


class Command(BaseCommand):
    help = "Crea usuarios demo, el cuestionario y ingresos de ejemplo."

    def add_arguments(self, parser):
        parser.add_argument("--entries", type=int, default=60)
        parser.add_argument("--days", type=int, default=14)
        parser.add_argument("--reset", action="store_true", help="Borra los ingresos existentes antes de crear los de demo.")

    def handle(self, *args, **options):
        rng = random.Random(2026)
        call_command("seed_roles", verbosity=0)
        call_command("seed_questionnaire", verbosity=0)
        users = self._users()
        if options["reset"]:
            TruckEntryModel.objects.all().delete()

        questionnaire = get_questionnaire_repository().get_active()
        qid = {q.semantic_tag: q for q in questionnaire.questions}
        register = container.register_truck_entry()
        review = container.review_entry()
        operators = [u for u, role in users if role is Role.OPERATOR]
        reviewer = Actor(id=users[1][0].id, display_name="Sergio Cardona", role=Role.SUPERVISOR)
        today = timezone.localdate()
        created = 0

        for index in range(options["entries"]):
            offset = 0 if index < 8 else min(int(rng.expovariate(0.28)), options["days"] - 1)
            when = self._moment(rng, today, offset)
            answers = self._answers(rng, qid)
            command = RegisterEntryCommand(
                user_id=rng.choice(operators).id, answers=answers, evidences=[],
                confirm_iso_override=bool(answers.get("__invalid_iso")),
            )
            answers.pop("__invalid_iso", None)
            entry_id = register.execute(command)
            TruckEntryModel.objects.filter(pk=entry_id).update(created_at=when)
            if offset >= 1 and rng.random() < 0.8:
                review.execute(ReviewEntryCommand(entry_id, reviewer, "Revisado en demo."))
                TruckEntryModel.objects.filter(pk=entry_id).update(reviewed_at=when + timedelta(hours=2))
            created += 1

        self.stdout.write(self.style.SUCCESS(f"{created} ingresos creados."))
        self.stdout.write("Usuarios demo (contraseña común): " + DEMO_PASSWORD)
        for user, role in users:
            self.stdout.write(f"  - {user.username:<11} {role.value}")

    # -- helpers ---------------------------------------------------------------------
    def _users(self) -> list[tuple[User, Role]]:
        result = []
        for username, first, last, role, position in USERS:
            user, _ = User.objects.get_or_create(username=username, defaults={"first_name": first, "last_name": last})
            user.first_name, user.last_name = first, last
            user.is_staff = role is Role.ADMIN
            user.set_password(DEMO_PASSWORD)
            user.save()
            user.groups.set([Group.objects.get(name=role.value)])
            Profile.objects.update_or_create(user=user, defaults={"position": position})
            result.append((user, role))
        return result

    @staticmethod
    def _moment(rng: random.Random, today, offset: int) -> datetime:
        hour = int(max(6, min(17, rng.gauss(10.5, 2.6))))
        if offset == 0:
            hour = min(hour, max(6, timezone.localtime().hour))
        naive = datetime.combine(today - timedelta(days=offset), time(hour, rng.randint(0, 59)))
        return timezone.make_aware(naive)

    @staticmethod
    def _plate(rng: random.Random) -> str:
        letters = "".join(rng.choice("ABCDEFGHJKLMNPRSTUVWXYZ") for _ in range(3))
        return f"{letters}{rng.randint(100, 999)}"

    @staticmethod
    def _container(rng: random.Random, valid: bool) -> str:
        owner = "".join(rng.choice("ABCDEFGHJKLMNPRSTUVWXYZ") for _ in range(3)) + "U"
        base = owner + f"{rng.randint(0, 999999):06d}"
        digit = iso6346.compute_check_digit(base)
        return base + str(digit if valid else (digit + 1) % 10)

    def _answers(self, rng: random.Random, qid: dict) -> dict:
        def pick(tag: str) -> str:
            return rng.choice(qid[tag].choices).value

        has_container = rng.random() < 0.6
        has_novelty = rng.random() < 0.2
        invalid_iso = has_container and rng.random() < 0.1
        data = {
            "plate": self._plate(rng),
            "driver_name": rng.choice(DRIVERS),
            "driver_id": str(rng.randint(10_000_000, 1_099_999_999)),
            "supplier": pick("supplier"),
            "has_container": "true" if has_container else "false",
            "cargo_type": pick("cargo_type"),
            "pallets_count": str(rng.randint(4, 26)),
            "boxes_count": str(rng.randint(120, 900)),
            "witness_samples_count": str(rng.randint(1, 6)),
            "unit": pick("unit"),
            "vehicle_condition": rng.choices(["good", "fair", "bad"], weights=[70, 22, 8])[0],
            "has_novelty": "true" if has_novelty else "false",
        }
        if has_container:
            data.update(
                container_code=self._container(rng, valid=not invalid_iso),
                seal_number=f"SL{rng.randint(100000, 999999)}",
                seal_ok="true" if rng.random() < 0.92 else "false",
            )
        if has_novelty:
            data["novelty_type"] = rng.sample([c.value for c in qid["novelty_type"].choices], k=rng.randint(1, 2))
            data["novelty_description"] = rng.choice(
                ["Estibas con humedad visible", "Cajas golpeadas en el costado", "Olor fuerte al abrir el contenedor", "Se observan plagas en el piso"]
            )
        result = {qid[tag].id: value for tag, value in data.items()}
        result["__invalid_iso"] = invalid_iso
        return result
