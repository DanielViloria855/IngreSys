from datetime import datetime, timezone

import pytest

from apps.analytics.application.dtos import AskQuery, ChartPoint, DashboardMetricsDTO, SupplierIssues
from apps.analytics.application.ports import AnalyticsAssistant
from apps.analytics.application.prompts import ASSISTANT_SYSTEM_PROMPT, build_assistant_messages
from apps.analytics.application.use_cases import MAX_HISTORY_TURNS, MAX_QUESTION_CHARS, AskAnalyticsQuestion
from apps.analytics.domain.assistant import AssistantUnavailable, ChatRole, ChatTurn, InvalidQuestion
from apps.analytics.infrastructure.llm.groq_assistant import GroqAssistantAdapter
from apps.analytics.infrastructure.llm.rule_based_assistant import RuleBasedAssistantAdapter

NOW = lambda: datetime(2026, 1, 1, tzinfo=timezone.utc)  # noqa: E731


def metrics(**over):
    base = dict(
        range_key="k", range_label="Últimos 7 días", days=7, trucks=100, boxes=3000, pallets=400, witness_samples=50,
        novelty_entries=20, containers_total=40, containers_iso_valid=36, iso_valid_pct=90.0, seals_not_ok=3, pending_review=45,
        by_hour=[ChartPoint(f"{h:02d}h", {8: 30, 14: 20, 20: 4}.get(h, 0)) for h in range(24)],
        by_day=[ChartPoint(f"0{d}/11", v) for d, v in zip(range(1, 8), (10, 12, 30, 14, 12, 10, 12))],
        novelty_by_type=[ChartPoint("Humedad", 9), ChartPoint("Plagas", 4)],
        novelty_by_day=[ChartPoint(f"0{d}/11", v) for d, v in zip(range(1, 8), (1, 2, 9, 3, 2, 1, 2))],
        by_weekday=[ChartPoint("Lunes", 40), ChartPoint("Martes", 30), ChartPoint("Miércoles", 30)] + [ChartPoint("Jueves", 0)] * 4,
        top_suppliers=[ChartPoint("Carga Express", 30)],
        supplier_issues=[SupplierIssues("Frontera Cargo", 20, 12, 7, 5, 3, 60.0)],
        deltas={"trucks": 25.0},
    )
    base.update(over)
    return DashboardMetricsDTO(**base)


class Fixed(AnalyticsAssistant):
    model_name = "fijo"

    def __init__(self):
        self.queries = []

    def answer(self, query):
        self.queries.append(query)
        return "respuesta"


class Boom(AnalyticsAssistant):
    model_name = "boom"

    def answer(self, query):
        raise AssistantUnavailable("sin internet")


def ask(text, m=None, history=()):
    return AskAnalyticsQuestion(Boom(), RuleBasedAssistantAdapter(), NOW).execute(AskQuery(text, m or metrics(), tuple(history)))


# -- caso de uso --------------------------------------------------------------------------
def test_use_case_validates_question():
    use_case = AskAnalyticsQuestion(Fixed(), RuleBasedAssistantAdapter(), NOW)
    with pytest.raises(InvalidQuestion):
        use_case.execute(AskQuery("   ", metrics()))
    with pytest.raises(InvalidQuestion):
        use_case.execute(AskQuery("x" * (MAX_QUESTION_CHARS + 1), metrics()))


def test_use_case_uses_primary_and_trims_history():
    primary = Fixed()
    history = tuple(ChatTurn(ChatRole.USER, f"p{i}") for i in range(10))
    result = AskAnalyticsQuestion(primary, RuleBasedAssistantAdapter(), NOW).execute(AskQuery("  hola  ", metrics(), history))
    assert result.answer == "respuesta" and result.model_used == "fijo" and not result.fallback_used
    sent = primary.queries[0]
    assert sent.question == "hola" and len(sent.history) == MAX_HISTORY_TURNS and sent.history[-1].text == "p9"


def test_use_case_falls_back_to_rules_when_primary_fails():
    result = ask("¿Cuántos camiones ingresaron?")
    assert result.fallback_used and result.model_used == "Reglas automáticas" and "100 camiones" in result.answer


# -- reglas -----------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "question,expected",
    [
        ("¿Qué proveedor tiene más incidencias?", "Frontera Cargo"),
        ("¿A qué hora llegan más camiones?", "08h"),
        ("¿Hubo ingresos fuera de horario?", "fuera del horario"),
        ("¿Cómo van las novedades?", "Humedad"),
        ("¿Qué día hubo más novedades?", "03/11"),
        ("¿Y los sellos?", "3 ingreso(s)"),
        ("¿Cómo está el ISO de los contenedores?", "36 pasaron"),
        ("¿Cuántos pendientes de revisión hay?", "45 de 100"),
        ("¿Qué día de la semana hay más movimiento?", "lunes"),
        ("Dame un resumen", "100 camiones"),
        ("¿Cuántas cajas en promedio?", "30 cajas por camión"),
    ],
)
def test_rule_assistant_answers_from_metrics(question, expected):
    assert expected in ask(question).answer


def test_rule_assistant_unknown_question_and_empty_period():
    assert "No puedo responder" in ask("¿Qué opinas del fútbol?").answer
    assert "No hay ingresos" in ask("lo que sea", metrics(trucks=0)).answer


# -- prompt y adaptador Groq ----------------------------------------------------------------------
def test_prompt_contains_rules_metrics_history_and_question_without_pii():
    query = AskQuery("¿Qué proveedor falla?", metrics(), (ChatTurn(ChatRole.USER, "hola"), ChatTurn(ChatRole.ASSISTANT, "buenas")))
    messages = build_assistant_messages(query)
    assert [m["role"] for m in messages] == ["system", "user", "assistant", "user"]
    assert ASSISTANT_SYSTEM_PROMPT in messages[0]["content"] and "Frontera Cargo" in messages[0]["content"]
    assert "range_key" not in messages[0]["content"] and messages[-1]["content"] == "¿Qué proveedor falla?"


def test_groq_assistant_without_key_is_unavailable():
    with pytest.raises(AssistantUnavailable):
        GroqAssistantAdapter("", "modelo").answer(AskQuery("hola", metrics()))


def test_clean_answer_removes_markdown_and_odd_spaces():
    from apps.analytics.infrastructure.llm.groq_assistant import clean_answer

    raw = "El proveedor es **Frontera\u202fCargo** con `61,9\u00a0%`.\n- primera\n* segunda\n## Título  \n"
    assert clean_answer(raw) == "El proveedor es Frontera Cargo con 61,9 %.\n• primera\n• segunda\nTítulo"


# -- recomendaciones, estimaciones y patrones (contexto histórico) ------------------------------------------------
from datetime import date  # noqa: E402

WEEK = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]


def reference(avg=(40, 42, 41, 44, 60, 12, 4)):
    return metrics(range_label="Últimos 30 días", days=30, weekday_average=[ChartPoint(n, v) for n, v in zip(WEEK, avg)])


def ask_ctx(text, m=None, ref=None, today=date(2026, 11, 5)):  # jueves 5/11/2026
    return AskAnalyticsQuestion(Boom(), RuleBasedAssistantAdapter(), NOW).execute(AskQuery(text, m or metrics(), (), ref, today)).answer


def test_rule_assistant_recommends_actions_from_data():
    answer = ask_ctx("¿Qué me recomiendas hacer mañana?")  # «recomiendas» gana a «mañana»
    assert "Sugerencias" in answer and "Frontera Cargo" in answer and "pendientes" in answer and "08h" in answer


def test_rule_assistant_forecasts_tomorrow_from_weekday_average():
    answer = ask_ctx("¿Mañana debería ser un día de mucho volumen?", metrics(trucks=33, range_label="Hoy", days=1), reference())
    assert "viernes" in answer and "60 camiones" in answer and "por encima" in answer and "estimación" in answer


def test_rule_assistant_forecast_without_history_is_honest():
    assert "No hay suficiente historial" in ask_ctx("¿Cómo será mañana?", metrics(), None)


def test_rule_assistant_patterns_use_reference_not_single_day():
    answer = ask_ctx("¿Qué patrón es el más recurrente?", metrics(trucks=33, range_label="Hoy", days=1), reference())
    assert "viernes" in answer and "Frontera Cargo" in answer and "últimos 30 días" in answer


def test_prompt_includes_today_tomorrow_and_historical_context():
    query = AskQuery("¿Mañana habrá mucho volumen?", metrics(range_label="Hoy"), (), reference(), date(2026, 11, 5))
    system = build_assistant_messages(query)[0]["content"]
    assert "jueves 05/11/2026" in system and "Mañana será viernes 06/11/2026" in system
    assert "Contexto histórico de los últimos 30 días" in system and "weekday_average" in system
    assert "recomendaciones operativas" in system  # ya no rechaza recomendar


def test_prompt_without_context_still_builds():
    system = build_assistant_messages(AskQuery("hola", metrics()))[0]["content"]
    assert "Fecha actual" not in system and "Contexto histórico" not in system


def test_prompt_keeps_weekday_stats_only_in_historical_context_for_short_periods():
    query = AskQuery("¿Mañana habrá mucho volumen?", metrics(days=1, range_label="Hoy"), (), reference(), date(2026, 11, 5))
    system = build_assistant_messages(query)[0]["content"]
    selected, historical = system.split("Contexto histórico de los últimos 30 días")
    assert '"weekday_average"' not in selected.split("Métricas del periodo seleccionado")[1]
    assert '"weekday_average"' in historical
    wide = build_assistant_messages(AskQuery("hola", metrics(days=30), (), None, None))[0]["content"]
    assert '"weekday_average"' in wide  # en un periodo largo sí se conserva


def test_rule_forecast_refuses_to_estimate_from_a_single_day():
    one_day = metrics(days=1, range_label="Hoy", weekday_average=[ChartPoint(n, 33 if n == "Jueves" else 0) for n in WEEK])
    assert "No hay suficiente historial" in ask_ctx("¿Cómo será mañana?", one_day, None)
