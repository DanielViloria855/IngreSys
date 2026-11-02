from django.urls import path

from apps.entries.infrastructure import views

app_name = "entries"
urlpatterns = [
    path("", views.EntryListView.as_view(), name="list"),
    path("new/", views.EntryCreateView.as_view(), name="create"),
    path("export/", views.EntryExportCsvView.as_view(), name="export"),
    path("ocr/plate/", views.OcrPlateView.as_view(), name="ocr_plate"),
    path("ocr/container/", views.OcrContainerView.as_view(), name="ocr_container"),
    path("<int:pk>/", views.EntryDetailView.as_view(), name="detail"),
    path("<int:pk>/review/", views.EntryReviewView.as_view(), name="review"),
]
