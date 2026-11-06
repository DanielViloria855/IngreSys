"""Infraestructura (entries): adaptador de OCR con Google Cloud Vision."""
from apps.entries.application.ports import OcrService
from apps.entries.domain.exceptions import OcrUnavailable
from apps.entries.infrastructure.ocr.image_preprocessing import prepare_image


class GoogleVisionOcrAdapter(OcrService):
    """Adaptador secundario: OCR con IA usando Google Cloud Vision (TEXT_DETECTION).

    Usa transporte REST (más tolerante con redes corporativas que gRPC). Credenciales: llave de API o GOOGLE_APPLICATION_CREDENTIALS. El cliente se crea la primera vez que se necesita,
    así una credencial ausente no tumba el servidor: solo avisa y deja escribir a mano.
    """

    def __init__(self, api_key: str = ""):
        self._api_key = api_key
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from google.cloud import vision

                if self._api_key:  # llave de API simple
                    self._client = vision.ImageAnnotatorClient(transport="rest", client_options={"api_key": self._api_key})
                else:  # cuenta de servicio (GOOGLE_APPLICATION_CREDENTIALS)
                    self._client = vision.ImageAnnotatorClient(transport="rest")
            except Exception as exc:  # credenciales ausentes o inválidas
                raise OcrUnavailable("El OCR con IA no está configurado. Escribe el dato a mano.") from exc
        return self._client

    def read_text(self, image_bytes: bytes) -> list[str]:
        from google.cloud import vision

        content = prepare_image(image_bytes)
        client = self._get_client()
        try:
            response = client.text_detection(image=vision.Image(content=content))
        except Exception as exc:  # red, cuota, etc.
            raise OcrUnavailable("No se pudo contactar el servicio de OCR. Escribe el dato a mano.") from exc
        if response.error.message:
            raise OcrUnavailable(f"El servicio de OCR respondió con un error: {response.error.message}")
        if not response.text_annotations:
            return []
        return response.text_annotations[0].description.splitlines()
