from django.urls import path

from apps.analytics.infrastructure import views

app_name = "analytics"
urlpatterns = [
    path("", views.DashboardView.as_view(), name="dashboard"),
    path("metrics/", views.MetricsJsonView.as_view(), name="metrics"),
    path("insights/", views.InsightsView.as_view(), name="insights"),
    path("ask/", views.AskView.as_view(), name="ask"),
]
