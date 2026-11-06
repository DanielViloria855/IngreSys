"""Funcional: tablero, endpoints JSON de analítica, gestión de personal, login/logout y navegación por rol."""
import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from apps.accounts.infrastructure.models import Profile
from shared.domain.roles import Role
from tests.factories import PASSWORD, make_user, register

pytestmark = pytest.mark.django_db


def html(response):
    return response.content.decode()


# -- tablero ---------------------------------------------------------------------------------------
@pytest.mark.parametrize("params", [{}, {"range": "7d"}, {"range": "30d"}, {"range": "custom", "start": "2026-01-01", "end": "2026-01-31"}])
def test_dashboard_presets_render(client, supervisor, params):
    client.force_login(supervisor)
    response = client.get(reverse("analytics:dashboard"), params)
    assert response.status_code == 200 and "Camiones ingresados" in html(response)
    assert response.context["preset"] == params.get("range", "today")


def test_dashboard_invalid_custom_range_falls_back_with_warning(client, supervisor):
    client.force_login(supervisor)
    response = client.get(reverse("analytics:dashboard"), {"range": "custom", "start": "2026-02-01", "end": "2026-01-01"}, follow=True)
    assert response.context["preset"] == "today" and "posterior" in html(response)


def test_dashboard_custom_range_is_propagated_to_json_urls(client, supervisor):
    client.force_login(supervisor)
    ctx = client.get(reverse("analytics:dashboard"), {"range": "custom", "start": "2026-01-01", "end": "2026-01-31"}).context
    assert "start=2026-01-01" in ctx["metrics_url"] and "end=2026-01-31" in ctx["insights_query"]


@pytest.mark.parametrize("provider,label", [("rules", "reglas automáticas"), ("groq", "IA (Groq)")])
def test_dashboard_shows_insight_mode(client, supervisor, settings, provider, label):
    settings.INSIGHT_PROVIDER = provider
    client.force_login(supervisor)
    assert f"Modo actual: {label}." in html(client.get(reverse("analytics:dashboard")))


def test_metrics_json_contract(client, supervisor, operator):
    register(operator)
    client.force_login(supervisor)
    body = client.get(reverse("analytics:metrics"), {"range": "7d"}).json()
    assert body["days"] == 7 and body["trucks"] == 1 and len(body["by_hour"]) == 24 and len(body["by_day"]) == 7
    assert set(body["deltas"]) >= {"trucks", "boxes"} and body["previous"]["trucks"] == 0
    assert client.get(reverse("analytics:metrics"), {"range": "custom", "start": "x", "end": "y"}).status_code == 400


def test_insights_fall_back_to_rules_when_groq_has_no_key(client, supervisor, settings):
    settings.INSIGHT_PROVIDER = "groq"
    client.force_login(supervisor)
    body = client.post(reverse("analytics:insights"), {"range": "today"}).json()
    assert body["fallback_used"] is True and body["model_used"] == "Reglas automáticas" and body["insights"]


# -- personal --------------------------------------------------------------------------------------
def test_staff_list_shows_users_with_role_and_status(client, administrator, operator):
    Profile.objects.create(user=operator, position="Portería", document_id="CC-9")
    operator.is_active = False
    operator.save()
    client.force_login(administrator)
    response = client.get(reverse("staff:list"))
    rows = {r["username"]: r for r in response.context["rows"]}
    assert rows["op1"]["role"] == "Operario" and rows["op1"]["position"] == "Portería" and rows["op1"]["is_active"] is False
    assert rows["op1"]["name"] == "Olga Pérez" and list(rows)[0] == "adm"  # activos primero


def test_staff_create_invalid_rerenders_with_errors(client, administrator):
    client.force_login(administrator)
    response = client.post(reverse("staff:create"), {"username": "adm", "first_name": "", "last_name": "x", "role": "Operario"})
    assert response.status_code == 200 and "Ya existe un usuario con ese nombre." in html(response)
    assert User.objects.count() == 1


def test_staff_edit_get_prefills_and_unknown_is_404(client, administrator, operator):
    client.force_login(administrator)
    page = html(client.get(reverse("staff:edit", args=[operator.id])))
    assert 'value="op1"' in page and "Déjala vacía" in page
    assert client.get(reverse("staff:edit", args=[999999])).status_code == 404


def test_saved_staff_member_can_log_in_and_deactivated_cannot(client, administrator):
    client.force_login(administrator)
    data = {"username": "nora", "first_name": "Nora", "last_name": "R", "email": "", "role": "Supervisor", "document_id": "",
            "position": "", "phone": "", "password": "Clave-segura-2026", "is_active": "on"}
    assert client.post(reverse("staff:create"), data).status_code == 302
    client.logout()
    assert client.login(username="nora", password="Clave-segura-2026")
    client.logout()
    client.force_login(administrator)
    nora = User.objects.get(username="nora")
    client.post(reverse("staff:edit", args=[nora.id]), dict(data, password="", is_active=""))
    client.logout()
    assert not client.login(username="nora", password="Clave-segura-2026")


# -- autenticación -----------------------------------------------------------------------------------
def test_login_success_redirects_home_then_by_role(client, supervisor):
    response = client.post(reverse("accounts:login"), {"username": "sup", "password": PASSWORD}, follow=True)
    assert response.redirect_chain[-1][0] == reverse("analytics:dashboard")


def test_login_failure_message(client, operator):
    response = client.post(reverse("accounts:login"), {"username": "op1", "password": "mala"})
    assert response.status_code == 200 and "Usuario o contraseña incorrectos" in html(response)


def test_inactive_user_cannot_log_in(client, operator):
    operator.is_active = False
    operator.save()
    assert "Usuario o contraseña incorrectos" in html(client.post(reverse("accounts:login"), {"username": "op1", "password": PASSWORD}))


def test_login_honours_safe_next(client, supervisor):
    response = client.post(reverse("accounts:login") + "?next=/entries/", {"username": "sup", "password": PASSWORD, "next": "/entries/"})
    assert response["Location"] == "/entries/"


def test_logout_requires_post_and_ends_session(client, operator):
    client.force_login(operator)
    response = client.post(reverse("accounts:logout"))
    assert response["Location"] == reverse("accounts:login")
    assert client.get(reverse("entries:list")).status_code == 302


# -- navegación según el rol -----------------------------------------------------------------------
@pytest.mark.parametrize(
    "role,visible,hidden",
    [(Role.OPERATOR, ["Histórico", "Nuevo ingreso"], ["Tablero", "Personal", "Cuestionario"]),
     (Role.SUPERVISOR, ["Tablero", "Histórico"], ["Personal", "Cuestionario"]),
     (Role.ADMIN, ["Tablero", "Histórico", "Personal", "Cuestionario", "Administración"], [])],
)
def test_navbar_by_role(client, seeded, role, visible, hidden):
    user = make_user(f"nav-{role.name}", role)
    client.force_login(user)
    nav = html(client.get(reverse("entries:list"))).split("<main", 1)[0]
    for text in visible:
        assert f">{text}<" in nav
    for text in hidden:
        assert f">{text}<" not in nav
    assert f"<small>{role.value}</small>" in nav
