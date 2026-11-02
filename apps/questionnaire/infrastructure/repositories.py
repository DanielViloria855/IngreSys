"""Infraestructura (questionnaire): adaptador secundario con el ORM de Django."""
from apps.questionnaire.application.ports import QuestionnaireRepository
from apps.questionnaire.domain.entities import ChoiceOption, Question, QuestionType, Questionnaire
from apps.questionnaire.infrastructure.models import Questionnaire as QuestionnaireModel


class DjangoQuestionnaireRepository(QuestionnaireRepository):
    """Adaptador secundario (infraestructura): implementa el puerto con el ORM y mapea modelo → entidad."""

    def get_active(self) -> Questionnaire | None:
        model = QuestionnaireModel.objects.filter(is_active=True).order_by("-id").first()
        if model is None:
            return None
        questions = (
            model.questions.filter(is_active=True).prefetch_related("choices").order_by("order", "id")
        )
        return Questionnaire(
            id=model.id,
            name=model.name,
            questions=[
                Question(
                    id=q.id,
                    order=q.order,
                    text=q.text,
                    help_text=q.help_text,
                    type=QuestionType(q.type),
                    is_required=q.is_required,
                    semantic_tag=q.semantic_tag,
                    depends_on_id=q.depends_on_id,
                    depends_on_value=q.depends_on_value,
                    choices=tuple(ChoiceOption(id=c.id, label=c.label, value=c.value) for c in q.choices.all()),
                )
                for q in questions
            ],
        )
