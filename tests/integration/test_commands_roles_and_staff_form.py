"""Integración: comandos de gestión, roles/permisos y formulario de personal."""
import io

import pytest
from django.contrib.auth.models import AnonymousUser, Group, User
from django.core.management import call_command

from apps.accounts.infrastructure.forms import StaffForm
from apps.accounts.infrastructure.models import Profile
from apps.core.context_processors import user_role
from apps.core.management.commands.check_integrations import _mask
from apps.core.permissions import ROLE_PERMISSIONS, ensure_roles
from apps.core.roles import build_actor, get_role
from apps.entries.infrastructure.models import TruckEntry as TruckEntryModel
from apps.questionnaire.infrastructure.models import Question, Questionnaire
from shared.domain.roles import Role
from tests.factories import make_user, register

pytestmark = pytest.mark.django_db


def run(name, *args):
    out, err = io.StringIO(), io.StringIO()
    call_command(name, *args, stdout=out, stderr=err)
    return out.getvalue(), err.getvalue()


# -- seed_roles / permisos -------------------------------------------------------------------------
def perms(role):
    return set(Group.objects.get(name=role.value).permissions.values_list("codename", flat=True))


def test_seed_roles_is_idempotent_and_sets_exact_permissions(db):
    run("seed_roles")
    run("seed_roles")
    assert Group.objects.filter(name__in=[r.value for r in Role]).count() == 3
    assert {"add_question", "change_questionnaire", "delete_choice", "view_truckentry"} <= perms(Role.ADMIN)
    assert "change_truckentry" not in perms(Role.ADMIN)  # los ingresos son de solo lectura en /admin/
    assert perms(Role.SUPERVISOR) == set() and perms(Role.OPERATOR) == set()


def test_ensure_roles_removes_manually_added_permissions(db):
    ensure_roles()
    from django.contrib.auth.models import Permission

    Group.objects.get(name=Role.OPERATOR.value).permissions.add(Permission.objects.get(codename="delete_truckentry"))
    ensure_roles()
    assert perms(Role.OPERATOR) == set()


def test_every_permission_in_the_matrix_exists(db):
    ensure_roles()
    expected = {f"{a}_{m}" for apps in ROLE_PERMISSIONS.values() for models in apps.values() for m, acts in models.items() for a in acts}
    assert perms(Role.ADMIN) == expected


# -- seed_questionnaire ----------------------------------------------------------------------------
def test_seed_questionnaire_twice_and_reset(seeded):
    out, _ = run("seed_questionnaire")
    assert "Ya existe" in out and Questionnaire.objects.count() == 1
    old_id = Questionnaire.objects.get().id
    out, _ = run("seed_questionnaire", "--reset")
    assert "19 preguntas" in out and Questionnaire.objects.get().id != old_id
    assert Question.objects.count() == 19


def test_seed_questionnaire_reset_refuses_when_entries_exist(operator):
    register(operator)
    _, err = run("seed_questionnaire", "--reset")
    assert "No se pudo borrar" in err and TruckEntryModel.objects.count() == 1 and Questionnaire.objects.count() == 1


# -- seed_demo_data --------------------------------------------------------------------------------
def test_seed_demo_data_small_run_is_deterministic(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    out, _ = run("seed_demo_data", "--entries", "25", "--days", "10", "--seed", "7")
    assert "25 ingresos creados" in out and TruckEntryModel.objects.count() == 25
    assert {u.username for u in User.objects.all()} >= {"admin", "supervisor", "operario1", "operario2", "operario3"}
    assert User.objects.get(username="admin").is_staff and not User.objects.get(username="supervisor").is_staff
    first = list(TruckEntryModel.objects.order_by("id").values_list("plate", "container_code", "status"))
    run("seed_demo_data", "--entries", "25", "--days", "10", "--seed", "7", "--reset")
    assert list(TruckEntryModel.objects.order_by("id").values_list("plate", "container_code", "status")) == first


# -- check_integrations ----------------------------------------------------------------------------
@pytest.mark.parametrize("text", ["clave AIzaSyA1234567890abcdef", "token gsk_abcdefghijklmnop123"])
def test_mask_hides_keys(text):
    masked = _mask(text)
    assert "[llave oculta]" in masked and "AIzaSy" not in masked and "gsk_abc" not in masked


def test_check_integrations_with_offline_providers_never_prints_secrets(settings):
    settings.GROQ_API_KEY = "gsk_supersecreto1234567890"
    settings.GOOGLE_VISION_API_KEY = "AIzaSySuperSecreto123456"
    out, _ = run("check_integrations")
    assert "adaptador falso" in out and "usando reglas" in out
    assert "GROQ_API_KEY=definida" in out and "GOOGLE_VISION_API_KEY=definida" in out
    assert "supersecreto" not in out.lower()


# -- roles -----------------------------------------------------------------------------------------
def test_get_role_rules(seeded):
    assert get_role(AnonymousUser()) is None
    assert get_role(make_user("nadie", None)) is None
    assert get_role(User.objects.create_superuser("root", password="x")) is Role.ADMIN
    both = make_user("ambos", Role.OPERATOR)
    both.groups.add(Group.objects.get(name=Role.SUPERVISOR.value))
    assert get_role(both) is Role.SUPERVISOR  # gana el rol de más privilegio


def test_build_actor_defaults(seeded):
    actor = build_actor(make_user("sinrol", None))
    assert actor.role is Role.OPERATOR and actor.display_name == "sinrol"
    named = build_actor(make_user("n", Role.ADMIN, first_name="Ana", last_name="Ruiz"))
    assert named.display_name == "Ana Ruiz" and named.can_review


@pytest.mark.parametrize(
    "role,flags",
    [(Role.ADMIN, (True, False, False, True, True)), (Role.SUPERVISOR, (False, True, False, True, True)),
     (Role.OPERATOR, (False, False, True, False, False))],
)
def test_context_processor_flags(seeded, rf, role, flags):
    request = rf.get("/")
    request.user = make_user(f"u-{role.name}", role)
    ctx = user_role(request)
    assert ctx["user_role"] == role.value
    assert (ctx["role_is_admin"], ctx["role_is_supervisor"], ctx["role_is_operator"], ctx["can_see_dashboard"], ctx["can_review"]) == flags


def test_context_processor_for_anonymous_and_requests_without_user(rf):
    request = rf.get("/")
    request.user = AnonymousUser()
    assert user_role(request)["user_role"] == "" and not user_role(request)["can_review"]
    assert user_role(rf.get("/"))["user_role"] == ""


# -- formulario de personal ------------------------------------------------------------------------
def staff_data(**over):
    data = {"username": "nuevo", "first_name": "Nora", "last_name": "Ruiz", "email": "", "role": Role.OPERATOR.value,
            "document_id": "1", "position": "Portería", "phone": "300", "password": "Clave-segura-2026", "is_active": "on"}
    data.update(over)
    return data


def test_staff_form_creates_user_profile_and_group(seeded):
    form = StaffForm(staff_data())
    assert form.is_valid(), form.errors
    user = form.save()
    assert user.check_password("Clave-segura-2026") and not user.is_staff and user.is_active
    assert get_role(user) is Role.OPERATOR and Profile.objects.get(user=user).phone == "300"


def test_staff_form_admin_role_grants_django_admin(seeded):
    form = StaffForm(staff_data(role=Role.ADMIN.value))
    assert form.is_valid() and form.save().is_staff


@pytest.mark.parametrize(
    "over,field",
    [({"username": "OP1"}, "username"), ({"password": ""}, "password"), ({"password": "123"}, "password"),
     ({"password": "password"}, "password"), ({"role": "Root"}, "role"), ({"email": "no-es-correo"}, "email")],
)
def test_staff_form_validation(operator, over, field):
    form = StaffForm(staff_data(**over))
    assert not form.is_valid() and field in form.errors


def test_staff_form_edit_keeps_password_and_switches_role(operator):
    old_hash = operator.password
    form = StaffForm(staff_data(username="op1", password="", role=Role.SUPERVISOR.value), instance=operator)
    assert form.is_valid(), form.errors
    user = form.save()
    assert user.password == old_hash and get_role(user) is Role.SUPERVISOR
    assert list(user.groups.values_list("name", flat=True)) == [Role.SUPERVISOR.value]


def test_staff_form_initial_from_instance(operator):
    Profile.objects.create(user=operator, position="Portería")
    form = StaffForm(instance=operator)
    assert form.initial["username"] == "op1" and form.initial["role"] == Role.OPERATOR.value
    assert form.initial["position"] == "Portería" and not form.fields["password"].required
    assert form.fields["role"].widget.attrs["class"] == "form-select"
