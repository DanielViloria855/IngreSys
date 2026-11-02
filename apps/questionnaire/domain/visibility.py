"""Dominio (questionnaire): regla de ramificación (qué preguntas se muestran).

Se usa en el servidor y se replica en `static/js/dynamic-form.js` para el navegador.
"""
from typing import Any, Iterable, Mapping

from apps.questionnaire.domain.entities import Question


def _norm(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value).strip().lower()


def _matches(raw: Any, expected: str) -> bool:
    if raw is None or raw == "" or raw == [] or raw == ():
        return False
    if isinstance(raw, (list, tuple, set)):
        return any(_norm(item) == _norm(expected) for item in raw)
    return _norm(raw) == _norm(expected)


class VisibilityRule:
    """Regla (dominio): una pregunta es visible si no depende de otra o si la otra tiene el valor esperado."""

    @staticmethod
    def is_visible(question: Question, answers: Mapping[int, Any]) -> bool:
        """Función pura: ¿se muestra `question` dadas las respuestas (por id de pregunta)?"""
        if question.depends_on_id is None:
            return True
        return _matches(answers.get(question.depends_on_id), question.depends_on_value)

    @classmethod
    def visible_questions(cls, questions: Iterable[Question], answers: Mapping[int, Any]) -> list[Question]:
        """Preguntas visibles en orden. Si el padre está oculto, el hijo también (cascada)."""
        visible_ids: set[int] = set()
        result: list[Question] = []
        for question in sorted(questions, key=lambda q: q.order):
            if question.depends_on_id is not None and question.depends_on_id not in visible_ids:
                continue
            if cls.is_visible(question, answers):
                result.append(question)
                if question.id is not None:
                    visible_ids.add(question.id)
        return result
