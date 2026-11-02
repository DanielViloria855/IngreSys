"""Infraestructura (analytics): inyección de dependencias manual (INSIGHT_PROVIDER=groq|rules)."""
from django.conf import settings

from apps.analytics.application.ports import InsightGenerator
from apps.analytics.application.use_cases import GenerateAIInsights, GetDashboardMetrics
from apps.analytics.infrastructure.llm.groq_adapter import GroqInsightAdapter
from apps.analytics.infrastructure.llm.rule_based_adapter import RuleBasedInsightAdapter
from apps.analytics.infrastructure.repositories import DjangoInsightCache, DjangoMetricsRepository


def get_insight_generator() -> InsightGenerator:
    if settings.INSIGHT_PROVIDER == "groq":
        return GroqInsightAdapter(settings.GROQ_API_KEY, settings.GROQ_MODEL)
    return RuleBasedInsightAdapter()


def get_dashboard_metrics() -> GetDashboardMetrics:
    return GetDashboardMetrics(DjangoMetricsRepository())


def generate_ai_insights() -> GenerateAIInsights:
    return GenerateAIInsights(
        primary=get_insight_generator(),
        fallback=RuleBasedInsightAdapter(),
        cache=DjangoInsightCache(),
    )
