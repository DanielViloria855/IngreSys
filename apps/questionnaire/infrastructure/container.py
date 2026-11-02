"""Infraestructura (questionnaire): inyección de dependencias manual."""
from apps.questionnaire.application.ports import QuestionnaireRepository
from apps.questionnaire.application.use_cases import GetActiveQuestionnaire
from apps.questionnaire.infrastructure.repositories import DjangoQuestionnaireRepository


def get_questionnaire_repository() -> QuestionnaireRepository:
    return DjangoQuestionnaireRepository()


def get_active_questionnaire_use_case() -> GetActiveQuestionnaire:
    return GetActiveQuestionnaire(get_questionnaire_repository())
