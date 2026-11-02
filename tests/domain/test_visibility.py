from apps.questionnaire.domain.entities import Question, QuestionType
from apps.questionnaire.domain.visibility import VisibilityRule


def q(id, order, dep=None, value="", type=QuestionType.TEXT):
    return Question(id=id, order=order, text=f"q{id}", type=type, depends_on_id=dep, depends_on_value=value)


def test_independent_question_always_visible():
    assert VisibilityRule.is_visible(q(1, 1), {})


def test_boolean_dependency():
    child = q(2, 2, dep=1, value="true")
    assert VisibilityRule.is_visible(child, {1: True})
    assert not VisibilityRule.is_visible(child, {1: False})
    assert not VisibilityRule.is_visible(child, {})


def test_multi_choice_dependency():
    child = q(2, 2, dep=1, value="pests")
    assert VisibilityRule.is_visible(child, {1: ["odors", "pests"]})
    assert not VisibilityRule.is_visible(child, {1: ["odors"]})


def test_cascade_hides_grandchildren():
    questions = [q(1, 1, type=QuestionType.BOOLEAN), q(2, 2, dep=1, value="true"), q(3, 3, dep=2, value="x")]
    visible = VisibilityRule.visible_questions(questions, {1: False, 2: "x"})
    assert [x.id for x in visible] == [1]
    visible = VisibilityRule.visible_questions(questions, {1: True, 2: "x"})
    assert [x.id for x in visible] == [1, 2, 3]
