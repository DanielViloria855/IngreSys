"""Aplicación (questionnaire): casos de uso."""
from apps.questionnaire.application.ports import QuestionnaireRepository
from apps.questionnaire.domain.entities import Questionnaire
from shared.application.base import BaseUseCase
from shared.domain.base import DomainError


class NoActiveQuestionnaire(DomainError):
    """No hay un cuestionario activo configurado."""


class GetActiveQuestionnaire(BaseUseCase[None, Questionnaire]):
    """Caso de uso (aplicación): entrega el cuestionario activo para armar el formulario."""

    def __init__(self, repository: QuestionnaireRepository):
        self._repository = repository

    def execute(self, data: None = None) -> Questionnaire:
        questionnaire = self._repository.get_active()
        if questionnaire is None:
            raise NoActiveQuestionnaire("No hay un cuestionario activo. Ejecuta `manage.py seed_questionnaire`.")
        return questionnaire
