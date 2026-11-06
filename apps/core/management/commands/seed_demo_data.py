"""Datos de demostración: roles, usuarios, cuestionario y muchos ingresos con una «historia» realista.

Los ingresos se crean con el caso de uso real `RegisterTruckEntry`, así la demo ejercita todo el flujo.

No es ruido aleatorio uniforme: el tablero y el análisis con IA necesitan patrones que interpretar.
  · Volumen con tendencia al alza, menos movimiento los fines de semana y picos a las 8 h y a las 14 h.
  · Los últimos 7 días tienen una semana anómala: más novedades (sobre todo humedad), más volumen y
    algunos ingresos fuera de horario.
  · El proveedor «Frontera Cargo» concentra los problemas: sellos rotos, ISO inválido y plagas.
  · Los ingresos antiguos están revisados; los recientes se acumulan sin revisar.
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
PROBLEM_SUPPLIER = "frontera_cargo"
WEEKDAY_FACTOR = [1.15, 1.1, 1.0, 1.0, 0.95, 0.45, 0.2]  # lunes … domingo
SUPPLIER_WEIGHTS = {"transportes_andina": 22, "logística_del_caribe": 18, "carga_express": 20, "frontera_cargo": 14, "transmar_sa": 18, "otro": 8}
DRIVERS = ["Carlos Restrepo", "Luis Gómez", "Andrés Muñoz", "Jorge Salazar", "Camilo Ríos", "Mauricio Zapata", "Fabio Henao", "Óscar Villa",
           "Iván Cardona", "Wilson Arango", "Hernán Betancur", "Diego Ospina"]
NOVELTY_TEXT = {
    "humidity": "Estibas con humedad visible", "pests": "Se observan plagas en el piso del contenedor",
    "damaged": "Cajas golpeadas en el costado", "odors": "Olor fuerte al abrir el contenedor",
    "looting": "Precinto alterado, faltante de mercancía", "other": "Novedad registrada por el operario",
}
USERS = [
    ("admin", "Daniela", "Arango", Role.ADMIN, "Coordinadora de sistemas"),
    ("supervisor", "Sergio", "Cardona", Role.SUPERVISOR, "Supervisor de recibo"),
    ("operario1", "Natalia", "Osorio", Role.OPERATOR, "Operaria de portería"),
    ("operario2", "Julián", "Pérez", Role.OPERATOR, "Operario de portería"),
    ("operario3", "Marta", "Londoño", Role.OPERATOR, "Operaria de portería"),
]


class Command(BaseCommand):
    help = "Crea usuarios demo, el cuestionario y muchos ingresos con tendencias para el tablero y la IA."

    def add_arguments(self, parser):
        parser.add_argument("--entries", type=int, default=700, help="Cantidad de ingresos a crear.")
        parser.add_argument("--days", type=int, default=45, help="Días hacia atrás sobre los que se reparten.")
        parser.add_argument("--seed", type=int, default=2026, help="Semilla del generador (mismo valor = mismos datos).")
        parser.add_argument("--reset", action="store_true", help="Borra TODOS los ingresos existentes antes de crear los de demo.")

    def handle(self, *args, **options):
        rng = random.Random(options["seed"])
        days = max(options["days"], 8)
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

        offsets = list(range(days))
        weights = [self._day_weight(today - timedelta(days=o), o, days) for o in offsets]
        chosen = rng.choices(offsets, weights=weights, k=options["entries"])
        chosen.sort(reverse=True)  # del más antiguo al más reciente

        created = reviewed = 0
        for offset in chosen:
            anomaly = offset < 7
            when = self._moment(rng, today, offset, anomaly)
            supplier = rng.choices(list(SUPPLIER_WEIGHTS), weights=list(SUPPLIER_WEIGHTS.values()))[0]
            answers, invalid_iso = self._answers(rng, qid, supplier, anomaly)
            entry_id = register.execute(RegisterEntryCommand(
                user_id=rng.choice(operators).id, answers=answers, evidences=[], confirm_iso_override=invalid_iso,
            ))
            TruckEntryModel.objects.filter(pk=entry_id).update(created_at=when)
            review_rate = 0.92 if offset > 3 else (0.35 if offset > 0 else 0.0)  # los recientes se acumulan sin revisar
            if rng.random() < review_rate:
                review.execute(ReviewEntryCommand(entry_id, reviewer, rng.choice(["Revisado.", "Sin diferencias.", "Documentos conformes.", ""])))
                TruckEntryModel.objects.filter(pk=entry_id).update(reviewed_at=when + timedelta(hours=rng.randint(1, 20)))
                reviewed += 1
            created += 1

        self.stdout.write(self.style.SUCCESS(f"{created} ingresos creados en {days} días ({reviewed} revisados)."))
        self.stdout.write(f"Total de ingresos en la base: {TruckEntryModel.objects.count()}")
        self.stdout.write("Usuarios demo (contraseña común): " + DEMO_PASSWORD)
        for user, role in users:
            self.stdout.write(f"  - {user.username:<11} {role.value}")

    # -- usuarios ---------------------------------------------------------------------
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

    # -- tiempo -------------------------------------------------------------------------
    @staticmethod
    def _day_weight(day, offset: int, days: int) -> float:
        trend = 1 + 0.9 * (1 - offset / days)  # el volumen crece hacia hoy
        spike = 1.45 if offset < 7 else 1.0  # semana anómala
        return WEEKDAY_FACTOR[day.weekday()] * trend * spike

    @staticmethod
    def _moment(rng: random.Random, today, offset: int, anomaly: bool) -> datetime:
        if anomaly and rng.random() < 0.1:
            hour = rng.randint(19, 21)  # ingresos fuera de horario
        elif rng.random() < 0.6:
            hour = int(rng.gauss(8.4, 1.2))
        else:
            hour = int(rng.gauss(14, 1.5))
        hour = max(6, min(21, hour))
        if offset == 0:
            hour = min(hour, max(6, timezone.localtime().hour))
        naive = datetime.combine(today - timedelta(days=offset), time(hour, rng.randint(0, 59)))
        return timezone.make_aware(naive)

    # -- contenido de cada ingreso --------------------------------------------------------
    @staticmethod
    def _letters(rng: random.Random, n: int) -> str:
        return "".join(rng.choice("ABCDEFGHJKLMNPRSTUVWXYZ") for _ in range(n))

    def _container(self, rng: random.Random, valid: bool) -> str:
        base = self._letters(rng, 3) + "U" + f"{rng.randint(0, 999999):06d}"
        digit = iso6346.compute_check_digit(base)
        return base + str(digit if valid else (digit + rng.randint(1, 9)) % 10)  # nunca coincide con el correcto

    def _answers(self, rng: random.Random, qid: dict, supplier: str, anomaly: bool) -> tuple[dict, bool]:
        problem = supplier == PROBLEM_SUPPLIER
        has_container = rng.random() < (0.7 if problem else 0.55)
        invalid_iso = has_container and rng.random() < (0.28 if problem else 0.05)
        novelty_rate = 0.12 + (0.2 if anomaly else 0) + (0.15 if problem else 0)
        has_novelty = rng.random() < novelty_rate
        pallets = max(2, int(rng.gauss(16, 6)))
        data = {
            "plate": self._letters(rng, 3) + str(rng.randint(100, 999)),
            "driver_name": rng.choice(DRIVERS),
            "driver_id": str(rng.randint(10_000_000, 1_099_999_999)),
            "supplier": supplier,
            "has_container": "true" if has_container else "false",
            "cargo_type": rng.choice([c.value for c in qid["cargo_type"].choices]),
            "pallets_count": str(pallets),
            "boxes_count": str(int(pallets * rng.uniform(22, 45))),
            "witness_samples_count": str(rng.randint(1, 6)),
            "unit": rng.choice(["kg", "units"]),
            "vehicle_condition": rng.choices(["good", "fair", "bad"], weights=[55, 30, 15] if problem else [75, 20, 5])[0],
            "has_novelty": "true" if has_novelty else "false",
        }
        if has_container:
            data.update(
                container_code=self._container(rng, valid=not invalid_iso),
                seal_number=f"SL{rng.randint(100000, 999999)}",
                seal_ok="true" if rng.random() > (0.22 if problem else 0.04) else "false",
            )
        if has_novelty:
            humid_week = anomaly and rng.random() < 0.55
            pool = ["humidity"] if humid_week else (["pests", "looting"] if problem and rng.random() < 0.6 else ["damaged", "odors", "humidity", "pests", "other"])
            kinds = rng.sample(pool, k=min(len(pool), rng.choice([1, 1, 2])))
            data["novelty_type"] = kinds
            data["novelty_description"] = NOVELTY_TEXT[kinds[0]]
        result = {qid[tag].id: value for tag, value in data.items()}
        return result, invalid_iso
