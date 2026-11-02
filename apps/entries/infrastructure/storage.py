"""Infraestructura (entries): adaptador de almacenamiento de evidencias."""
import uuid

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils import timezone

from apps.entries.application.ports import FileStorage


class DjangoFileStorage(FileStorage):
    """Adaptador secundario (infraestructura): guarda con `default_storage` en evidences/<año>/<mes>/<id>/."""

    def save(self, entry_id: int, filename: str, content: bytes) -> str:
        now = timezone.localtime()
        extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else "jpg"
        path = f"evidences/{now:%Y}/{now:%m}/{entry_id}/{uuid.uuid4().hex}.{extension}"
        return default_storage.save(path, ContentFile(content))
