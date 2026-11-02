from django.urls import path

from apps.accounts.infrastructure.views import StaffFormView, StaffListView

app_name = "staff"
urlpatterns = [
    path("", StaffListView.as_view(), name="list"),
    path("new/", StaffFormView.as_view(), name="create"),
    path("<int:pk>/edit/", StaffFormView.as_view(), name="edit"),
]
