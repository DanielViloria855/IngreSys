"""Infraestructura (entries): inyección de dependencias manual.

El adaptador concreto se elige por .env (OCR_PROVIDER=google|fake).
"""
from functools import lru_cache

from django.conf import settings

from apps.entries.application.ports import FileStorage, OcrService, TruckEntryRepository
from apps.entries.application.use_cases import (
    GetEntryDetail,
    ListEntries,
    ReadContainerWithAI,
    ReadPlateWithAI,
    RegisterTruckEntry,
    ReviewEntry,
)
from apps.entries.infrastructure.ocr.fake_ocr_adapter import FakeOcrAdapter
from apps.entries.infrastructure.repositories import DjangoTruckEntryRepository
from apps.entries.infrastructure.storage import DjangoFileStorage
from apps.questionnaire.infrastructure.container import get_questionnaire_repository


@lru_cache(maxsize=1)
def get_ocr_service() -> OcrService:
    if settings.OCR_PROVIDER == "google":
        from apps.entries.infrastructure.ocr.google_vision_adapter import GoogleVisionOcrAdapter

        return GoogleVisionOcrAdapter(settings.GOOGLE_VISION_API_KEY)
    return FakeOcrAdapter()


def get_repository() -> TruckEntryRepository:
    return DjangoTruckEntryRepository()


def get_storage() -> FileStorage:
    return DjangoFileStorage()


def register_truck_entry() -> RegisterTruckEntry:
    return RegisterTruckEntry(
        repository=get_repository(),
        storage=get_storage(),
        questionnaires=get_questionnaire_repository(),
        max_upload_bytes=settings.MAX_UPLOAD_MB * 1024 * 1024,
    )


def read_plate_with_ai() -> ReadPlateWithAI:
    return ReadPlateWithAI(get_ocr_service())


def read_container_with_ai() -> ReadContainerWithAI:
    return ReadContainerWithAI(get_ocr_service())


def list_entries() -> ListEntries:
    return ListEntries(get_repository())


def get_entry_detail() -> GetEntryDetail:
    return GetEntryDetail(get_repository())


def review_entry() -> ReviewEntry:
    return ReviewEntry(get_repository())
