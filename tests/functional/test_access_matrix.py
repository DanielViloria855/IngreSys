"""Funcional: matriz de acceso — cada URL × cada tipo de usuario → código HTTP esperado."""
import json

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from shared.domain.roles import Role
from tests.factories import make_user, register

pytestmark = pytest.mark.django_db

ANON, NO_ROLE, OP, SUP, ADM, ROOT = "anónimo", "sin_rol", "operario", "supervisor", "administrador", "superusuario"
LOGIN = 302  # redirige a /accounts/login/

# (nombre de URL, método, necesita un ingreso existente) → {usuario: código}
MATRIX = [
    (("entries:list", "get", False), {ANON: LOGIN, NO_ROLE: 403, OP: 200, SUP: 200, ADM: 200, ROOT: 200}),
    (("entries:create", "get", False), {ANON: LOGIN, NO_ROLE: 403, OP: 200, SUP: 200, ADM: 200, ROOT: 200}),
    (("entries:detail", "get", True), {ANON: LOGIN, NO_ROLE: 403, OP: 200, SUP: 200, ADM: 200, ROOT: 200}),
    (("entries:export", "get", False), {ANON: LOGIN, NO_ROLE: 403, OP: 403, SUP: 200, ADM: 200, ROOT: 200}),
    (("entries:review", "post", True), {ANON: LOGIN, NO_ROLE: 403, OP: 403, SUP: 302, ADM: 302, ROOT: 302}),
    (("entries:ocr_plate", "post", False), {ANON: LOGIN, NO_ROLE: 403, OP: 400, SUP: 400, ADM: 400, ROOT: 400}),
    (("entries:ocr_container", "post", False), {ANON: LOGIN, NO_ROLE: 403, OP: 400, SUP: 400, ADM: 400, ROOT: 400}),
    (("analytics:dashboard", "get", False), {ANON: LOGIN, NO_ROLE: 403, OP: 403, SUP: 200, ADM: 200, ROOT: 200}),
    (("analytics:metrics", "get", False), {ANON: LOGIN, NO_ROLE: 403, OP: 403, SUP: 200, ADM: 200, ROOT: 200}),
    (("analytics:insights", "post", False), {ANON: LOGIN, NO_ROLE: 403, OP: 403, SUP: 200, ADM: 200, ROOT: 200}),
    (("analytics:ask", "post", False), {ANON: LOGIN, NO_ROLE: 403, OP: 403, SUP: 200, ADM: 200, ROOT: 200}),
    (("staff:list", "get", False), {ANON: LOGIN, NO_ROLE: 403, OP: 403, SUP: 403, ADM: 200, ROOT: 200}),
    (("staff:create", "get", False), {ANON: LOGIN, NO_ROLE: 403, OP: 403, SUP: 403, ADM: 200, ROOT: 200}),
    (("staff:edit", "get", True), {ANON: LOGIN, NO_ROLE: 403, OP: 403, SUP: 403, ADM: 200, ROOT: 200}),
    (("home", "get", False), {ANON: LOGIN, NO_ROLE: 302, OP: 302, SUP: 302, ADM: 302, ROOT: 302}),
    (("accounts:login", "get", False), {ANON: 200, NO_ROLE: 302, OP: 302, SUP: 302, ADM: 302, ROOT: 302}),
]
CASES = [(url, method, needs_obj, who, code) for (url, method, needs_obj), codes in MATRIX for who, code in codes.items()]


@pytest.fixture
def actors(seeded):
    return {
        NO_ROLE: make_user("norole", None),
        OP: make_user("op", Role.OPERATOR),
        SUP: make_user("sup", Role.SUPERVISOR),
        ADM: make_user("adm", Role.ADMIN),
        ROOT: User.objects.create_superuser("root", password="x"),
    }


@pytest.mark.parametrize("url,method,needs_obj,who,code", CASES, ids=[f"{c[0]}-{c[3]}" for c in CASES])
def test_access_matrix(client, actors, url, method, needs_obj, who, code):
    if who != ANON:
        client.force_login(actors[who])
    args = []
    if needs_obj:
        args = [actors[OP].id] if url == "staff:edit" else [register(actors[OP])]
    kwargs = {}
    if url == "analytics:ask":
        kwargs = {"data": json.dumps({"question": "¿Cuántos camiones hubo?", "range": "today"}), "content_type": "application/json"}
    response = getattr(client, method)(reverse(url, args=args), **kwargs)
    assert response.status_code == code
    if code == LOGIN and who == ANON:
        assert response["Location"].startswith(reverse("accounts:login"))


@pytest.mark.parametrize(
    "url,method",
    [("entries:review", "get"), ("entries:ocr_plate", "get"), ("analytics:insights", "get"), ("analytics:ask", "get"),
     ("entries:export", "post"), ("analytics:metrics", "post"), ("accounts:logout", "get")],
)
def test_wrong_http_method_is_405(client, actors, url, method):
    client.force_login(actors[ADM])
    args = [1] if url == "entries:review" else []
    assert getattr(client, method)(reverse(url, args=args)).status_code == 405


@pytest.mark.parametrize("who,target", [(OP, "entries:create"), (NO_ROLE, "entries:create"), (SUP, "analytics:dashboard"),
                                        (ADM, "analytics:dashboard"), (ROOT, "analytics:dashboard")])
def test_home_redirects_by_role(client, actors, who, target):
    client.force_login(actors[who])
    assert client.get(reverse("home"))["Location"] == reverse(target)


def test_forbidden_page_is_friendly(client, actors):
    client.force_login(actors[OP])
    response = client.get(reverse("analytics:dashboard"))
    assert response.status_code == 403 and "No tiene permiso" in response.content.decode()


def test_not_found_page_is_friendly(client, actors):
    client.force_login(actors[ADM])
    response = client.get(reverse("entries:detail", args=[999999]))
    assert response.status_code == 404 and "Página no encontrada" in response.content.decode()
