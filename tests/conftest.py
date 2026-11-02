import pytest


@pytest.fixture(autouse=True)
def isolate_ai_providers(settings):
    """Las pruebas nunca llaman a Google Vision ni a Groq, sin importar lo que diga el .env."""
    from apps.entries.infrastructure import container

    settings.OCR_PROVIDER = "fake"
    settings.INSIGHT_PROVIDER = "rules"
    settings.GROQ_API_KEY = ""
    settings.GOOGLE_VISION_API_KEY = ""
    container.get_ocr_service.cache_clear()
    yield
    container.get_ocr_service.cache_clear()
