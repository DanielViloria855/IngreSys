"""Funcional: pantallas de ingresos (registro, histórico, detalle, revisión, CSV y OCR) con el cliente de Django."""
import csv
import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.entries.infrastructure import container
from apps.entries.infrastructure.models import TruckEntry
from apps.entries.infrastructure.ocr.fake_ocr_adapter import FakeOcrAdapter
from apps.questionnaire.infrastructure.models import Questionnaire
from tests.factories import BAD_DIGIT_CONTAINER, VALID_CONTAINER, jpeg_bytes, post_data, questions_by_tag, register

pytestmark = pytest.mark.django_db


def html(response):
    return response.content.decode()


# -- registro --------------------------------------------------------------------------------------
def test_create_success_redirects_to_detail_with_message(client, operator):
    client.force_login(operator)
    response = client.post(reverse("entries:create"), post_data(), follow=True)
    entry = TruckEntry.objects.get()
    assert response.redirect_chain[-1][0] == reverse("entries:detail", args=[entry.id])
    assert "Ingreso registrado correctamente." in html(response)


def test_create_with_container_and_novelty_photo(client, operator):
    client.force_login(operator)
    tags = questions_by_tag()
    data = post_data(has_container="true", container_code="csqu 305438 3", seal_number="S-1", seal_ok="true",
                     has_novelty="true", novelty_type=["pests", "humidity"], novelty_description="húmedo")
    data[f"photo_{tags['novelty_photo'].id}"] = SimpleUploadedFile("n.jpg", jpeg_bytes(), "image/jpeg")
    data[f"photo_{tags['container_code'].id}"] = SimpleUploadedFile("c.png", jpeg_bytes(), "image/png")
    assert client.post(reverse("entries:create"), data).status_code == 302
    entry = TruckEntry.objects.get()
    assert entry.container_code == VALID_CONTAINER and entry.status == "registrado"
    assert sorted(entry.evidences.values_list("kind", flat=True)) == ["container", "novelty"]


def test_create_bad_iso_shows_confirmation_then_saves_with_observation(client, operator):
    client.force_login(operator)
    data = post_data(has_container="true", container_code=BAD_DIGIT_CONTAINER, seal_number="1", seal_ok="true")
    first = client.post(reverse("entries:create"), data)
    page = html(first)
    assert first.status_code == 422 and "esperado 3" in page and 'name="confirm_iso"' in page
    assert "data-ocr-confirm hidden" not in page  # la casilla de confirmación se muestra
    assert f'value="{BAD_DIGIT_CONTAINER}"' in page  # el valor escrito se conserva
    second = client.post(reverse("entries:create"), dict(data, confirm_iso="1"))
    assert second.status_code == 302 and TruckEntry.objects.get().status == "con_observacion"


def test_create_errors_keep_branch_open_and_warn_about_lost_photos(client, operator):
    client.force_login(operator)
    tags = questions_by_tag()
    data = post_data(has_novelty="true", plate="MAL")
    data[f"photo_{tags['plate'].id}"] = SimpleUploadedFile("p.jpg", jpeg_bytes(), "image/jpeg")
    response = client.post(reverse("entries:create"), data)
    page = html(response)
    assert response.status_code == 422 and "Revise 3 campos marcados" in page  # placa + tipo + descripción de novedad
    assert "Las fotos no se conservan" in page and "Placa inválida" in page
    assert TruckEntry.objects.count() == 0


def test_create_rejects_disallowed_file_type(client, operator):
    client.force_login(operator)
    data = post_data()
    data[f"photo_{questions_by_tag()['plate'].id}"] = SimpleUploadedFile("virus.exe", b"MZ", "application/octet-stream")
    response = client.post(reverse("entries:create"), data)
    assert response.status_code == 422 and "Formato no permitido" in html(response)


def test_create_without_active_questionnaire(client, operator):
    Questionnaire.objects.update(is_active=False)
    client.force_login(operator)
    for response in (client.get(reverse("entries:create")), client.post(reverse("entries:create"), {})):
        assert response.status_code == 200 and "El formulario aún no está configurado" in html(response)
        assert "Configurar cuestionario" not in html(response)  # solo el administrador ve el atajo


def test_admin_sees_setup_shortcut(client, administrator):
    Questionnaire.objects.update(is_active=False)
    client.force_login(administrator)
    assert "Configurar cuestionario" in html(client.get(reverse("entries:create")))


def test_create_form_renders_every_question_type(client, operator):
    client.force_login(operator)
    page = html(client.get(reverse("entries:create")))
    for marker in ('data-q-type="plate_ocr"', 'data-q-type="container_ocr"', 'data-q-type="boolean"', 'data-q-type="single_choice"',
                   'data-q-type="multi_choice"', 'data-q-type="number"', 'data-q-type="text"', 'data-q-type="photo"'):
        assert marker in page
    assert page.count("data-required") >= 10 and "data-depends-on" in page


# -- histórico -------------------------------------------------------------------------------------
def test_list_empty_states(client, supervisor):
    client.force_login(supervisor)
    assert "Aún no hay ingresos registrados" in html(client.get(reverse("entries:list")))
    assert "Ningún registro coincide" in html(client.get(reverse("entries:list"), {"plate": "zzz"}))


def test_list_pagination_and_bad_page_numbers(client, supervisor, operator):
    for _ in range(23):
        register(operator)
    client.force_login(supervisor)
    page2 = html(client.get(reverse("entries:list"), {"page": 2}))
    assert "página 2 de 2" in page2 and page2.count('class="row-link"') == 3
    for bad in ("abc", "-5", "0", "999"):
        assert client.get(reverse("entries:list"), {"page": bad}).status_code == 200


def test_list_filters_are_kept_in_links(client, supervisor, operator):
    for _ in range(21):
        register(operator, plate="AAA111")
    client.force_login(supervisor)
    page = html(client.get(reverse("entries:list"), {"plate": "aaa", "status": "registrado"}))
    assert "plate=aaa&amp;status=registrado&amp;page=2" in page
    assert reverse("entries:export") + "?plate=aaa&amp;status=registrado" in page


def test_operator_list_has_no_user_filter_or_export(client, operator):
    client.force_login(operator)
    page = html(client.get(reverse("entries:list")))
    assert "Sus registros" in page and "Exportar CSV" not in page


# -- detalle y revisión -----------------------------------------------------------------------------
def test_detail_shows_iso_digits_answers_and_review_form(client, supervisor, operator):
    entry_id = register(operator, has_container="true", container_code=BAD_DIGIT_CONTAINER, seal_number="1", seal_ok="true",
                        confirm=True, driver_name="Ramiro")
    client.force_login(supervisor)
    page = html(client.get(reverse("entries:detail", args=[entry_id])))
    assert "Dígito leído 4 · esperado 3" in page and "Ramiro" in page and "Marcar como revisado" in page
    assert 'CSQU 305438 <span class="cd">4</span>' in page and "quedó con observación" in page


def test_operator_detail_has_no_review_form(client, operator):
    client.force_login(operator)
    page = html(client.get(reverse("entries:detail", args=[register(operator)])))
    assert "Pendiente de revisión" in page and "Marcar como revisado" not in page


def test_review_twice_warns_and_missing_is_404(client, supervisor, operator):
    entry_id = register(operator)
    client.force_login(supervisor)
    client.post(reverse("entries:review", args=[entry_id]), {"comment": "primera"})
    again = client.post(reverse("entries:review", args=[entry_id]), {"comment": "segunda"}, follow=True)
    assert "ya fue revisado" in html(again)
    assert TruckEntry.objects.get(pk=entry_id).review_comment == "primera"
    assert client.post(reverse("entries:review", args=[424242])).status_code == 404


# -- exportación CSV -------------------------------------------------------------------------------
def read_csv(response):
    body = response.content.decode("utf-8")
    assert body.startswith("﻿")
    return list(csv.reader(io.StringIO(body[1:])))


def test_csv_export_content_and_filters(client, supervisor, operator):
    register(operator, plate="AAA111", has_novelty="true", novelty_type=["pests"], novelty_description="x")
    register(operator, plate="BBB222", has_container="true", container_code=BAD_DIGIT_CONTAINER, seal_number="1",
             seal_ok="true", confirm=True)
    client.force_login(supervisor)
    response = client.get(reverse("entries:export"))
    assert response["Content-Type"] == "text/csv; charset=utf-8" and "ingresos.csv" in response["Content-Disposition"]
    header, *rows = read_csv(response)
    assert header[:4] == ["ID", "Fecha", "Placa", "Contenedor"] and len(rows) == 2
    by_plate = {r[2]: r for r in rows}
    assert by_plate["BBB222"][4] == "No" and by_plate["BBB222"][7] == "Con observación" and by_plate["BBB222"][8] == "No"
    assert by_plate["AAA111"][4] == "" and by_plate["AAA111"][8] == "Sí" and by_plate["AAA111"][5] == "Otro"
    assert [r[2] for r in read_csv(client.get(reverse("entries:export"), {"plate": "bbb"}))[1:]] == ["BBB222"]


# -- OCR -------------------------------------------------------------------------------------------
def img():
    return SimpleUploadedFile("f.jpg", b"img", "image/jpeg")


@pytest.mark.parametrize(
    "lines,url,status",
    [(["HOLA"], "entries:ocr_plate", "verify"), (["HOLA"], "entries:ocr_container", "verify"),
     (["12 34"], "entries:ocr_plate", "verify")],
)
def test_ocr_unrecognized(client, operator, monkeypatch, lines, url, status):
    monkeypatch.setattr(container, "get_ocr_service", lambda: FakeOcrAdapter(lines))
    client.force_login(operator)
    body = client.post(reverse(url), {"image": img()}).json()
    assert body["status"] == status and body["is_valid"] is False and body["candidate"] == ""


def test_ocr_plate_inside_longer_text_is_extracted(client, operator, monkeypatch):
    """Diseño: el parser busca ventanas, así que «ABC1234» (un carácter de más) devuelve «ABC123»."""
    monkeypatch.setattr(container, "get_ocr_service", lambda: FakeOcrAdapter(["ABC1234"]))
    client.force_login(operator)
    assert client.post(reverse("entries:ocr_plate"), {"image": img()}).json()["candidate"] == "ABC123"


def test_ocr_empty_file_is_400(client, operator):
    client.force_login(operator)
    response = client.post(reverse("entries:ocr_plate"), {"image": SimpleUploadedFile("f.jpg", b"")})
    assert response.status_code == 400 and response.json() == {"error": "Adjunta una foto."}


def test_ocr_bad_image_with_real_preprocessing_gives_503(client, operator, settings, monkeypatch):
    """Con el adaptador de Google (cliente simulado) una foto ilegible responde 503 con mensaje claro."""
    from google.cloud import vision

    from apps.entries.infrastructure.ocr.google_vision_adapter import GoogleVisionOcrAdapter

    monkeypatch.setattr(vision, "ImageAnnotatorClient", lambda **kw: pytest.fail("no debería llamar a la API"))
    monkeypatch.setattr(container, "get_ocr_service", lambda: GoogleVisionOcrAdapter("k"))
    client.force_login(operator)
    response = client.post(reverse("entries:ocr_plate"), {"image": img()})
    assert response.status_code == 503 and "No se pudo leer la imagen" in response.json()["error"]
