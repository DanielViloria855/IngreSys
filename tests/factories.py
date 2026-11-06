"""Ayudas compartidas para las pruebas que usan la base de datos (usuarios, cuestionario e ingresos)."""
import io

from django.contrib.auth.models import Group, User
from django.core.management import call_command
from PIL import Image

from apps.entries.application.dtos import EvidenceUpload, RegisterEntryCommand
from apps.entries.infrastructure import container
from apps.questionnaire.infrastructure.container import get_questionnaire_repository
from shared.domain.roles import Role

PASSWORD = "x-pass-123"
VALID_CONTAINER = "CSQU3054383"
BAD_DIGIT_CONTAINER = "CSQU3054384"  # dígito esperado: 3

DEFAULT_ANSWERS = {
    "plate": "SKX482",
    "driver_name": "Luis",
    "driver_id": "123",
    "supplier": "otro",
    "has_container": "false",
    "cargo_type": "boxes",
    "vehicle_condition": "good",
    "has_novelty": "false",
}


def seed() -> None:
    call_command("seed_roles", verbosity=0)
    call_command("seed_questionnaire", verbosity=0)


def make_user(username: str, role: Role | None, password: str = PASSWORD, **extra) -> User:
    user = User.objects.create_user(username, password=password, **extra)
    if role is not None:
        user.groups.add(Group.objects.get(name=role.value))
    return user


def questions_by_tag() -> dict:
    return {q.semantic_tag: q for q in get_questionnaire_repository().get_active().questions}


def answers_for(**by_tag) -> dict:
    tags = questions_by_tag()
    data = dict(DEFAULT_ANSWERS, **by_tag)
    return {tags[tag].id: value for tag, value in data.items()}


def register(user, *, confirm: bool = False, photos: dict | None = None, **by_tag) -> int:
    """Registra un ingreso con el caso de uso real. `photos` = {semantic_tag: bytes}."""
    tags = questions_by_tag()
    evidences = [EvidenceUpload(tags[tag].id, f"{tag}.jpg", content) for tag, content in (photos or {}).items()]
    command = RegisterEntryCommand(user.id, answers_for(**by_tag), evidences, confirm_iso_override=confirm)
    return container.register_truck_entry().execute(command)


def post_data(**by_tag) -> dict:
    """Datos de POST del formulario dinámico (`q_<id>`), con los valores por defecto válidos."""
    tags = questions_by_tag()
    data = dict(DEFAULT_ANSWERS, **by_tag)
    return {f"q_{tags[tag].id}": value for tag, value in data.items() if value is not None}


def jpeg_bytes(size=(40, 30), color="white") -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, color).save(out, format="JPEG")
    return out.getvalue()
