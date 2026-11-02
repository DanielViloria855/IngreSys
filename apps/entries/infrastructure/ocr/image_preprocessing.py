"""Infraestructura (entries): preprocesa la foto antes de enviarla al OCR."""
import io

from PIL import Image, ImageOps, UnidentifiedImageError

from apps.entries.domain.exceptions import OcrUnavailable

MAX_SIDE = 1600


def prepare_image(image_bytes: bytes, max_side: int = MAX_SIDE) -> bytes:
    """Corrige la orientación EXIF, reduce a `max_side` px y convierte a JPEG."""
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            image = ImageOps.exif_transpose(image).convert("RGB")
            image.thumbnail((max_side, max_side))
            out = io.BytesIO()
            image.save(out, format="JPEG", quality=85)
            return out.getvalue()
    except (UnidentifiedImageError, OSError) as exc:
        raise OcrUnavailable("No se pudo leer la imagen. Intenta con otra foto.") from exc
