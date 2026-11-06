from pathlib import Path

import pytest

# carpeta de tests/ -> marcador (pytest.ini los declara). Así `pytest -m security` corre solo esa capa.
FOLDER_MARKERS = {
    "domain": "unit",
    "application": "unit",
    "property": "property",
    "architecture": "architecture",
    "infrastructure": "integration",
    "integration": "integration",
    "contract": "contract",
    "functional": "functional",
    "security": "security",
    "performance": "performance",
    "smoke": "smoke",
    "e2e": "e2e",
}
TESTS_DIR = Path(__file__).parent


def pytest_collection_modifyitems(config, items):
    for item in items:
        try:
            folder = Path(item.path).relative_to(TESTS_DIR).parts[0]
        except ValueError:
            continue
        marker = FOLDER_MARKERS.get(folder)
        if marker:
            item.add_marker(getattr(pytest.mark, marker))


# -- fixtures compartidas para las pruebas con base de datos ---------------------------------
@pytest.fixture(autouse=True)
def fast_password_hashing(settings):
    """PBKDF2 es lento a propósito; en pruebas basta MD5 (las contraseñas no son reales)."""
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


@pytest.fixture
def seeded(db, settings, tmp_path):
    """Roles + cuestionario semilla; las fotos van a una carpeta temporal."""
    from tests.factories import seed

    settings.MEDIA_ROOT = tmp_path
    seed()


@pytest.fixture
def operator(seeded):
    from tests.factories import make_user
    from shared.domain.roles import Role

    return make_user("op1", Role.OPERATOR, first_name="Olga", last_name="Pérez")


@pytest.fixture
def operator2(seeded):
    from tests.factories import make_user
    from shared.domain.roles import Role

    return make_user("op2", Role.OPERATOR)


@pytest.fixture
def supervisor(seeded):
    from tests.factories import make_user
    from shared.domain.roles import Role

    return make_user("sup", Role.SUPERVISOR, first_name="Sara", last_name="Gil")


@pytest.fixture
def administrator(seeded):
    from tests.factories import make_user
    from shared.domain.roles import Role

    return make_user("adm", Role.ADMIN, is_staff=True)


@pytest.fixture(autouse=True)
def isolate_ai_providers(settings):
    """Las pruebas nunca llaman a Google Vision ni a Groq, sin importar lo que diga el .env."""
    from apps.entries.infrastructure import container

    original = container.get_ocr_service  # algunos tests lo reemplazan con monkeypatch
    settings.OCR_PROVIDER = "fake"
    from django.core.cache import cache

    cache.clear()  # el límite de preguntas al asistente vive en la caché
    settings.INSIGHT_PROVIDER = "rules"
    settings.GROQ_API_KEY = ""
    settings.GOOGLE_VISION_API_KEY = ""
    original.cache_clear()
    yield
    original.cache_clear()
