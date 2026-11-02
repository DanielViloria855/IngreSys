# ingreSys

Prototipo académico (Tecnológico de Antioquia) inspirado en SIGIM: control de ingreso de camiones con formulario dinámico, OCR con IA de placas y contenedores, validación ISO 6346, evidencia fotográfica, histórico y un tablero BI con análisis por LLM.

Contexto completo del proyecto: [CONTEXTO_INGRESYS.md](CONTEXTO_INGRESYS.md) · Sistema de diseño: [design-system/ingresys/MASTER.md](design-system/ingresys/MASTER.md)

## Arranque rápido

```bash
python -m venv .venv && .venv\Scripts\activate      # Windows
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo_data                      # roles, usuarios, cuestionario y ~60 ingresos
python manage.py runserver
```

Usuarios demo (contraseña `Ingresys2026!`): `admin`, `supervisor`, `operario1..3`.

El `.env` incluido usa `OCR_PROVIDER=fake` e `INSIGHT_PROVIDER=rules`, así corre sin internet ni credenciales.
Para IA real: `OCR_PROVIDER=google` (+ `GOOGLE_APPLICATION_CREDENTIALS`) e `INSIGHT_PROVIDER=groq` (+ `GROQ_API_KEY`).

Pruebas: `python -m pytest`

## Arquitectura hexagonal (ligera)

```
  Adaptadores PRIMARIOS      Views (CBV) · Forms · Templates · JSON
  (quien llama al núcleo)              │
                                       ▼
 ┌──────────────────── APLICACIÓN ────────────────────┐
 │  Casos de uso (BaseUseCase) · DTOs                  │
 │  PUERTOS (ABC): TruckEntryRepository, OcrService,   │
 │  FileStorage, MetricsRepository, InsightGenerator…  │
 │        ┌────────── DOMINIO (Python puro) ─────────┐ │
 │        │ Entity · ValueObject · Plate · ISO 6346  │ │
 │        │ Parsers (Template Method) · Visibility   │ │
 │        └──────────────────────────────────────────┘ │
 └─────────────────────────────────────────────────────┘
                                       ▲ implementan los puertos
  Adaptadores SECUNDARIOS    DjangoTruckEntryRepository · GoogleVisionOcrAdapter
  (lo que el núcleo usa)     GroqInsightAdapter · RuleBasedInsightAdapter
                             DjangoFileStorage · InMemory* / Fake* (pruebas)
```

Dependencias solo hacia adentro: `domain` no importa nada; `application` solo importa `domain`; `infrastructure` importa todo.

| Módulo | Qué hace |
|---|---|
| `apps/accounts` | Login/logout, roles (`Group`), gestión de personal |
| `apps/questionnaire` | Formulario dinámico y regla de ramificación |
| `apps/entries` | Ingreso de camiones, OCR, ISO 6346, evidencias, histórico, revisión |
| `apps/analytics` | Tablero BI, insights con Groq (caché + respaldo por reglas) |

Frontend: Django Templates con Atomic Design (`templates/atoms → molecules → organisms → layouts → pages`), Bootstrap 5, Chart.js y JS vanilla en `static/js/`.

## Desviaciones menores respecto al documento de contexto

- Los comandos `seed_*` viven en `apps/<app>/management/commands/` (Django solo los descubre ahí).
- `apps/<app>/models.py` y `admin.py` son un puente (`from ...infrastructure.models import *`) porque Django exige esos nombres.
- `LOGIN_REDIRECT_URL="home"`: `/` redirige según el rol (el operario no tiene acceso al tablero).
