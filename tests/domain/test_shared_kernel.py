"""Unitarias: núcleo compartido (Entity, ValueObject, Actor, Page, Role)."""
from dataclasses import FrozenInstanceError

import pytest

from apps.entries.domain.entities import TruckEntry
from apps.entries.domain.exceptions import InvalidPlate
from apps.entries.domain.value_objects import Plate
from apps.questionnaire.domain.entities import Question, QuestionType
from shared.application.actor import Actor
from shared.application.pagination import Page
from shared.domain.base import DomainError
from shared.domain.roles import Role


def entry(id=None, plate="ABC123"):
    e = TruckEntry.register(questionnaire_id=1, created_by_id=1, plate=plate, container_code="", container_iso_valid=True)
    e.id = id
    return e


class TestEntityIdentity:
    def test_same_id_same_type_are_equal_even_with_different_data(self):
        assert entry(5, "ABC123") == entry(5, "XYZ999")

    def test_different_ids_are_different(self):
        assert entry(5) != entry(6)

    def test_unsaved_entities_are_only_equal_to_themselves(self):
        a, b = entry(), entry()
        assert a == a and a != b

    def test_different_entity_types_with_same_id_are_different(self):
        question = Question(id=5, text="x", type=QuestionType.TEXT)
        assert entry(5) != question

    def test_hash_is_consistent_with_equality(self):
        assert len({entry(1), entry(1), entry(2)}) == 2
        unsaved = entry()
        assert unsaved in {unsaved}


class TestValueObject:
    def test_validates_on_construction(self):
        with pytest.raises(InvalidPlate):
            Plate("nope")

    def test_is_immutable(self):
        with pytest.raises(FrozenInstanceError):
            Plate("ABC123").value = "XYZ999"  # type: ignore[misc]

    def test_domain_errors_share_a_base(self):
        assert issubclass(InvalidPlate, DomainError)


@pytest.mark.parametrize(
    "role,sees_all,reviews",
    [(Role.ADMIN, True, True), (Role.SUPERVISOR, True, True), (Role.OPERATOR, False, False)],
)
def test_actor_permissions_by_role(role, sees_all, reviews):
    actor = Actor(1, "x", role)
    assert actor.can_see_all is sees_all and actor.can_review is reviews


def test_role_values_match_django_group_names():
    assert [r.value for r in Role] == ["Administrador", "Supervisor", "Operario"]


@pytest.mark.parametrize(
    "number,num_pages,prev,next_",
    [(1, 1, False, False), (1, 3, False, True), (2, 3, True, True), (3, 3, True, False)],
)
def test_page_navigation_flags(number, num_pages, prev, next_):
    page = Page(items=[], number=number, num_pages=num_pages, total=0)
    assert (page.has_prev, page.has_next) == (prev, next_)
