import pytest

from apps.entries.domain import iso6346
from apps.entries.domain.entities import EntryStatus, TruckEntry
from apps.entries.domain.exceptions import EntryAlreadyReviewed, InvalidContainerCode, InvalidPlate
from apps.entries.domain.parsers import ContainerCodeParser, PlateParser
from apps.entries.domain.value_objects import ContainerCode, Plate
from datetime import datetime


@pytest.mark.parametrize("code,ok", [("CSQU3054383", True), ("MSKU9070323", True), ("CSQU3054384", False)])
def test_iso6346_check_digit(code, ok):
    assert iso6346.is_valid(code) is ok


def test_iso6346_expected_digit():
    assert iso6346.compute_check_digit("CSQU305438") == 3


@pytest.mark.parametrize("code", ["CSQ3054383", "CSQX3054383", "CSQU305438", "1SQU3054383"])
def test_iso6346_bad_format(code):
    assert not iso6346.has_valid_format(code)


def test_container_code_normalizes_and_validates():
    assert ContainerCode.from_raw("csqu 305438-3").value == "CSQU3054383"


def test_container_code_format_vs_check_digit_errors():
    with pytest.raises(InvalidContainerCode) as fmt:
        ContainerCode("ABC")
    assert fmt.value.reason == "format"
    with pytest.raises(InvalidContainerCode) as chk:
        ContainerCode("CSQU3054384")
    assert chk.value.reason == "check_digit" and chk.value.expected_check_digit == 3


@pytest.mark.parametrize("raw,kind", [("abc 123", "vehicle"), ("R12345", "trailer"), ("s-98765", "trailer")])
def test_plate_valid(raw, kind):
    assert Plate.from_raw(raw).kind == kind


@pytest.mark.parametrize("raw", ["AB1234", "ABCD12", "123ABC", ""])
def test_plate_invalid(raw):
    with pytest.raises(InvalidPlate):
        Plate.from_raw(raw)


def test_value_objects_equal_by_value():
    assert Plate("ABC123") == Plate("ABC123")


@pytest.mark.parametrize(
    "lines,expected",
    [
        (["COLOMBIA", "SKX 482", "BOGOTA"], "SKX482"),
        (["SKX4B2"], "SKX482"),  # B en posición de dígito → 8
        (["5KX482"], "SKX482"),  # 5 en posición de letra → S
        (["R 12345"], "R12345"),
    ],
)
def test_plate_parser(lines, expected):
    result = PlateParser().parse(lines)
    assert result.is_valid and result.candidate == expected


def test_plate_parser_confusions_o_zero():
    assert PlateParser().parse(["ABC1O3"]).candidate == "ABC103"  # O → 0 en posición de dígito


def test_plate_parser_no_match_returns_raw():
    result = PlateParser().parse(["HOLA MUNDO"])
    assert not result.is_valid and result.candidate == "" and result.raw_text == "HOLA MUNDO"


def test_parsers_prefer_whole_line_over_window_inside_other_text():
    lines = ["CSQU 305438 3", "SKX 482"]  # «SQU305» dentro del contenedor parece placa; la línea completa gana
    assert PlateParser().parse(lines).candidate == "SKX482"
    assert ContainerCodeParser().parse(lines).candidate == "CSQU3054383"


def test_container_parser_valid_across_spaces():
    result = ContainerCodeParser().parse(["CSQU 305438 3"])
    assert result.is_valid and result.candidate == "CSQU3054383"


def test_container_parser_confusion_zero_o():
    result = ContainerCodeParser().parse(["MSKU9O70323"])  # O en posición de dígito
    assert result.is_valid and result.candidate == "MSKU9070323"


def test_container_parser_bad_check_digit_is_fallback_not_valid():
    result = ContainerCodeParser().parse(["CSQU3054384"])
    assert not result.is_valid and result.candidate == "CSQU3054384"


def test_entry_register_status_and_review():
    entry = TruckEntry.register(questionnaire_id=1, created_by_id=2, plate="ABC123", container_code="CSQU3054384", container_iso_valid=False)
    assert entry.status is EntryStatus.WITH_OBSERVATION and entry.had_observation
    entry.mark_reviewed(5, " ok ", datetime(2026, 1, 1))
    assert entry.status is EntryStatus.REVIEWED and entry.review_comment == "ok"
    with pytest.raises(EntryAlreadyReviewed):
        entry.mark_reviewed(5, "", datetime(2026, 1, 1))
