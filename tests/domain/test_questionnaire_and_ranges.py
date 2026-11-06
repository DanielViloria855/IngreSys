"""Unitarias: cuestionario (tipos, opciones, visibilidad) y rango de fechas del tablero."""
from datetime import date
from decimal import Decimal

import pytest

from apps.analytics.domain.insight import Insight, InsightLevel
from apps.analytics.domain.metrics import MAX_DAYS, DateRange, InvalidDateRange
from apps.questionnaire.domain.entities import ChoiceOption, Question, QuestionType, Questionnaire
from apps.questionnaire.domain.visibility import VisibilityRule
from shared.domain.base import DomainError


# -- tipos y entidades -----------------------------------------------------------------------------
@pytest.mark.parametrize(
    "qtype,photo,ocr",
    [
        (QuestionType.TEXT, False, False), (QuestionType.NUMBER, False, False), (QuestionType.BOOLEAN, False, False),
        (QuestionType.SINGLE_CHOICE, False, False), (QuestionType.MULTI_CHOICE, False, False), (QuestionType.DATE, False, False),
        (QuestionType.PHOTO, True, False), (QuestionType.PLATE_OCR, True, True), (QuestionType.CONTAINER_OCR, True, True),
    ],
)
def test_question_type_capabilities(qtype, photo, ocr):
    assert (qtype.has_photo_input, qtype.is_ocr) == (photo, ocr)


@pytest.mark.parametrize("label,value", [("", "x"), ("x", ""), ("  ", "x"), ("x", "   ")])
def test_choice_option_requires_label_and_value(label, value):
    with pytest.raises(DomainError):
        ChoiceOption(1, label, value)


def test_choice_lookup_and_tag_lookup():
    q = Question(id=1, text="P", type=QuestionType.SINGLE_CHOICE, semantic_tag="supplier",
                 choices=(ChoiceOption(1, "Andina", "andina"),))
    assert q.choice_by_value("andina").label == "Andina"
    assert q.choice_by_value("ANDINA") is None  # el valor es exacto
    questionnaire = Questionnaire(id=1, name="x", questions=[q])
    assert questionnaire.question_by_tag("supplier") is q and questionnaire.question_by_tag("nope") is None


def test_insight_is_a_value():
    assert Insight(InsightLevel.INFO, "a", "b") == Insight(InsightLevel.INFO, "a", "b")


# -- visibilidad -----------------------------------------------------------------------------------
def q(id, order, dep=None, value=""):
    return Question(id=id, order=order, text=f"q{id}", type=QuestionType.TEXT, depends_on_id=dep, depends_on_value=value)


@pytest.mark.parametrize(
    "answer,expected,visible",
    [
        ("TRUE", "true", True), (" true ", "true", True), (True, "TRUE", True), ("false", "true", False),
        (Decimal("5"), "5", True), (5, "5", True), (("a", "b"), "b", True), ({"b"}, "B", True),
        ((), "x", False), ([], "x", False), ("", "x", False), (None, "x", False),
    ],
)
def test_visibility_value_matching(answer, expected, visible):
    assert VisibilityRule.is_visible(q(2, 2, dep=1, value=expected), {1: answer}) is visible


def test_visible_questions_are_returned_in_order_regardless_of_input_order():
    questions = [q(3, 3), q(1, 1), q(2, 2)]
    assert [x.id for x in VisibilityRule.visible_questions(questions, {})] == [1, 2, 3]


def test_child_ordered_before_its_parent_is_hidden():
    """La cascada se evalúa en orden: un hijo que aparece antes que su padre no puede verse."""
    questions = [q(1, 2), q(2, 1, dep=1, value="x")]
    assert [x.id for x in VisibilityRule.visible_questions(questions, {1: "x"})] == [1]


def test_dependency_on_missing_question_hides_child():
    assert VisibilityRule.visible_questions([q(2, 1, dep=99, value="x")], {99: "x"}) == []


# -- rango de fechas -------------------------------------------------------------------------------
TODAY = date(2026, 11, 5)


@pytest.mark.parametrize("preset,days", [("today", 1), ("7d", 7), ("30d", 30), ("desconocido", 1), ("", 1)])
def test_presets(preset, days):
    r = DateRange.from_preset(preset, TODAY)
    assert r.end == TODAY and r.days == days


def test_custom_range_and_key():
    r = DateRange.from_preset("custom", TODAY, "2026-01-01", "2026-01-31")
    assert r.days == 31 and r.key == "2026-01-01_2026-01-31"
    assert list(r.each_day())[0] == date(2026, 1, 1) and len(list(r.each_day())) == 31


@pytest.mark.parametrize("start,end", [("", ""), ("2026-13-01", "2026-12-31"), ("01/01/2026", "2026-01-02"), ("2026-02-01", "2026-01-01")])
def test_invalid_custom_ranges(start, end):
    with pytest.raises(InvalidDateRange):
        DateRange.from_preset("custom", TODAY, start, end)


def test_max_range_length():
    DateRange(date(2025, 1, 1), date(2025, 1, 1).replace(year=2026))  # 366 días: permitido
    with pytest.raises(InvalidDateRange):
        DateRange(date(2025, 1, 1), date(2026, 1, 2))
    assert MAX_DAYS == 366


def test_previous_of_single_day_is_yesterday():
    prev = DateRange(TODAY, TODAY).previous()
    assert (prev.start, prev.end) == (date(2026, 11, 4), date(2026, 11, 4))
