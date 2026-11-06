"""Adaptadores secundarios con dependencias externas simuladas: Google Vision, Groq, Pillow, almacenamiento, DI."""
import io
import json
import re
import sys
import types
from types import SimpleNamespace

import pytest
from PIL import Image

from apps.analytics.application.dtos import ChartPoint, DashboardMetricsDTO
from apps.analytics.domain.insight import InsightLevel, InsightUnavailable
from apps.analytics.infrastructure import container as analytics_container
from apps.analytics.infrastructure.llm.groq_adapter import GroqInsightAdapter
from apps.analytics.infrastructure.llm.rule_based_adapter import RuleBasedInsightAdapter
from apps.entries.domain.exceptions import OcrUnavailable
from apps.entries.infrastructure import container as entries_container
from apps.entries.infrastructure.ocr.fake_ocr_adapter import FakeOcrAdapter
from apps.entries.infrastructure.ocr.google_vision_adapter import GoogleVisionOcrAdapter
from apps.entries.infrastructure.ocr.image_preprocessing import MAX_SIDE, prepare_image
from apps.entries.infrastructure.storage import DjangoFileStorage


def image_bytes(size=(100, 50), mode="RGB", fmt="PNG", exif_orientation=None) -> bytes:
    image = Image.new(mode, size, "white" if mode == "RGB" else None)
    out = io.BytesIO()
    kwargs = {}
    if exif_orientation:
        exif = image.getexif()
        exif[0x0112] = exif_orientation
        kwargs["exif"] = exif.tobytes()
    image.save(out, format=fmt, **kwargs)
    return out.getvalue()


def opened(data: bytes) -> Image.Image:
    return Image.open(io.BytesIO(data))


# -- preprocesamiento de imagen --------------------------------------------------------------------
def test_large_image_is_downscaled_keeping_aspect_and_converted_to_jpeg():
    result = opened(prepare_image(image_bytes((4000, 2000))))
    assert result.format == "JPEG" and max(result.size) == MAX_SIDE and result.size == (1600, 800)


def test_small_image_is_not_upscaled():
    assert opened(prepare_image(image_bytes((300, 200)))).size == (300, 200)


def test_transparent_png_is_flattened_to_rgb():
    assert opened(prepare_image(image_bytes(mode="RGBA"))).mode == "RGB"


def test_exif_orientation_is_applied():
    rotated = opened(prepare_image(image_bytes((200, 100), fmt="JPEG", exif_orientation=6)))
    assert rotated.size == (100, 200)


@pytest.mark.parametrize("data", [b"", b"no soy una imagen", b"\xff\xd8\xff" + b"0" * 20])
def test_unreadable_image_raises_ocr_unavailable(data):
    with pytest.raises(OcrUnavailable, match="No se pudo leer la imagen"):
        prepare_image(data)


# -- Google Vision (cliente simulado) --------------------------------------------------------------
class FakeVisionClient:
    instances = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.response = SimpleNamespace(error=SimpleNamespace(message=""), text_annotations=[SimpleNamespace(description="COLOMBIA\nSKX 482")])
        self.raise_on_call = None
        self.calls = 0
        FakeVisionClient.instances.append(self)

    def text_detection(self, image):
        self.calls += 1
        assert opened(image.content).format == "JPEG"  # la imagen llega preprocesada
        if self.raise_on_call:
            raise self.raise_on_call
        return self.response


@pytest.fixture
def vision(monkeypatch):
    from google.cloud import vision as real_vision

    FakeVisionClient.instances = []
    monkeypatch.setattr(real_vision, "ImageAnnotatorClient", FakeVisionClient)
    return FakeVisionClient


def test_vision_returns_lines_and_uses_rest_with_api_key(vision):
    adapter = GoogleVisionOcrAdapter("AIza-test")
    assert adapter.read_text(image_bytes()) == ["COLOMBIA", "SKX 482"]
    assert vision.instances[0].kwargs == {"transport": "rest", "client_options": {"api_key": "AIza-test"}}


def test_vision_without_key_uses_service_account(vision):
    GoogleVisionOcrAdapter().read_text(image_bytes())
    assert vision.instances[0].kwargs == {"transport": "rest"}


def test_vision_client_is_created_once(vision):
    adapter = GoogleVisionOcrAdapter("k")
    adapter.read_text(image_bytes())
    adapter.read_text(image_bytes())
    assert len(vision.instances) == 1 and vision.instances[0].calls == 2


def test_vision_no_text_returns_empty(vision):
    adapter = GoogleVisionOcrAdapter("k")
    adapter._get_client().response.text_annotations = []
    assert adapter.read_text(image_bytes()) == []


def test_vision_api_error_message(vision):
    adapter = GoogleVisionOcrAdapter("k")
    adapter._get_client().response.error.message = "quota exceeded"
    with pytest.raises(OcrUnavailable, match="quota exceeded"):
        adapter.read_text(image_bytes())


def test_vision_network_error(vision):
    adapter = GoogleVisionOcrAdapter("k")
    adapter._get_client().raise_on_call = ConnectionError("dns")
    with pytest.raises(OcrUnavailable, match="No se pudo contactar") as err:
        adapter.read_text(image_bytes())
    assert isinstance(err.value.__cause__, ConnectionError)


def test_vision_missing_credentials(monkeypatch):
    from google.cloud import vision as real_vision

    def boom(**kwargs):
        raise RuntimeError("DefaultCredentialsError")

    monkeypatch.setattr(real_vision, "ImageAnnotatorClient", boom)
    with pytest.raises(OcrUnavailable, match="no está configurado"):
        GoogleVisionOcrAdapter().read_text(image_bytes())


# -- Groq (SDK simulado) ---------------------------------------------------------------------------
def metrics():
    return DashboardMetricsDTO(
        range_key="k", range_label="Hoy", days=1, trucks=3, boxes=1, pallets=1, witness_samples=1, novelty_entries=0,
        containers_total=0, containers_iso_valid=0, iso_valid_pct=None, seals_not_ok=0, pending_review=0,
        by_hour=[ChartPoint("08h", 3)],
    )


@pytest.fixture
def fake_groq(monkeypatch):
    """Sustituye el módulo `groq` por uno falso que registra la petición."""
    state = SimpleNamespace(content='{"insights":[{"level":"warning","title":"T","message":"M"}]}', error=None, request=None, init=None)

    class Groq:
        def __init__(self, **kwargs):
            state.init = kwargs
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

        def _create(self, **kwargs):
            state.request = kwargs
            if state.error:
                raise state.error
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=state.content))])

    monkeypatch.setitem(sys.modules, "groq", types.SimpleNamespace(Groq=Groq))
    return state


def test_groq_without_key_never_calls_the_api(fake_groq):
    with pytest.raises(InsightUnavailable, match="GROQ_API_KEY"):
        GroqInsightAdapter("", "m").generate(metrics())
    assert fake_groq.request is None


def test_groq_request_shape(fake_groq):
    [insight] = GroqInsightAdapter("gsk_x", "llama", timeout=5).generate(metrics())
    assert insight.level is InsightLevel.WARNING
    assert fake_groq.init == {"api_key": "gsk_x", "timeout": 5}
    req = fake_groq.request
    assert req["model"] == "llama" and req["response_format"] == {"type": "json_object"} and req["temperature"] == 0.3
    assert [m["role"] for m in req["messages"]] == ["system", "user"]
    assert json.loads(req["messages"][1]["content"])["trucks"] == 3


def test_groq_model_name_is_shown_to_user():
    assert GroqInsightAdapter("k", "openai/gpt-oss-120b").model_name == "Groq · openai/gpt-oss-120b"


@pytest.mark.parametrize("error", [TimeoutError("lento"), RuntimeError("429 rate limit")])
def test_groq_transport_errors_become_unavailable(fake_groq, error):
    fake_groq.error = error
    with pytest.raises(InsightUnavailable, match="Groq no respondió"):
        GroqInsightAdapter("k", "m").generate(metrics())


@pytest.mark.parametrize("content", [None, "", "no json", '{"insights":[]}'])
def test_groq_bad_content_becomes_unavailable(fake_groq, content):
    fake_groq.content = content
    with pytest.raises(InsightUnavailable):
        GroqInsightAdapter("k", "m").generate(metrics())


# -- contenedores de inyección de dependencias ------------------------------------------------------
def test_ocr_provider_selection(settings):
    entries_container.get_ocr_service.cache_clear()
    assert isinstance(entries_container.get_ocr_service(), FakeOcrAdapter)
    assert entries_container.get_ocr_service() is entries_container.get_ocr_service()  # una sola instancia
    settings.OCR_PROVIDER = "google"
    entries_container.get_ocr_service.cache_clear()
    assert isinstance(entries_container.get_ocr_service(), GoogleVisionOcrAdapter)


def test_insight_provider_selection(settings):
    assert isinstance(analytics_container.get_insight_generator(), RuleBasedInsightAdapter)
    settings.INSIGHT_PROVIDER, settings.GROQ_MODEL = "groq", "mx"
    generator = analytics_container.get_insight_generator()
    assert isinstance(generator, GroqInsightAdapter) and generator.model_name.endswith("mx")
    use_case = analytics_container.generate_ai_insights()
    assert isinstance(use_case._fallback, RuleBasedInsightAdapter)


def test_upload_limit_comes_from_settings(settings):
    settings.MAX_UPLOAD_MB = 2
    assert entries_container.register_truck_entry()._max_bytes == 2 * 1024 * 1024


# -- almacenamiento de evidencias ------------------------------------------------------------------
def test_file_storage_path_and_content(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    path = DjangoFileStorage().save(17, "Foto.PNG", b"abc")
    assert re.fullmatch(r"evidences/\d{4}/\d{2}/17/[0-9a-f]{32}\.png", path)
    assert (tmp_path / path).read_bytes() == b"abc"


def test_file_storage_never_reuses_names_and_defaults_extension(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    storage = DjangoFileStorage()
    a, b = storage.save(1, "x.jpg", b"1"), storage.save(1, "x.jpg", b"2")
    assert a != b and storage.save(1, "sin_extension", b"3").endswith(".jpg")


def test_file_storage_ignores_user_supplied_path_components(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    path = DjangoFileStorage().save(1, "../../etc/passwd.jpg", b"x")
    assert ".." not in path and path.startswith("evidences/")
