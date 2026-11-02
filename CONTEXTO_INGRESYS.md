# ingreSys — Contexto del proyecto para el asistente de código

> Documento de contexto para implementar **ingreSys**, prototipo académico (Tecnológico de Antioquia) inspirado en SIGIM, un sistema real de control de ingreso de camiones y mercancía. Es una versión **condensada**. Conserva la esencia de SIGIM: formulario dinámico, OCR con IA de placas y contenedores, validación ISO 6346, evidencia fotográfica e histórico. Le agrega un tablero de BI con interpretación por LLM.

**Reglas de oro**
1. Simple antes que sofisticado. Es un proyecto universitario: hexagonal **ligera**, pero con las capas bien visibles para poder explicarlas en la sustentación.
2. Si Django ya lo resuelve (auth, admin, ORM, templates), se usa Django.
3. El código debe **enseñar**: nombres claros, docstrings cortos que digan a qué capa pertenece cada clase y qué patrón aplica.

---

## 1. Alcance

| # | Módulo | Qué hace |
|---|---|---|
| 1 | **Autenticación** | Login/logout con `django.contrib.auth`, roles con `Group` |
| 2 | **Ingreso de camiones** | Formulario dinámico de una sola fase. Incluye OCR con IA (Google Cloud Vision) para la **placa** y el **código de contenedor**, validación **ISO 6346** y evidencia fotográfica |
| 3 | **Histórico** | Listado con filtros, estado/fase del registro, detalle y revisión por el supervisor |
| 4 | **Tablero BI + IA** | Tarjetas KPI y gráficos del proceso diario (camiones, cajas, estibas, muestras testigo, novedades, ISO). Un LLM (**Groq**, plan gratuito) interpreta los datos y genera mensajes de análisis |
| 5 | **Administración** | Gestión de personal (usuarios, roles) y gestión del cuestionario dinámico |

**Fuera de alcance:** fase 2 de descargue, integración SAP, Power BI, API móvil separada, despliegue en Kubernetes, multi-sede.

### Integraciones de IA (requisito del proyecto)
| Integración | Tipo de IA | Uso |
|---|---|---|
| **Google Cloud Vision** (`TEXT_DETECTION`) | Visión por computador (deep learning pre-entrenado) | Leer placas y códigos de contenedor desde fotos |
| **Groq** (LLM open-source, p. ej. `openai/gpt-oss-120b` o `llama-3.3-70b-versatile`) | Modelo de lenguaje (LLM) | Interpretar los KPIs del día o del rango y generar alertas, tendencias y recomendaciones en lenguaje natural |

Ambas entran por **puertos**, así que se pueden reemplazar por otros adaptadores, incluidos adaptadores falsos para pruebas o demos sin internet. Ese es el argumento central de la arquitectura hexagonal en la sustentación.

> Costos: Cloud Vision trae 1.000 unidades gratis al mes por feature (sobra para el prototipo). El plan Free de Groq no pide tarjeta y tiene límites por minuto y por día. El tablero **no** llama al LLM en cada carga: guarda el análisis en caché (ver sección 9).

---

## 2. Stack técnico

| Capa | Tecnología |
|---|---|
| Lenguaje | Python 3.12 |
| Backend | Django 5.x con arquitectura hexagonal |
| Frontend | Django Templates organizados con **Atomic Design** + Bootstrap 5 (CDN) + JS vanilla en archivos separados + Chart.js (CDN) para gráficos |
| Base de datos | SQLite en desarrollo, PostgreSQL opcional (por `.env`) |
| IA – OCR | `google-cloud-vision` |
| IA – LLM | SDK `groq` (API compatible con OpenAI) |
| Imágenes | `Pillow` |
| Config | `django-environ` + `.env` |
| Tests | `pytest` + `pytest-django` |

**Aclaración sobre el "monolito":** el proyecto es **un solo proyecto Django desplegable**, pero **no un solo archivo**. Backend organizado por capas hexagonales y frontend en muchos templates HTML pequeños (átomos, moléculas, organismos, layouts y páginas). No hay framework de frontend ni paso de build.

---

## 3. Arquitectura hexagonal (ligera y explicable)

```
                 ┌──────────────────────── INFRAESTRUCTURA ────────────────────────┐
                 │                                                                  │
 Adaptadores     │  Views (CBV) · Forms · Templates · endpoints JSON               │
 PRIMARIOS  ───► │        │                                                        │
 (driving)       │        ▼                                                        │
                 │   ┌──────────── APLICACIÓN ────────────┐                        │
                 │   │  Casos de uso (BaseUseCase)        │                        │
                 │   │  DTOs                              │                        │
                 │   │  PUERTOS (clases abstractas ABC)   │                        │
                 │   │      ┌──── DOMINIO ────┐           │                        │
                 │   │      │ Entidades       │           │                        │
                 │   │      │ Value Objects   │           │                        │
                 │   │      │ Reglas (ISO,    │           │                        │
                 │   │      │ placa, visibil.)│           │                        │
                 │   │      └─────────────────┘           │                        │
                 │   └────────────────────────────────────┘                        │
                 │        ▲ implementan los puertos                                │
 Adaptadores     │  DjangoTruckEntryRepository · GoogleVisionOcrAdapter ·          │
 SECUNDARIOS ◄── │  GroqInsightAdapter · DjangoFileStorage · Fake* (tests)         │
 (driven)        │                                                                  │
                 └──────────────────────────────────────────────────────────────────┘
```

**Regla de dependencias:** solo hacia adentro. `domain` no importa nada de `application` ni de Django. `application` solo importa `domain`. `infrastructure` puede importar todo.

| Capa | Contiene | Ejemplos |
|---|---|---|
| **Dominio** | Python puro. Entidades, value objects, reglas, excepciones | `TruckEntry`, `Plate`, `ContainerCode`, `iso6346.compute_check_digit`, `VisibilityRule` |
| **Aplicación – Puertos** | Interfaces abstractas (`abc.ABC`) que el núcleo necesita | `TruckEntryRepository`, `OcrService`, `InsightGenerator`, `FileStorage`, `MetricsRepository` |
| **Aplicación – Casos de uso** | Orquestan dominio + puertos. Un caso de uso = una acción del usuario | `RegisterTruckEntry`, `ReadPlateWithAI`, `GetDashboardMetrics`, `GenerateAIInsights` |
| **Infraestructura – Adaptadores primarios** | Lo que **llama** al núcleo | Vistas Django, comandos `manage.py` |
| **Infraestructura – Adaptadores secundarios** | Lo que el núcleo **usa** a través de puertos | Repositorios ORM, Google Vision, Groq, almacenamiento de archivos |

### Simplificaciones permitidas
- Los modelos ORM viven en infraestructura y los repositorios mapean ORM ↔ entidad. Para catálogos triviales se aceptan DTOs simples.
- La autenticación **no se abstrae**: `django.contrib.auth` se usa directo en infraestructura.
- Inyección de dependencias **manual** en un `container.py` por módulo. El adaptador concreto se elige según `.env` (p. ej. `OCR_PROVIDER=google|fake`).

---

## 4. POO y herencia (debe ser visible en el código)

El proyecto debe mostrar herencia, abstracción y polimorfismo de forma explícita para la sustentación. Usar **`abc.ABC` + `@abstractmethod`** para los puertos (no `Protocol`), porque así la herencia queda visible.

### Jerarquías obligatorias

```python
# shared/domain/base.py
class Entity(ABC):                 # base de entidades: identidad por id
    id: int | None
    def __eq__(self, other): ...

class ValueObject(ABC):            # base de value objects: igualdad por valor, inmutables
    @abstractmethod
    def _validate(self) -> None: ...

class DomainError(Exception): ...  # base de excepciones de dominio
class InvalidPlate(DomainError): ...
class InvalidContainerCode(DomainError): ...
```

```python
# shared/application/base.py
class BaseUseCase(ABC, Generic[TInput, TOutput]):
    @abstractmethod
    def execute(self, data: TInput) -> TOutput: ...
```

```python
# entries/application/ports.py        ← PUERTO (abstracción)
class OcrService(ABC):
    @abstractmethod
    def read_text(self, image_bytes: bytes) -> list[str]: ...

# entries/infrastructure/ocr/google_vision_adapter.py   ← ADAPTADOR (herencia)
class GoogleVisionOcrAdapter(OcrService):
    def read_text(self, image_bytes): ...   # llama a Cloud Vision

# entries/infrastructure/ocr/fake_ocr_adapter.py
class FakeOcrAdapter(OcrService):
    def read_text(self, image_bytes): ...   # devuelve texto fijo (tests/demo)
```

Lo mismo para `InsightGenerator` → `GroqInsightAdapter` / `RuleBasedInsightAdapter`, y para los repositorios → `DjangoXRepository` / `InMemoryXRepository`.

### Herencia también en el código que pone Django
- **Value objects:** `Plate(ValueObject)`, `ContainerCode(ValueObject)`.
- **Parsers de OCR:** `BaseCodeParser(ABC)` con el método plantilla `parse()` (normaliza → genera candidatos → corrige confusiones → valida). `PlateParser` y `ContainerCodeParser` heredan y solo sobrescriben el patrón y la validación (**patrón Template Method**).
- **Modelos:** `TimeStampedModel(models.Model)` abstracto con `created_at`/`updated_at`, del que heredan los demás.
- **Vistas:** CBV con mixins, p. ej. `class EntryCreateView(LoginRequiredMixin, RoleRequiredMixin, View)`. `RoleRequiredMixin` es propio y está en `core`.
- **Templates:** `{% extends %}` (herencia de plantillas) + `{% include %}` (composición Atomic Design).

Cada clase base lleva un docstring de una línea que diga qué rol cumple, p. ej. `"""Puerto (aplicación): contrato para servicios de OCR."""`.

---

## 5. Estructura de carpetas

```
ingresys/
├── manage.py
├── .env.example
├── requirements.txt
├── README.md
├── config/                         # settings, urls, wsgi
├── shared/                         # clases base reutilizables
│   ├── domain/base.py              # Entity, ValueObject, DomainError
│   └── application/base.py         # BaseUseCase
├── apps/
│   ├── core/                       # mixins de roles, TimeStampedModel, context processors
│   ├── accounts/                   # login, roles, gestión de personal
│   │   └── infrastructure/ (views.py, forms.py, urls.py, admin.py, models.py[Profile])
│   ├── questionnaire/              # formulario dinámico
│   │   ├── domain/ (entities.py, visibility.py)
│   │   ├── application/ (ports.py, use_cases.py, dtos.py)
│   │   └── infrastructure/ (models.py, repositories.py, admin.py, container.py,
│   │                        management/commands/seed_questionnaire.py)
│   ├── entries/                    # ingreso de camiones + histórico
│   │   ├── domain/ (entities.py, value_objects.py, iso6346.py, parsers.py, exceptions.py)
│   │   ├── application/ (ports.py, use_cases.py, dtos.py)
│   │   └── infrastructure/
│   │       ├── models.py
│   │       ├── repositories.py     # DjangoTruckEntryRepository
│   │       ├── ocr/ (google_vision_adapter.py, fake_ocr_adapter.py)
│   │       ├── storage.py          # DjangoFileStorage
│   │       ├── forms.py            # construcción dinámica del formulario
│   │       ├── views.py  urls.py  container.py
│   └── analytics/                  # tablero BI + IA
│       ├── domain/ (metrics.py, insight.py)
│       ├── application/ (ports.py, use_cases.py, dtos.py, prompts.py)
│       └── infrastructure/
│           ├── repositories.py     # DjangoMetricsRepository (consultas agregadas ORM)
│           ├── llm/ (groq_adapter.py, rule_based_adapter.py)
│           ├── models.py           # AIInsightCache
│           ├── views.py  urls.py  container.py
├── templates/                      # Atomic Design (ver sección 11)
├── static/
│   ├── css/app.css
│   └── js/ (ocr-capture.js, dynamic-form.js, dashboard-charts.js, ai-insights.js)
└── tests/
    ├── domain/  application/  infrastructure/
```

---

## 6. Autenticación y personal

- `LoginView` / `LogoutView` (POST) de Django con templates propios.
- `LOGIN_URL="login"`, `LOGIN_REDIRECT_URL="analytics:dashboard"`.
- Todas las vistas usan `LoginRequiredMixin`. Los permisos por rol usan un `RoleRequiredMixin(allowed_roles=[...])` propio.
- Roles (`Group`, creados con el comando `seed_roles`):

| Rol | Puede |
|---|---|
| `Administrador` | Todo: personal, cuestionario, histórico, tablero, revisión |
| `Supervisor` | Histórico completo, tablero BI + IA, marcar como revisado |
| `Operario` | Registrar ingresos y ver solo sus propios registros |

- `Profile` 1:1 con `User`: `document_id`, `position`, `phone`. No se crea un modelo de usuario personalizado.
- Los usuarios se desactivan (`is_active=False`), nunca se borran.
- CRUD de personal en vistas propias (rol `Administrador`) y también en Django Admin.

---

## 7. Formulario dinámico (esencia de SIGIM)

El formulario se construye desde BD, así que el administrador puede cambiar las preguntas sin tocar código.

### Modelo de datos
```
Questionnaire (id, name, is_active)
  └── Question (id, questionnaire, order, text, help_text, type, is_required,
                semantic_tag, is_active, depends_on → Question?, depends_on_value?)
        └── Choice (id, question, label, value, order)

TruckEntry (id, questionnaire, created_by → User, created_at, plate, container_code,
            container_iso_valid, status, reviewed_by?, reviewed_at?, review_comment)
  ├── Answer   (id, entry, question, value_text, value_number, value_bool, choices M2M, meta JSON)
  └── Evidence (id, entry, question?, kind, image, uploaded_at)
```

**Tipos (`Question.type`):** `text`, `number`, `boolean`, `single_choice`, `multi_choice`, `date`, `photo`, `plate_ocr`, `container_ocr`.

`plate_ocr` y `container_ocr` se renderizan como foto + botón **"Leer con IA"** + campo editable con el resultado. El usuario siempre puede corregirlo.

**`semantic_tag`:** identificador estable para encontrar preguntas sin depender de su texto. Lo usan el caso de uso de registro (copia `plate` y `container_code` a columnas de `TruckEntry`) y **el tablero BI** (suma `boxes_count`, `pallets_count`, `witness_samples_count`, etc.).

**Ramificación:** una pregunta puede depender de una pregunta anterior y un valor. `VisibilityRule.is_visible(question, answers)` es una función pura del dominio. Se usa en el servidor (las preguntas ocultas no se exigen ni se guardan) y se replica en `dynamic-form.js` para mostrar/ocultar en el navegador.

### Cuestionario semilla (`seed_questionnaire`)
| # | Pregunta | Tipo | `semantic_tag` | Depende de |
|---|---|---|---|---|
| 1 | Foto y placa del vehículo | plate_ocr | `plate` | — |
| 2 | Nombre del conductor | text | `driver_name` | — |
| 3 | Cédula del conductor | text | `driver_id` | — |
| 4 | Proveedor / transportadora | single_choice | `supplier` | — |
| 5 | ¿Trae contenedor? | boolean | `has_container` | — |
| 6 | Foto y código del contenedor | container_ocr | `container_code` | 5 = true |
| 7 | Número de sello/precinto | text | `seal_number` | 5 = true |
| 8 | ¿Sello intacto? | boolean | `seal_ok` | 5 = true |
| 9 | Tipo de carga | single_choice (estibas/cajas/granel/recipientes) | `cargo_type` | — |
| 10 | Cantidad de estibas | number | `pallets_count` | — |
| 11 | Cantidad de cajas | number | `boxes_count` | — |
| 12 | Cantidad de muestras testigo | number | `witness_samples_count` | — |
| 13 | Peso/unidad (kg o unidades) | single_choice | `unit` (va en `meta`) | — |
| 14 | Estado general del vehículo | single_choice (bueno/regular/malo) | `vehicle_condition` | — |
| 15 | ¿Hay novedades? | boolean | `has_novelty` | — |
| 16 | Tipo de novedad | multi_choice (plagas, saqueo, olores, mercancía afectada, humedad, otro) | `novelty_type` | 15 = true |
| 17 | Descripción de la novedad | text | `novelty_description` | 15 = true |
| 18 | Foto de evidencia de la novedad | photo | `novelty_photo` | 15 = true |
| 19 | Observaciones generales | text (opcional) | `observations` | — |

---

## 8. Ingreso de camiones + OCR con IA

### Flujo
1. El operario abre **Nuevo ingreso**. `GetActiveQuestionnaire` arma el formulario.
2. Para placa o contenedor: toma la foto y pulsa "Leer con IA". `ocr-capture.js` hace `fetch POST` a `/entries/ocr/plate/` o `/entries/ocr/container/` y recibe JSON. El campo se llena y aparece un badge (✅ válido / ⚠️ verificar / ❌ ISO inválido).
3. Envía el formulario. `RegisterTruckEntry` valida los requeridos visibles, la placa y el ISO, guarda respuestas y evidencias, y redirige al detalle.

### Casos de uso
- `ReadPlateWithAI(image_bytes) -> PlateReadResult(raw_text, candidate, is_valid)`
- `ReadContainerWithAI(image_bytes) -> ContainerReadResult(raw_text, candidate, is_valid, expected_check_digit)`
- `RegisterTruckEntry(RegisterEntryCommand) -> int`
- `ListEntries(filters, user) -> Page[EntrySummaryDTO]`
- `GetEntryDetail(entry_id, user) -> EntryDetailDTO`
- `ReviewEntry(entry_id, reviewer, comment) -> None`

### Adaptador Google Cloud Vision
```python
class GoogleVisionOcrAdapter(OcrService):
    """Adaptador secundario: OCR con IA usando Google Cloud Vision (TEXT_DETECTION)."""
    def __init__(self):
        from google.cloud import vision
        self._client = vision.ImageAnnotatorClient()   # usa GOOGLE_APPLICATION_CREDENTIALS

    def read_text(self, image_bytes: bytes) -> list[str]:
        from google.cloud import vision
        response = self._client.text_detection(image=vision.Image(content=image_bytes))
        if response.error.message:
            raise OcrUnavailable(response.error.message)
        if not response.text_annotations:
            return []
        return response.text_annotations[0].description.splitlines()
```
- Antes de enviar, preprocesar con Pillow: redimensionar a 1600 px máx., convertir a JPEG y corregir la orientación EXIF.
- Manejar errores de red o credenciales con `OcrUnavailable(DomainError)`. La vista responde un mensaje amigable y deja escribir a mano.
- `FakeOcrAdapter` para tests y para demos sin credenciales (`OCR_PROVIDER=fake`).

### Parsers (dominio, Template Method)
`BaseCodeParser.parse(lines)` sigue estos pasos:
1. Unir y normalizar (mayúsculas, sin espacios, guiones ni puntos).
2. Generar ventanas candidatas del largo esperado.
3. Corregir confusiones típicas **según la posición**. En posiciones de letra: `0→O 1→I 5→S 8→B 2→Z`. En posiciones de dígito: `O→0 I→1 S→5 B→8 Z→2`.
4. Devolver el primer candidato que pase `validate()`.

`PlateParser` y `ContainerCodeParser` heredan de esta base.

### Placa colombiana (`Plate`)
- Vehículo: `^[A-Z]{3}\d{3}$` (ej. `ABC123`)
- Remolque/semirremolque: `^[RS]\d{5}$` (ej. `R12345`)
- Si no hay coincidencia: se muestra el texto crudo con estado "requiere verificación".

### ISO 6346 (`entries/domain/iso6346.py`)
Formato `AAAU1234567`: 3 letras de propietario + categoría (`U`/`J`/`Z`) + 6 dígitos de serie + dígito de control.

```python
LETTER_VALUES = {
    "A": 10, "B": 12, "C": 13, "D": 14, "E": 15, "F": 16, "G": 17, "H": 18,
    "I": 19, "J": 20, "K": 21, "L": 23, "M": 24, "N": 25, "O": 26, "P": 27,
    "Q": 28, "R": 29, "S": 30, "T": 31, "U": 32, "V": 34, "W": 35, "X": 36,
    "Y": 37, "Z": 38,
}  # se saltan los múltiplos de 11

def compute_check_digit(code10: str) -> int:
    total = sum((LETTER_VALUES[c] if c.isalpha() else int(c)) * (2 ** i)
                for i, c in enumerate(code10))
    return (total % 11) % 10
```
Casos de prueba: `CSQU3054383` ✅, `MSKU9070323` ✅, `CSQU3054384` ❌.

`ContainerCode(ValueObject)` valida el patrón `^[A-Z]{3}[UJZ]\d{7}$` y el dígito de control. `InvalidContainerCode` distingue entre "formato inválido" y "dígito de control incorrecto (esperado X)".

**Regla de negocio:** un contenedor que no pasa ISO **se puede guardar**, pero con `container_iso_valid=False` y estado `con_observacion`. El usuario debe marcar un checkbox de confirmación.

### Evidencias
- Puerto `FileStorage` → `DjangoFileStorage` (usa `default_storage`).
- Ruta: `MEDIA_ROOT/evidences/<año>/<mes>/<entry_id>/`. Máximo 8 MB, solo `jpg/jpeg/png/webp`.
- Inputs con `accept="image/*" capture="environment"` para abrir la cámara trasera en tablet o celular.

---

## 9. Tablero BI + IA (`analytics`)

### Contenido
**Filtros:** hoy (por defecto) / últimos 7 días / últimos 30 días / rango personalizado.

**Tarjetas KPI:**
| KPI | Fuente |
|---|---|
| Camiones ingresados | `count(TruckEntry)` |
| Total de cajas | suma de `boxes_count` |
| Total de estibas | suma de `pallets_count` |
| Muestras testigo | suma de `witness_samples_count` |
| Ingresos con novedad | `has_novelty = true` |
| % contenedores ISO válidos | `container_iso_valid` |
| Sellos no intactos | `seal_ok = false` |
| Pendientes de revisión | `status != revisado` |

**Gráficos (Chart.js):**
- Ingresos por hora del día (barras), para ver la carga del proceso diario.
- Ingresos por día en el rango (línea).
- Novedades por tipo (barras horizontales).
- Top 5 proveedores por número de ingresos (barras).
- Estado de los registros (dona).

### Arquitectura del módulo
- `MetricsRepository` (puerto) → `DjangoMetricsRepository`, con agregaciones ORM (`annotate`, `Count`, `Sum`, `TruncHour`, `TruncDate`) sobre `Answer` filtrando por `question__semantic_tag`.
- `GetDashboardMetrics(DateRange) -> DashboardMetricsDTO` (dataclass serializable a JSON).
- `InsightGenerator` (puerto) con dos implementaciones:
  - `GroqInsightAdapter`: llama al LLM.
  - `RuleBasedInsightAdapter`: reglas fijas (p. ej. "novedades > 20 % → alerta"). Sirve de **respaldo** si Groq falla o no hay API key, y muestra el polimorfismo en la sustentación.
- `GenerateAIInsights(metrics_dto) -> list[Insight]`. Usa Groq y, si lanza `InsightUnavailable`, cae al adaptador por reglas.

### Integración con Groq
```python
class GroqInsightAdapter(InsightGenerator):
    """Adaptador secundario: interpreta métricas con un LLM vía Groq."""
    def __init__(self, api_key: str, model: str):
        from groq import Groq
        self._client = Groq(api_key=api_key)
        self._model = model

    def generate(self, metrics: DashboardMetricsDTO) -> list[Insight]:
        completion = self._client.chat.completions.create(
            model=self._model,
            temperature=0.3,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_prompt(metrics)},
            ],
        )
        return parse_insights(completion.choices[0].message.content)
```

**Prompt (`analytics/application/prompts.py`):**
- Sistema: "Eres un analista de logística de recibo de mercancía. Recibes métricas agregadas en JSON. Responde **solo** JSON con la forma `{"insights":[{"level":"info|warning|alert","title":"...","message":"..."}]}`, máximo 5 insights, en español, frases cortas, sin inventar datos que no estén en el JSON."
- Usuario: el `DashboardMetricsDTO` en JSON + el rango de fechas + una comparación con el periodo anterior, si existe.
- **Solo se envían datos agregados.** Nunca nombres, cédulas ni placas individuales (privacidad).

**Validación de la respuesta:** `parse_insights` hace `json.loads`, valida `level` contra el enum `InsightLevel` del dominio, recorta a 5 y, si el JSON es inválido, lanza `InsightUnavailable`, que activa el respaldo por reglas.

**Caché y límites del plan gratuito:**
- El tablero carga las métricas al instante. Los insights se generan solo con el botón **"Analizar con IA"** (`ai-insights.js` → `POST /analytics/insights/`).
- Modelo `AIInsightCache(range_key, metrics_hash, payload JSON, model_used, created_at)`. Si el hash de las métricas no cambió, se devuelve lo guardado sin volver a llamar a Groq.
- `timeout` de 20 s en el cliente.

**UI de insights:** organismo `ai_insights_panel` con tarjetas coloreadas por nivel (info = azul, warning = amarillo, alert = rojo), la etiqueta "Generado por IA · modelo X · hora" y un aviso de que es una interpretación automática.

---

## 10. Histórico

- Tabla paginada (20 por página): fecha y hora (`America/Bogota`), placa, contenedor, ISO ✅/❌, proveedor, registrado por, estado (badge), ¿novedad?
- Filtros: rango de fechas, placa, contenedor, estado, con/sin novedad, usuario.
- **Línea de estado/fase** como en SIGIM: `registrado` → `con_observacion` (si aplica) → `revisado`. Se muestra como stepper en el detalle.
- Detalle: respuestas visibles en orden, galería de evidencias, resultado ISO (dígito leído vs. esperado), datos de la revisión.
- Supervisor/Admin: botón "Marcar como revisado" con comentario. El operario ve solo sus registros.
- Exportar a CSV lo filtrado (opcional).

---

## 11. Frontend con Atomic Design (Django Templates)

Atomic Design se mapea directo a Django: **`{% include %}` compone** (átomos → moléculas → organismos) y **`{% extends %}` hereda** (layouts → páginas). Cada componente es un `.html` pequeño que recibe sus datos con `with`.

```
templates/
├── atoms/              # piezas mínimas, sin lógica
│   ├── button.html          # params: label, variant, type, icon, id
│   ├── input.html           # params: name, type, value, placeholder, required
│   ├── label.html
│   ├── badge.html           # params: text, variant (success|warning|danger|info)
│   ├── icon.html            # Bootstrap Icons
│   ├── spinner.html
│   └── image_thumb.html
├── molecules/          # combinación de átomos con un propósito
│   ├── form_field.html      # label + input + help + error
│   ├── photo_capture.html   # input cámara + preview
│   ├── ocr_field.html       # photo_capture + botón "Leer con IA" + input editable + badge
│   ├── kpi_card.html        # icono + valor + título + variación
│   ├── search_bar.html
│   ├── filter_group.html
│   ├── insight_card.html    # nivel + título + mensaje
│   └── status_badge.html    # mapea estado → badge
├── organisms/          # secciones completas de la interfaz
│   ├── navbar.html
│   ├── dynamic_form.html    # itera preguntas e incluye la molécula según question.type
│   ├── entries_table.html
│   ├── entries_filters.html
│   ├── kpi_grid.html
│   ├── chart_panel.html     # <canvas> + título
│   ├── ai_insights_panel.html
│   ├── evidence_gallery.html
│   ├── status_timeline.html
│   └── staff_table.html
├── layouts/            # "templates" de Atomic Design (estructura sin datos)
│   ├── base.html            # <head>, CDNs, bloques
│   ├── auth_layout.html     # extends base: centrado, sin navbar
│   └── app_layout.html      # extends base: navbar + contenedor + mensajes
└── pages/              # vistas concretas con datos reales
    ├── auth/login.html
    ├── entries/create.html   entries/list.html   entries/detail.html
    ├── analytics/dashboard.html
    └── staff/list.html   staff/form.html
```

Ejemplos de uso:
```django
{# molecules/kpi_card.html #}
<div class="card kpi-card h-100">
  <div class="card-body">
    {% include "atoms/icon.html" with name=icon %}
    <div class="kpi-value">{{ value }}</div>
    <div class="kpi-title">{{ title }}</div>
  </div>
</div>

{# organisms/kpi_grid.html #}
<div class="row g-3">
  {% for kpi in kpis %}
    <div class="col-6 col-md-3">
      {% include "molecules/kpi_card.html" with icon=kpi.icon value=kpi.value title=kpi.title %}
    </div>
  {% endfor %}
</div>

{# pages/analytics/dashboard.html #}
{% extends "layouts/app_layout.html" %}
{% block content %}
  {% include "organisms/kpi_grid.html" %}
  {% include "organisms/ai_insights_panel.html" %}
{% endblock %}
```

**Reglas del frontend**
- Los átomos no conocen modelos: solo reciben parámetros.
- Ninguna lógica de negocio en templates. Las vistas entregan DTOs ya listos para mostrar.
- JS vanilla en `static/js/`, un archivo por comportamiento, cargado solo en la página que lo necesita (`{% block scripts %}`).
- Bootstrap 5, Bootstrap Icons y Chart.js por CDN. Sin npm ni build.
- Diseño **pensado para tablet** (como SIGIM): una columna en el formulario, botones y campos grandes.

---

## 12. URLs

```
/                                → redirect al tablero (supervisor/admin) o a nuevo ingreso (operario)
/accounts/login/  /accounts/logout/
/entries/                        → histórico
/entries/new/                    → nuevo ingreso
/entries/<id>/                   → detalle
/entries/<id>/review/            → POST revisar (supervisor/admin)
/entries/ocr/plate/              → POST imagen → JSON
/entries/ocr/container/          → POST imagen → JSON
/analytics/                      → tablero BI
/analytics/metrics/?range=...    → JSON para los gráficos
/analytics/insights/             → POST → JSON con insights de IA
/staff/  /staff/new/  /staff/<id>/edit/
/admin/
```

---

## 13. Configuración

`.env.example`
```
DEBUG=True
SECRET_KEY=change-me
ALLOWED_HOSTS=localhost,127.0.0.1
DATABASE_URL=sqlite:///db.sqlite3
TIME_ZONE=America/Bogota

# IA - OCR
OCR_PROVIDER=google            # google | fake
GOOGLE_APPLICATION_CREDENTIALS=./credentials/vision-sa.json

# IA - LLM
INSIGHT_PROVIDER=groq          # groq | rules
GROQ_API_KEY=
GROQ_MODEL=openai/gpt-oss-120b # verificar modelos disponibles en console.groq.com

MAX_UPLOAD_MB=8
```
- `credentials/` y `.env` van en `.gitignore`.
- `settings.py`: `LANGUAGE_CODE="es-co"`, `USE_TZ=True`, `TEMPLATES[0]["DIRS"]=[BASE_DIR/"templates"]`, `STATICFILES_DIRS`, `MEDIA_*`.

`requirements.txt`: `Django`, `django-environ`, `Pillow`, `google-cloud-vision`, `groq`, `pytest`, `pytest-django`.

---

## 14. Pruebas mínimas

- **Dominio:** `iso6346` (válidos, inválidos, formato), `Plate`, `ContainerCode`, `PlateParser` / `ContainerCodeParser` con confusiones O/0, I/1, S/5, B/8, `VisibilityRule`.
- **Aplicación** (adaptadores falsos e in-memory): `RegisterTruckEntry` (requeridos, preguntas ocultas, ISO inválido → `con_observacion`), `ReadContainerWithAI` con `FakeOcrAdapter`, `GenerateAIInsights` con un generador que falla (debe caer al de reglas), `parse_insights` con JSON inválido.
- **Infraestructura:** login requerido, permisos por rol, el operario no ve registros ajenos, endpoints OCR con Vision mockeado, métricas agregadas correctas sobre datos semilla.
- Comando `seed_demo_data` que cree unos 60 ingresos repartidos en 14 días, para que el tablero se vea con datos en la demo.

---

## 15. Orden de implementación

1. Proyecto Django, `settings`, `.env`, `shared/` (clases base), `layouts/` + átomos básicos, login/logout.
2. Dominio de `entries`: `iso6346`, `Plate`, `ContainerCode`, parsers + tests.
3. `questionnaire`: modelos, admin, `VisibilityRule`, `seed_questionnaire`.
4. `entries`: modelos, repositorio, `RegisterTruckEntry`, organismo `dynamic_form`, página de nuevo ingreso (con `FakeOcrAdapter`).
5. IA de OCR: `GoogleVisionOcrAdapter`, endpoints JSON, `ocr-capture.js`, molécula `ocr_field`.
6. Evidencias fotográficas.
7. Histórico: lista, filtros, detalle, línea de estado, revisión.
8. Roles (`seed_roles`), `RoleRequiredMixin`, gestión de personal.
9. `analytics`: `DjangoMetricsRepository`, KPIs, gráficos, `seed_demo_data`.
10. IA de insights: `RuleBasedInsightAdapter` primero, luego `GroqInsightAdapter`, caché y panel.
11. Pulido para tablet, tests de infraestructura y README con un diagrama de capas.

---

## 16. Convenciones para el asistente

- Código, clases y variables en **inglés**. Textos de UI, mensajes y docstrings en **español**.
- Type hints en todo dominio y aplicación. `@dataclass(frozen=True)` para value objects y DTOs.
- El dominio **no importa Django**. Si hace falta, es señal de que el código va en infraestructura.
- Vistas delgadas: leen el request, obtienen el caso de uso de `container.py`, ejecutan y renderizan.
- Cada puerto tiene al menos un adaptador real y uno falso o de respaldo.
- Docstring de una línea en cada clase indicando capa y rol (p. ej. "Caso de uso (aplicación): ...").
- Implementar por pasos según la sección 15. No generar todo el proyecto de una vez.
