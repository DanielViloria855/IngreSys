"""Infraestructura (questionnaire): adaptador en memoria para pruebas."""
from apps.questionnaire.application.ports import QuestionnaireRepository
from apps.questionnaire.domain.entities import Questionnaire


class InMemoryQuestionnaireRepository(QuestionnaireRepository):
    """Adaptador secundario (falso): devuelve el cuestionario que se le entregue, sin base de datos."""

    def __init__(self, questionnaire: Questionnaire | None = None):
        self._questionnaire = questionnaire

    def get_active(self) -> Questionnaire | None:
        return self._questionnaire
