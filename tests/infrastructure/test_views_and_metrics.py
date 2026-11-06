import pytest
from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

from apps.entries.application.dtos import RegisterEntryCommand
from apps.entries.domain.exceptions import OcrUnavailable
from apps.entries.infrastructure import container
from apps.entries.infrastructure.models import TruckEntry
from apps.entries.infrastructure.ocr.fake_ocr_adapter import FakeOcrAdapter
from apps.questionnaire.infrastructure.container import get_questionnaire_repository
from apps.analytics.infrastructure import container as analytics_container
from apps.analytics.domain.metrics import DateRange
from shared.domain.roles import Role

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def seeded(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    call_command("seed_roles", verbosity=0)
    call_command("seed_questionnaire", verbosity=0)


def make_user(username, role, **extra):
    user = User.objects.create_user(username, password="x-pass-123", **extra)
    user.groups.add(Group.objects.get(name=role.value))
    return user


@pytest.fixture
def operator(): return make_user("op1", Role.OPERATOR)


@pytest.fixture
def operator2(): return make_user("op2", Role.OPERATOR)


@pytest.fixture
def supervisor(): return make_user("sup", Role.SUPERVISOR)


@pytest.fixture
def admin_user(): return make_user("adm", Role.ADMIN)


def answers_for(**by_tag):
    questionnaire = get_questionnaire_repository().get_active()
    tags = {q.semantic_tag: q for q in questionnaire.questions}
    base = {"plate": "SKX482", "driver_name": "Luis", "driver_id": "123", "supplier": "otro", "has_container": "false",
            "cargo_type": "boxes", "vehicle_condition": "good", "has_novelty": "false"}
    base.update(by_tag)
    return {tags[t].id: v for t, v in base.items()}


def register(user, **by_tag):
    return container.register_truck_entry().execute(RegisterEntryCommand(user.id, answers_for(**by_tag)))


# -- acceso y roles ------------------------------------------------------------------------------
def test_login_required_everywhere(client):
    for name in ("entries:list", "entries:create", "analytics:dashboard", "staff:list"):
        response = client.get(reverse(name))
        assert response.status_code == 302 and "/accounts/login/" in response["Location"]


def test_login_page_and_redirects_by_role(client, operator, supervisor):
    assert client.get(reverse("accounts:login")).status_code == 200
    client.force_login(operator)
    assert client.get("/").url == reverse("entries:create")
    client.force_login(supervisor)
    assert client.get("/").url == reverse("analytics:dashboard")


def test_operator_cannot_open_dashboard_staff_or_review(client, operator):
    client.force_login(operator)
    assert client.get(reverse("analytics:dashboard")).status_code == 403
    assert client.get(reverse("analytics:metrics")).status_code == 403
    assert client.get(reverse("staff:list")).status_code == 403
    assert client.post(reverse("entries:review", args=[1])).status_code == 403


def test_operator_sees_only_own_entries(client, operator, operator2):
    mine, theirs = register(operator, plate="AAA111"), register(operator2, plate="BBB222")
    client.force_login(operator)
    html = client.get(reverse("entries:list")).content.decode()
    assert "AAA111" in html and "BBB222" not in html
    assert client.get(reverse("entries:detail", args=[mine])).status_code == 200
    assert client.get(reverse("entries:detail", args=[theirs])).status_code == 404


def test_supervisor_sees_all_filters_and_reviews(client, operator, operator2, supervisor):
    a, b = register(operator, plate="AAA111"), register(operator2, plate="BBB222")
    client.force_login(supervisor)
    html = client.get(reverse("entries:list")).content.decode()
    assert "AAA111" in html and "BBB222" in html
    only = client.get(reverse("entries:list"), {"plate": "bbb"}).content.decode()
    assert "BBB222" in only and "AAA111" not in only
    assert client.post(reverse("entries:review", args=[a]), {"comment": "todo bien"}).status_code == 302
    assert TruckEntry.objects.get(pk=a).status == "revisado"
    assert "Revisado" in client.get(reverse("entries:detail", args=[a])).content.decode()
    assert client.get(reverse("entries:export")).content.decode().startswith("﻿ID,")


# -- formulario dinámico por la vista ---------------------------------------------------------------------
def test_create_view_renders_dynamic_form_and_registers(client, operator):
    client.force_login(operator)
    page = client.get(reverse("entries:create")).content.decode()
    assert "Foto y placa del vehículo" in page and 'data-ocr-kind="plate"' in page
    questionnaire = get_questionnaire_repository().get_active()
    tags = {q.semantic_tag: q.id for q in questionnaire.questions}
    data = {f"q_{tags['plate']}": "skx482", f"q_{tags['driver_name']}": "Luis", f"q_{tags['driver_id']}": "99",
            f"q_{tags['supplier']}": "otro", f"q_{tags['has_container']}": "false", f"q_{tags['cargo_type']}": "boxes",
            f"q_{tags['vehicle_condition']}": "good", f"q_{tags['has_novelty']}": "false",
            f"photo_{tags['plate']}": SimpleUploadedFile("placa.jpg", b"\xff\xd8\xff" + b"0" * 50, "image/jpeg")}
    response = client.post(reverse("entries:create"), data)
    assert response.status_code == 302
    entry = TruckEntry.objects.get()
    assert entry.plate == "SKX482" and entry.created_by == operator and entry.evidences.count() == 1


def test_create_view_shows_errors_and_keeps_values(client, operator):
    client.force_login(operator)
    response = client.post(reverse("entries:create"), {})
    assert response.status_code == 422 and "Este campo es obligatorio." in response.content.decode()
    assert TruckEntry.objects.count() == 0


# -- OCR (Vision/OCR mockeado) ----------------------------------------------------------------------------
def test_ocr_endpoints_with_fake_service(client, operator, monkeypatch):
    client.force_login(operator)
    monkeypatch.setattr(container, "get_ocr_service", lambda: FakeOcrAdapter(["CSQU 305438 3", "SKX 482"]))
    img = lambda: SimpleUploadedFile("f.jpg", b"img", "image/jpeg")  # noqa: E731
    plate = client.post(reverse("entries:ocr_plate"), {"image": img()}).json()
    assert plate["candidate"] == "SKX482" and plate["status"] == "valid"
    cont = client.post(reverse("entries:ocr_container"), {"image": img()}).json()
    assert cont["candidate"] == "CSQU3054383" and cont["status"] == "valid"


def test_ocr_container_flags_invalid_iso_and_missing_image(client, operator, monkeypatch):
    client.force_login(operator)
    monkeypatch.setattr(container, "get_ocr_service", lambda: FakeOcrAdapter(["CSQU3054384"]))
    body = client.post(reverse("entries:ocr_container"), {"image": SimpleUploadedFile("f.jpg", b"i")}).json()
    assert body["status"] == "invalid" and body["expected_check_digit"] == 3
    assert client.post(reverse("entries:ocr_container"), {}).status_code == 400


def test_ocr_service_down_returns_friendly_503(client, operator, monkeypatch):
    class Down:
        def read_text(self, _):
            raise OcrUnavailable("sin servicio")

    client.force_login(operator)
    monkeypatch.setattr(container, "get_ocr_service", lambda: Down())
    response = client.post(reverse("entries:ocr_plate"), {"image": SimpleUploadedFile("f.jpg", b"i")})
    assert response.status_code == 503 and response.json()["error"] == "sin servicio"


# -- métricas agregadas -----------------------------------------------------------------------------------------
def test_dashboard_metrics_aggregates_seed_data(operator, supervisor, client):
    register(operator, boxes_count="100", pallets_count="10", witness_samples_count="2", has_novelty="true",
             novelty_type=["pests"], novelty_description="x", supplier="otro")
    register(operator, boxes_count="50", pallets_count="5", supplier="otro")
    register(operator, has_container="true", container_code="CSQU3054383", seal_number="1", seal_ok="false")
    today = timezone.localdate()
    m = analytics_container.get_dashboard_metrics().execute(DateRange(today, today))
    assert (m.trucks, m.boxes, m.pallets, m.witness_samples) == (3, 150, 15, 2)
    assert m.novelty_entries == 1 and m.seals_not_ok == 1 and m.pending_review == 3
    assert (m.containers_total, m.iso_valid_pct) == (1, 100.0)
    assert m.novelty_by_type[0].label == "Plagas" and m.novelty_by_type[0].value == 1
    assert m.top_suppliers[0].label == "Otro" and m.top_suppliers[0].value == 3
    assert sum(p.value for p in m.by_hour) == 3 and sum(p.value for p in m.by_day) == 3
    assert {p.label: p.value for p in m.status_breakdown}["Registrado"] == 3

    client.force_login(supervisor)
    page = client.get(reverse("analytics:dashboard"))
    assert page.status_code == 200 and "Camiones ingresados" in page.content.decode()
    assert client.get(reverse("analytics:metrics")).json()["trucks"] == 3


def test_insights_endpoint_uses_rules_and_cache(client, supervisor, operator):
    register(operator, has_novelty="true", novelty_type=["pests"], novelty_description="x")
    client.force_login(supervisor)
    first = client.post(reverse("analytics:insights"), {"range": "today"}).json()
    again = client.post(reverse("analytics:insights"), {"range": "today"}).json()
    assert first["insights"] and first["model_used"] == "Reglas automáticas"
    assert again["from_cache"] is True
    assert client.post(reverse("analytics:insights"), {"range": "custom", "start": "2026-02-01", "end": "2026-01-01"}).status_code == 400


# -- personal ------------------------------------------------------------------------------------------------------------
def test_admin_creates_and_deactivates_staff(client, admin_user):
    client.force_login(admin_user)
    data = {"username": "nuevo", "first_name": "Nora", "last_name": "Ruiz", "email": "", "role": "Operario", "document_id": "1",
            "position": "Portería", "phone": "", "password": "Clave-segura-2026", "is_active": "on"}
    assert client.post(reverse("staff:create"), data).status_code == 302
    user = User.objects.get(username="nuevo")
    assert user.groups.filter(name="Operario").exists() and user.profile.position == "Portería"
    edit = dict(data, password="", is_active="")
    assert client.post(reverse("staff:edit", args=[user.id]), edit).status_code == 302
    user.refresh_from_db()
    assert user.is_active is False
    self_edit = dict(data, username="adm", is_active="", role="Administrador")
    assert client.post(reverse("staff:edit", args=[admin_user.id]), self_edit).status_code == 200  # no puede desactivarse


def test_admin_role_can_edit_questionnaire_in_django_admin(client, admin_user):
    """Regresión: el rol Administrador (no superusuario) debe ver y editar el cuestionario en /admin/."""
    assert admin_user.is_staff is False  # make_user no marca is_staff; lo hace StaffForm / seed
    admin_user.is_staff = True
    admin_user.save()
    client.force_login(admin_user)
    for name in ("questionnaire_questionnaire_changelist", "questionnaire_question_changelist"):
        assert client.get(reverse(f"admin:{name}")).status_code == 200
    assert client.get(reverse("admin:questionnaire_question_add")).status_code == 200
    assert "Cuestionario dinámico" in client.get(reverse("admin:index")).content.decode()


def test_supervisor_cannot_edit_questionnaire(client, supervisor):
    supervisor.is_staff = True
    supervisor.save()
    client.force_login(supervisor)
    assert client.get(reverse("admin:questionnaire_question_changelist")).status_code == 403


# -- asistente del tablero ------------------------------------------------------------------------------
def _ask(client, payload):
    import json

    return client.post(reverse("analytics:ask"), data=json.dumps(payload), content_type="application/json")


def test_ask_endpoint_answers_with_rules_and_keeps_roles(client, supervisor, operator):
    register(operator, has_novelty="true", novelty_type=["pests"], novelty_description="x")
    client.force_login(operator)
    assert _ask(client, {"question": "hola"}).status_code == 403
    client.force_login(supervisor)
    body = _ask(client, {"question": "¿Cómo van las novedades?", "range": "today"}).json()
    assert "novedad" in body["answer"] and body["model_used"] == "Reglas automáticas" and body["fallback_used"] is False
    follow = _ask(client, {"question": "¿y el resumen?", "range": "today",
                           "history": [{"role": "user", "text": "hola"}, {"role": "assistant", "text": "buenas"}, {"role": "x", "text": "ignorado"}]})
    assert follow.status_code == 200


def test_ask_endpoint_validations_and_throttle(client, supervisor, settings):
    client.force_login(supervisor)
    assert _ask(client, {"question": "  "}).status_code == 400
    assert _ask(client, {"question": "x" * 600}).status_code == 400
    assert _ask(client, {"question": "ok", "range": "custom", "start": "2026-02-01", "end": "2026-01-01"}).status_code == 400
    assert client.post(reverse("analytics:ask"), data="no es json", content_type="application/json").status_code == 400
    from apps.analytics.infrastructure import views

    for _ in range(views.ASK_LIMIT):
        _ask(client, {"question": "resumen"})
    assert _ask(client, {"question": "resumen"}).status_code == 429


def test_ask_endpoint_gives_assistant_history_and_tomorrow_estimate(client, supervisor, operator):
    register(operator)
    client.force_login(supervisor)
    body = _ask(client, {"question": "¿Mañana será un día de mucho volumen?", "range": "today"}).json()
    # el endpoint le entrega la fecha y el historial de 30 días: responde sobre «mañana» y cita ese historial
    assert "Mañana es" in body["answer"] and "últimos 30 días" in body["answer"]
    recommend = _ask(client, {"question": "¿Qué me recomiendas hacer?", "range": "today"}).json()
    assert "Sugerencias" in recommend["answer"] or "mantener la operación" in recommend["answer"]
