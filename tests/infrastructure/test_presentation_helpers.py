"""Adaptadores primarios sin HTTP: view-models del formulario, filtros, KPIs, rangos y filtros de plantilla."""
from datetime import date

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import QueryDict
from django.utils.datastructures import MultiValueDict

from apps.analytics.application.dtos import ChartPoint, DashboardMetricsDTO
from apps.analytics.infrastructure.views import _fmt_delta, _parse_range, build_kpis
from apps.core.templatetags.ui import container_fmt
from apps.entries.infrastructure.forms import build_field_viewmodels, parse_entry_command, parse_filters
from tests.application.conftest import (
    BOXES, CONTAINER, HAS_CONTAINER, NOV_PHOTO, NOV_TYPE, NOVELTY, PLATE, SUPPLIER, build_questionnaire,
)


def qd(data: dict) -> QueryDict:
    q = QueryDict(mutable=True)
    for key, value in data.items():
        q.setlist(key, value if isinstance(value, list) else [value])
    return q


# -- formulario dinámico ---------------------------------------------------------------------------
def by_id(vms):
    return {vm.id: vm for vm in vms}


def test_empty_form_hides_dependent_questions_and_wires_ocr():
    vms = by_id(build_field_viewmodels(build_questionnaire()))
    assert vms[CONTAINER].hidden and vms[NOV_TYPE].hidden and not vms[PLATE].hidden
    assert (vms[PLATE].ocr_kind, vms[PLATE].ocr_url) == ("plate", "/entries/ocr/plate/")
    assert (vms[CONTAINER].ocr_kind, vms[CONTAINER].ocr_url) == ("container", "/entries/ocr/container/")
    assert vms[PLATE].name == f"q_{PLATE}" and vms[PLATE].photo_name == f"photo_{PLATE}"


def test_posted_values_are_kept_and_branches_open():
    post = qd({f"q_{HAS_CONTAINER}": "true", f"q_{NOVELTY}": "true", f"q_{NOV_TYPE}": ["pests"], f"q_{SUPPLIER}": "caribe"})
    vms = by_id(build_field_viewmodels(build_questionnaire(), post, {SUPPLIER: "mal"}))
    assert not vms[CONTAINER].hidden and not vms[NOV_TYPE].hidden
    assert vms[HAS_CONTAINER].bool_yes and not vms[HAS_CONTAINER].bool_no
    assert [c.selected for c in vms[NOV_TYPE].choices] == [True, False]
    assert vms[SUPPLIER].value == "caribe" and [c.selected for c in vms[SUPPLIER].choices] == [False, True]
    assert vms[SUPPLIER].error == "mal"


@pytest.mark.parametrize("code,show", [("CSQU3054384", True), ("CSQU3054383", False), ("XYZ", False)])
def test_iso_confirmation_checkbox_only_for_bad_check_digit(code, show):
    post = qd({f"q_{HAS_CONTAINER}": "true", f"q_{CONTAINER}": code, "confirm_iso": "1"})
    vm = by_id(build_field_viewmodels(build_questionnaire(), post))[CONTAINER]
    assert vm.show_confirm is show and vm.confirm_checked


def test_parse_entry_command_reads_lists_files_and_confirmation():
    post = qd({f"q_{PLATE}": "abc123", f"q_{NOV_TYPE}": ["pests", "humidity"], "confirm_iso": "on"})
    files = MultiValueDict({
        f"photo_{PLATE}": [SimpleUploadedFile("p.jpg", b"img")],
        f"photo_{NOV_PHOTO}": [SimpleUploadedFile("vacia.jpg", b"")],  # vacía: se ignora
        f"photo_{BOXES}": [SimpleUploadedFile("x.jpg", b"img")],       # pregunta sin foto: se ignora
    })
    command = parse_entry_command(post, files, build_questionnaire(), user_id=4)
    assert command.user_id == 4 and command.confirm_iso_override
    assert command.answers[PLATE] == "abc123" and command.answers[NOV_TYPE] == ["pests", "humidity"]
    assert command.answers[BOXES] is None
    assert [(e.question_id, e.filename, e.content) for e in command.evidences] == [(PLATE, "p.jpg", b"img")]


def test_parse_filters():
    filters, raw = parse_filters(qd({"date_from": "2026-01-01", "date_to": "basura", "plate": " abc ", "user": "7", "novelty": "yes"}))
    assert filters.date_from == date(2026, 1, 1) and filters.date_to is None
    assert filters.plate == "abc" and filters.user_id == 7 and filters.novelty == "yes"
    assert raw["date_to"] == "basura" and raw["container"] == ""


@pytest.mark.parametrize("user", ["", "abc", "-1", "1.5"])
def test_parse_filters_ignores_non_numeric_user(user):
    assert parse_filters(qd({"user": user}))[0].user_id is None


# -- tablero ---------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "value,expected",
    [(None, ("", "none")), (0.0, ("= 0 %", "flat")), (0.4, ("= 0 %", "flat")), (-0.4, ("= 0 %", "flat")),
     (12.0, ("+ 12 %", "up")), (-30.0, ("− 30 %", "down"))],
)
def test_fmt_delta(value, expected):
    assert _fmt_delta(value) == expected


def dto(**over):
    base = dict(range_key="k", range_label="Hoy", days=1, trucks=1234, boxes=5, pallets=0, witness_samples=0, novelty_entries=0,
                containers_total=0, containers_iso_valid=0, iso_valid_pct=None, seals_not_ok=0, pending_review=0,
                by_hour=[ChartPoint("00h", 0)])
    base.update(over)
    return DashboardMetricsDTO(**base)


def test_kpis_formatting_and_tones():
    kpis = {k["title"]: k for k in build_kpis(dto(novelty_entries=10, seals_not_ok=1, iso_valid_pct=80.0, containers_total=5,
                                                  containers_iso_valid=4, deltas={"novelty_entries": 50.0, "trucks": -10.0}))}
    assert kpis["Camiones ingresados"]["value"] == "1.234" and kpis["Camiones ingresados"]["delta_tone"] == "neutral"
    novelty = kpis["Ingresos con novedad"]
    assert novelty["tone"] == "warning" and novelty["delta_tone"] == "bad" and novelty["hint"] == "1 % de los ingresos"
    assert kpis["Contenedores ISO válidos"]["value"] == "80 %" and kpis["Contenedores ISO válidos"]["tone"] == "danger"
    assert kpis["Sellos no intactos"]["tone"] == "danger" and len(kpis) == 8


def test_kpis_without_trucks_or_containers():
    kpis = {k["title"]: k for k in build_kpis(dto(trucks=0))}
    assert kpis["Ingresos con novedad"]["hint"] == "" and kpis["Contenedores ISO válidos"]["value"] == "—"
    assert kpis["Contenedores ISO válidos"]["hint"] == "Sin contenedores"


def test_novelty_going_down_is_good_news():
    kpi = next(k for k in build_kpis(dto(deltas={"novelty_entries": -20.0})) if k["title"] == "Ingresos con novedad")
    assert kpi["delta_tone"] == "good"


@pytest.mark.parametrize(
    "params,preset,days,error",
    [({}, "today", 1, ""), ({"range": "7d"}, "7d", 7, ""), ({"range": "hack"}, "today", 1, ""),
     ({"range": "custom", "start": "2026-01-01", "end": "2026-01-10"}, "custom", 10, ""),
     ({"range": "custom", "start": "2026-02-01", "end": "2026-01-01"}, "today", 1, "posterior")],
)
def test_parse_range(params, preset, days, error):
    got_preset, date_range, message = _parse_range(params)
    assert got_preset == preset and date_range.days == days and error in message
    assert bool(message) is bool(error)


# -- filtro de plantilla ---------------------------------------------------------------------------
def test_container_fmt_highlights_check_digit():
    assert str(container_fmt("CSQU3054383")) == 'CSQU 305438 <span class="cd">3</span>'


@pytest.mark.parametrize("value,expected", [("", ""), (None, ""), ("ABC", "ABC"), (" CSQU3054383 ", 'CSQU 305438 <span class="cd">3</span>')])
def test_container_fmt_other_values(value, expected):
    assert str(container_fmt(value)) == expected


def test_container_fmt_escapes_html():
    assert "<script>" not in str(container_fmt("<script>x11"))  # 11 caracteres: pasa por format_html
