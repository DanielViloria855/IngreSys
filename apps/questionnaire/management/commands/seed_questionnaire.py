"""Crea el cuestionario semilla de ingreSys (19 preguntas, con ramificación)."""
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.questionnaire.infrastructure.models import Choice, Question, Questionnaire

SUPPLIERS = ["Transportes Andina", "Logística del Caribe", "Carga Express", "Frontera Cargo", "TransMar S.A.", "Otro"]
CARGO = [("Estibas", "pallets"), ("Cajas", "boxes"), ("Granel", "bulk"), ("Recipientes", "containers")]
UNITS = [("Kilogramos", "kg"), ("Unidades", "units")]
CONDITION = [("Bueno", "good"), ("Regular", "fair"), ("Malo", "bad")]
NOVELTIES = [
    ("Plagas", "pests"), ("Saqueo", "looting"), ("Olores", "odors"),
    ("Mercancía afectada", "damaged"), ("Humedad", "humidity"), ("Otro", "other"),
]

# (tag, texto, tipo, obligatoria, depende_de_tag, valor, opciones, ayuda)
SPEC = [
    ("plate", "Foto y placa del vehículo", "plate_ocr", True, None, "", None, "Toma la foto y pulsa «Leer con IA». Puedes corregir el texto."),
    ("driver_name", "Nombre del conductor", "text", True, None, "", None, ""),
    ("driver_id", "Cédula del conductor", "text", True, None, "", None, ""),
    ("supplier", "Proveedor / transportadora", "single_choice", True, None, "", [(s, s.lower().replace(" ", "_").replace(".", "")) for s in SUPPLIERS], ""),
    ("has_container", "¿Trae contenedor?", "boolean", True, None, "", None, ""),
    ("container_code", "Foto y código del contenedor", "container_ocr", True, "has_container", "true", None, "Se valida con la norma ISO 6346."),
    ("seal_number", "Número de sello/precinto", "text", True, "has_container", "true", None, ""),
    ("seal_ok", "¿Sello intacto?", "boolean", True, "has_container", "true", None, ""),
    ("cargo_type", "Tipo de carga", "single_choice", True, None, "", CARGO, ""),
    ("pallets_count", "Cantidad de estibas", "number", False, None, "", None, ""),
    ("boxes_count", "Cantidad de cajas", "number", False, None, "", None, ""),
    ("witness_samples_count", "Cantidad de muestras testigo", "number", False, None, "", None, ""),
    ("unit", "Peso / unidad (kg o unidades)", "single_choice", False, None, "", UNITS, ""),
    ("vehicle_condition", "Estado general del vehículo", "single_choice", True, None, "", CONDITION, ""),
    ("has_novelty", "¿Hay novedades?", "boolean", True, None, "", None, ""),
    ("novelty_type", "Tipo de novedad", "multi_choice", True, "has_novelty", "true", NOVELTIES, "Puedes marcar varias."),
    ("novelty_description", "Descripción de la novedad", "text", True, "has_novelty", "true", None, ""),
    ("novelty_photo", "Foto de evidencia de la novedad", "photo", False, "has_novelty", "true", None, ""),
    ("observations", "Observaciones generales", "text", False, None, "", None, ""),
]


class Command(BaseCommand):
    help = "Crea (o recrea con --reset) el cuestionario semilla."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Borra el cuestionario semilla existente antes de crearlo.")

    @transaction.atomic
    def handle(self, *args, **options):
        existing = Questionnaire.objects.filter(name="Ingreso de camiones")
        if existing.exists() and not options["reset"]:
            self.stdout.write("Ya existe el cuestionario semilla (usa --reset para recrearlo).")
            return
        if options["reset"]:
            try:
                existing.delete()
            except Exception as exc:  # preguntas con respuestas protegidas
                self.stderr.write(f"No se pudo borrar (hay ingresos registrados): {exc}")
                return

        questionnaire = Questionnaire.objects.create(name="Ingreso de camiones", is_active=True)
        by_tag: dict[str, Question] = {}
        for order, (tag, text, qtype, required, dep_tag, dep_value, options_, help_text) in enumerate(SPEC, start=1):
            question = Question.objects.create(
                questionnaire=questionnaire, order=order, text=text, help_text=help_text, type=qtype,
                is_required=required, semantic_tag=tag,
                depends_on=by_tag.get(dep_tag) if dep_tag else None, depends_on_value=dep_value,
            )
            by_tag[tag] = question
            for position, (label, value) in enumerate(options_ or [], start=1):
                Choice.objects.create(question=question, label=label, value=value, order=position)
        self.stdout.write(self.style.SUCCESS(f"Cuestionario creado con {len(SPEC)} preguntas."))
