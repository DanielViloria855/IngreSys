from django.urls import path

from apps.accounts.infrastructure.views import IngreLoginView, IngreLogoutView

app_name = "accounts"
urlpatterns = [
    path("login/", IngreLoginView.as_view(), name="login"),
    path("logout/", IngreLogoutView.as_view(), name="logout"),
]
