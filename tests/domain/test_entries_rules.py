"""Unitarias: reglas del dominio de ingresos (ISO 6346, placas, normalización, parsers OCR, entidad)."""
from datetime import datetime

import pytest

from apps.entries.domain import iso6346
from apps.entries.domain.entities import EntryStatus, TruckEntry
from apps.entries.domain.exceptions import EntryValidationError, InvalidContainerCode
from apps.entries.domain.parsers import DIGIT_TO_LETTER, LETTER_TO_DIGIT, ContainerCodeParser, PlateParser
from apps.entries.domain.value_objects import ContainerCode, Plate, normalize


# -- ISO 6346 ------------------------------------------------------------------------------------
def test_letter_values_skip_multiples_of_eleven():
    assert all(v % 11 for v in iso6346.LETTER_VALUES.values())
    assert len(iso6346.LETTER_VALUES) == 26


@pytest.mark.parametrize("category", ["U", "J", "Z"])
def test_valid_equipment_categories(category):
    base = f"ABC{category}123456"
    assert iso6346.has_valid_format(base + str(iso6346.compute_check_digit(base)))


@pytest.mark.parametrize("category", ["A", "R", "1"])
def test_invalid_equipment_categories(category):
    assert not iso6346.has_valid_format(f"ABC{category}1234565")


def test_lowercase_is_not_valid_format_without_normalizing():
    assert not iso6346.has_valid_format("csqu3054383")
    assert iso6346.is_valid(normalize("csqu3054383"))


def test_check_digit_ten_maps_to_zero():
    """Si la suma módulo 11 da 10, el dígito de control es 0 (regla de la norma)."""
    found = next(
        f"AAAU{n:06d}" for n in range(100000) if sum(
            (iso6346.LETTER_VALUES[c] if c.isalpha() else int(c)) * 2**i for i, c in enumerate(f"AAAU{n:06d}")
        ) % 11 == 10
    )
    assert iso6346.compute_check_digit(found) == 0
    assert iso6346.is_valid(found + "0")


# -- normalización y value objects ---------------------------------------------------------------
@pytest.mark.parametrize(
    "raw,expected",
    [("abc 123", "ABC123"), ("abc-123", "ABC123"), ("a.b.c 1-2-3", "ABC123"), ("\tabc\n123 ", "ABC123"), ("", ""), (None, "")],
)
def test_normalize(raw, expected):
    assert normalize(raw) == expected


@pytest.mark.parametrize("raw", ["S12345", "r 12345", "XYZ-999"])
def test_plate_accepts_vehicle_and_trailer(raw):
    plate = Plate.from_raw(raw)
    assert str(plate) == normalize(raw)


@pytest.mark.parametrize("raw", ["T12345", "R1234", "R123456", "ABC1234", "ÑBC123"])
def test_plate_rejects(raw):
    with pytest.raises(Exception):
        Plate.from_raw(raw)


def test_container_code_exposes_check_digit_and_str():
    code = ContainerCode.from_raw("MSKU 907032-3")
    assert code.check_digit == 3 and str(code) == "MSKU9070323"


def test_invalid_container_code_defaults():
    exc = InvalidContainerCode("x")
    assert exc.reason == "format" and exc.expected_check_digit is None


def test_entry_validation_error_carries_field_errors():
    exc = EntryValidationError({1: "a", "__all__": "b"})
    assert exc.errors[1] == "a" and "validación" in str(exc)


# -- parsers OCR ---------------------------------------------------------------------------------
def test_confusion_tables_are_inverse():
    assert {v: k for k, v in LETTER_TO_DIGIT.items()} == DIGIT_TO_LETTER


@pytest.mark.parametrize("line,expected", [("ABC1Z3", "ABC123"), ("ABC 1S3", "ABC153"), ("ABCI23", "ABC123")])
def test_plate_parser_corrects_letters_in_digit_positions(line, expected):
    assert PlateParser().parse([line]).candidate == expected


def test_plate_parser_corrects_digits_in_letter_positions():
    assert PlateParser().parse(["8KX482"]).candidate == "BKX482"
    assert PlateParser().parse(["1KX482"]).candidate == "IKX482"


def test_plate_parser_joins_split_lines():
    result = PlateParser().parse(["SKX", "482"])
    assert result.is_valid and result.candidate == "SKX482"


def test_plate_parser_trailer_s():
    assert PlateParser().parse(["S 98765"]).candidate == "S98765"


@pytest.mark.parametrize("lines", [[], [""], ["   ", "\t"]])
def test_parsers_handle_empty_input(lines):
    for parser in (PlateParser(), ContainerCodeParser()):
        result = parser.parse(lines)
        assert (result.raw_text, result.candidate, result.is_valid) == ("", "", False)


def test_container_parser_prefers_a_valid_code_over_an_earlier_bad_digit():
    result = ContainerCodeParser().parse(["CSQU3054384", "MSKU9070323"])
    assert result.is_valid and result.candidate == "MSKU9070323"


def test_container_parser_finds_code_inside_longer_text():
    result = ContainerCodeParser().parse(["CONTENEDOR: CSQU3054383 TARA 2200KG"])
    assert result.is_valid and result.candidate == "CSQU3054383"


def test_raw_text_joins_trimmed_lines():
    assert PlateParser().parse(["  COLOMBIA ", "", "SKX 482"]).raw_text == "COLOMBIA SKX 482"


# -- entidad TruckEntry --------------------------------------------------------------------------
def test_register_with_valid_iso_is_registered_without_observation():
    entry = TruckEntry.register(questionnaire_id=1, created_by_id=1, plate="ABC123", container_code="CSQU3054383", container_iso_valid=True)
    assert entry.status is EntryStatus.REGISTERED and not entry.had_observation and entry.id is None


def test_review_from_observation_state_records_reviewer_and_time():
    entry = TruckEntry.register(questionnaire_id=1, created_by_id=1, plate="ABC123", container_code="X", container_iso_valid=False)
    when = datetime(2026, 3, 1, 10, 0)
    entry.mark_reviewed(42, "  revisar sello  ", when)
    assert (entry.status, entry.reviewed_by_id, entry.reviewed_at, entry.review_comment) == (EntryStatus.REVIEWED, 42, when, "revisar sello")
    assert entry.had_observation  # la observación histórica se conserva


def test_status_values_are_stable_strings():
    assert [s.value for s in EntryStatus] == ["registrado", "con_observacion", "revisado"]
