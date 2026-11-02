"""Infraestructura (entries): adaptadores en memoria para pruebas y demos sin base de datos."""
from dataclasses import replace
from itertools import count

from apps.entries.application.dtos import AnswerValue, EntryDetailDTO, EntryFilters, EntrySummaryDTO, STATUS_META
from apps.entries.application.ports import FileStorage, TruckEntryRepository
from apps.entries.domain.entities import TruckEntry
from shared.application.pagination import Page


class InMemoryTruckEntryRepository(TruckEntryRepository):
    """Adaptador secundario (falso): guarda ingresos en diccionarios."""

    def __init__(self):
        self._ids = count(1)
        self.entries: dict[int, TruckEntry] = {}
        self.answers: dict[int, list[AnswerValue]] = {}
        self.evidences: list[tuple[int, int | None, str, str]] = []

    def save(self, entry: TruckEntry, answers: list[AnswerValue]) -> int:
        entry_id = next(self._ids)
        self.entries[entry_id] = replace(entry, id=entry_id)
        self.answers[entry_id] = list(answers)
        return entry_id

    def add_evidence(self, entry_id, question_id, kind, stored_path) -> None:
        self.evidences.append((entry_id, question_id, kind, stored_path))

    def get(self, entry_id: int) -> TruckEntry | None:
        return self.entries.get(entry_id)

    def get_detail(self, entry_id: int) -> EntryDetailDTO | None:
        entry = self.entries.get(entry_id)
        if entry is None:
            return None
        label, variant = STATUS_META[entry.status.value]
        return EntryDetailDTO(
            id=entry.id, created_at=entry.created_at, created_by_id=entry.created_by_id, created_by_name="",  # type: ignore[arg-type]
            plate=entry.plate, container_code=entry.container_code,
            container_iso_valid=entry.container_iso_valid if entry.container_code else None,
            iso_read_digit=None, iso_expected_digit=None, status=entry.status.value, status_label=label,
            status_variant=variant, answers=[], evidences=[],
        )

    def list(self, filters: EntryFilters, page: int, page_size: int) -> Page[EntrySummaryDTO]:
        rows = [e for e in self.entries.values() if filters.user_id in (None, e.created_by_id)]
        items = []
        for e in rows[(page - 1) * page_size : page * page_size]:
            label, variant = STATUS_META[e.status.value]
            items.append(EntrySummaryDTO(e.id, e.created_at, e.plate, e.container_code, None, "", "", e.status.value, label, variant, None))  # type: ignore[arg-type]
        return Page(items, page, max(1, -(-len(rows) // page_size)), len(rows), page_size)

    def save_review(self, entry: TruckEntry) -> None:
        self.entries[entry.id] = entry  # type: ignore[index]


class InMemoryFileStorage(FileStorage):
    """Adaptador secundario (falso): «guarda» archivos en memoria y devuelve rutas ficticias."""

    def __init__(self):
        self.files: dict[str, bytes] = {}

    def save(self, entry_id: int, filename: str, content: bytes) -> str:
        path = f"evidences/test/{entry_id}/{len(self.files)}_{filename}"
        self.files[path] = content
        return path
