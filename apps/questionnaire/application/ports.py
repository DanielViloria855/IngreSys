"""Aplicación (questionnaire): puertos."""
from abc import ABC, abstractmethod

from apps.questionnaire.domain.entities import Questionnaire


class QuestionnaireRepository(ABC):
    """Puerto (aplicación): contrato para obtener el cuestionario activo."""

    @abstractmethod
    def get_active(self) -> Questionnaire | None:
        """Cuestionario activo con sus preguntas activas ordenadas, o None si no hay."""
