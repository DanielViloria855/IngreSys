"""Seguridad: CSRF, control de acceso horizontal (IDOR), XSS, redirecciones abiertas, cabeceras,
contraseñas, subida de archivos, inyección en filtros, fuga de secretos y privacidad de los datos enviados al LLM."""
import json

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.analytics.application.prompts import build_user_prompt
from apps.analytics.domain.metrics import DateRange
from apps.analytics.infrastructure import container as analytics_container
from apps.entries.infrastructure.models import TruckEntry
from tests.factories import PASSWORD, post_data, questions_by_tag, register

pytestmark = pytest.mark.django_db


def html(response):
    return response.content.decode()


# -- CSRF ------------------------------------------------------------------------------------------
@pytest.fixture
def csrf_client():
    return Client(enforce_csrf_checks=True)


@pytest.mark.parametrize(
    "url,args,user",
    [("entries:create", [], "operator"), ("entries:ocr_plate", [], "operator"), ("entries:review", [1], "supervisor"),
     ("analytics:insights", [], "supervisor"), ("analytics:ask", [], "supervisor"), ("staff:create", [], "administrator"),
     ("accounts:logout", [], "operator")],
)
def test_state_changing_posts_require_csrf_token(request, csrf_client, url, args, user):
    csrf_client.force_login(request.getfixturevalue(user))
    assert csrf_client.post(reverse(url, args=args), {}).status_code == 403


def test_login_form_requires_csrf_token(csrf_client, operator):
    assert csrf_client.post(reverse("accounts:login"), {"username": "op1", "password": PASSWORD}).status_code == 403


def test_pages_expose_csrf_token_for_fetch_calls(client, supervisor):
    client.force_login(supervisor)
    assert '<meta name="csrf-token" content="' in html(client.get(reverse("analytics:dashboard")))


def test_post_with_valid_token_works(csrf_client, supervisor):
    csrf_client.force_login(supervisor)
    csrf_client.get(reverse("analytics:dashboard"))
    token = csrf_client.cookies["csrftoken"].value
    response = csrf_client.post(reverse("analytics:insights"), {"range": "today"}, HTTP_X_CSRFTOKEN=token)
    assert response.status_code == 200


# -- control de acceso horizontal -------------------------------------------------------------------
def test_operator_cannot_read_other_entries_by_id_or_filter(client, operator, operator2):
    theirs = register(operator2, plate="ZZZ999")
    client.force_login(operator)
    assert client.get(reverse("entries:detail", args=[theirs])).status_code == 404  # 404, no 403: no revela que existe
    assert "ZZZ999" not in html(client.get(reverse("entries:list"), {"user": operator2.id}))
    assert "ZZZ999" not in html(client.get(reverse("entries:list"), {"plate": "ZZZ"}))


def test_operator_cannot_escalate_through_staff_form(client, operator):
    client.force_login(operator)
    data = {"username": "op1", "first_name": "x", "last_name": "y", "role": "Administrador", "is_active": "on"}
    assert client.post(reverse("staff:edit", args=[operator.id]), data).status_code == 403
    operator.refresh_from_db()
    assert not operator.is_staff and not operator.groups.filter(name="Administrador").exists()


def test_operator_cannot_reach_django_admin(client, operator):
    client.force_login(operator)
    assert client.get("/admin/")["Location"].startswith("/admin/login/")


def test_admin_cannot_deactivate_itself(client, administrator):
    client.force_login(administrator)
    data = {"username": "adm", "first_name": "A", "last_name": "B", "email": "", "role": "Administrador", "document_id": "",
            "position": "", "phone": "", "password": "", "is_active": ""}
    response = client.post(reverse("staff:edit", args=[administrator.id]), data)
    assert response.status_code == 200 and "No puedes desactivar tu propio usuario." in html(response)
    administrator.refresh_from_db()
    assert administrator.is_active


# -- XSS -------------------------------------------------------------------------------------------
PAYLOAD = '<script>alert("x")</script>'


def test_user_input_is_escaped_in_detail_and_list(client, supervisor, operator):
    entry_id = register(operator, driver_name=PAYLOAD, observations=PAYLOAD)
    client.force_login(supervisor)
    client.post(reverse("entries:review", args=[entry_id]), {"comment": PAYLOAD})
    page = html(client.get(reverse("entries:detail", args=[entry_id])))
    assert PAYLOAD not in page and "&lt;script&gt;" in page


def test_filter_values_are_escaped(client, supervisor):
    client.force_login(supervisor)
    page = html(client.get(reverse("entries:list"), {"plate": '"><img src=x onerror=alert(1)>'}))
    assert "<img src=x" not in page


def test_staff_names_are_escaped(client, administrator, operator):
    operator.first_name = PAYLOAD
    operator.save()
    client.force_login(administrator)
    assert PAYLOAD not in html(client.get(reverse("staff:list")))


# -- redirecciones y cabeceras ---------------------------------------------------------------------
@pytest.mark.parametrize("target", ["https://evil.example/", "//evil.example/", "javascript:alert(1)"])
def test_login_ignores_external_next(client, operator, target):
    response = client.post(reverse("accounts:login"), {"username": "op1", "password": PASSWORD, "next": target})
    assert response.status_code == 302 and "evil" not in response["Location"] and "javascript" not in response["Location"]


def test_clickjacking_protection(client, operator):
    client.force_login(operator)
    assert client.get(reverse("entries:create"))["X-Frame-Options"] == "DENY"


def test_error_pages_do_not_leak_internals(client, operator):
    client.force_login(operator)
    page = html(client.get("/no-existe/"))
    assert "Traceback" not in page and "settings" not in page.lower()


# -- contraseñas y archivos ------------------------------------------------------------------------
def test_passwords_are_hashed(client, administrator):
    from django.contrib.auth.models import User

    client.force_login(administrator)
    client.post(reverse("staff:create"), {"username": "n", "first_name": "N", "last_name": "N", "email": "", "role": "Operario",
                                          "document_id": "", "position": "", "phone": "", "password": "Clave-segura-2026", "is_active": "on"})
    stored = User.objects.get(username="n").password
    assert "Clave-segura-2026" not in stored and stored.count("$") >= 2


@pytest.mark.parametrize("name", ["shell.php", "x.svg", "x.html", "noext", "evil.jpg.exe"])
def test_only_image_extensions_are_accepted(client, operator, name):
    client.force_login(operator)
    data = post_data()
    data[f"photo_{questions_by_tag()['plate'].id}"] = SimpleUploadedFile(name, b"<svg onload=alert(1)>", "image/svg+xml")
    assert client.post(reverse("entries:create"), data).status_code == 422
    assert TruckEntry.objects.count() == 0


@pytest.mark.parametrize("value", ["' OR 1=1 --", "%", "_", "\\", "\x00"])
def test_filters_are_not_injectable(client, supervisor, operator, value):
    register(operator, plate="AAA111")
    client.force_login(supervisor)
    response = client.get(reverse("entries:list"), {"plate": value, "container": value, "status": value})
    assert response.status_code == 200 and "AAA111" not in html(response)


# -- privacidad del LLM y secretos -----------------------------------------------------------------
def test_llm_prompt_contains_only_aggregates(operator):
    register(operator, plate="QWE987", driver_name="Hernando Pérez", driver_id="1098765432", supplier="carga_express",
             has_novelty="true", novelty_type=["pests"], novelty_description="Descripción privada del caso")
    today = timezone.localdate()
    prompt = build_user_prompt(analytics_container.get_dashboard_metrics().execute(DateRange(today, today)))
    for private in ("QWE987", "Hernando", "1098765432", "Descripción privada", "op1", "Olga"):
        assert private not in prompt
    assert json.loads(prompt)["trucks"] == 1


def test_json_endpoints_never_echo_provider_errors_with_secrets(client, supervisor, settings, monkeypatch):
    """El SDK suele incluir la llave en el mensaje de error; nada de eso debe llegar al navegador."""
    import sys
    import types

    secret = "gsk_esto_es_secreto_123456"

    class Groq:
        def __init__(self, **kwargs):
            def create(**kw):
                raise RuntimeError(f"401 Invalid API Key: {secret}")

            self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=create))

    monkeypatch.setitem(sys.modules, "groq", types.SimpleNamespace(Groq=Groq))
    settings.INSIGHT_PROVIDER, settings.GROQ_API_KEY = "groq", secret
    client.force_login(supervisor)
    response = client.post(reverse("analytics:insights"), {"range": "today"})
    assert response.status_code == 200 and response.json()["fallback_used"] is True
    assert "secreto" not in html(response) and "401" not in html(response)


def test_session_cookie_is_http_only(client, operator):
    response = client.post(reverse("accounts:login"), {"username": "op1", "password": PASSWORD})
    assert response.cookies["sessionid"]["httponly"]
