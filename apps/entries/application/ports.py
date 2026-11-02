"""Aplicación (entries): puertos que el núcleo necesita (abstracciones, herencia explícita con ABC)."""
from abc import ABC, abstractmethod

from apps.entries.application.dtos import AnswerValue, EntryDetailDTO, EntryFilters, EntrySummaryDTO
from apps.entries.domain.entities import TruckEntry
from shared.application.pagination import Page


class OcrService(ABC):
    """Puerto (aplicación): contrato para servicios de OCR."""

    @abstractmethod
    def read_text(self, image_bytes: bytes) -> list[str]:
        """Devuelve las líneas de texto detectadas en la imagen. Lanza OcrUnavailable si el servicio falla."""


class FileStorage(ABC):
    """Puerto (aplicación): contrato para guardar archivos de evidencia."""

    @abstractmethod
    def save(self, entry_id: int, filename: str, content: bytes) -> str:
        """Guarda el archivo y devuelve su ruta relativa."""


class TruckEntryRepository(ABC):
    """Puerto (aplicación): contrato de persistencia de ingresos."""

    @abstractmethod
    def save(self, entry: TruckEntry, answers: list[AnswerValue]) -> int:
        """Persiste el ingreso con sus respuestas y devuelve su id."""

    @abstractmethod
    def add_evidence(self, entry_id: int, question_id: int | None, kind: str, stored_path: str) -> None:
        """Asocia un archivo ya guardado al ingreso."""

    @abstractmethod
    def get(self, entry_id: int) -> TruckEntry | None:
        """Entidad del ingreso, o None."""

    @abstractmethod
    def get_detail(self, entry_id: int) -> EntryDetailDTO | None:
        """Detalle listo para mostrar (sin la línea de estado), o None."""

    @abstractmethod
    def list(self, filters: EntryFilters, page: int, page_size: int) -> Page[EntrySummaryDTO]:
        """Página de resúmenes según los filtros."""

    @abstractmethod
    def save_review(self, entry: TruckEntry) -> None:
        """Persiste el cambio de estado por revisión."""
