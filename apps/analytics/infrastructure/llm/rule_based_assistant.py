"""Infraestructura (analytics): asistente por reglas (respaldo y demo sin internet).

Interpreta la pregunta por palabras clave y responde con las métricas del periodo.
Mismo puerto que el asistente con LLM (polimorfismo): el caso de uso no distingue cuál usa.
"""
import unicodedata
from datetime import timedelta

from apps.analytics.application.dtos import AskQuery, DashboardMetricsDTO
from apps.analytics.application.ports import AnalyticsAssistant

EVENING_HOUR = 18  # después de esta hora se considera «fuera de horario»


def _norm(text: str) -> str:
    """Minúsculas y sin tildes, para comparar palabras clave."""
    return "".join(c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn")


def _top(points, n: int = 1):
    return sorted((p for p in points if p.value), key=lambda p: -p.value)[:n]


class RuleBasedAssistantAdapter(AnalyticsAssistant):
    """Adaptador secundario: responde con reglas fijas sobre las métricas (sin IA)."""

    model_name = "Reglas automáticas"

    def answer(self, query: AskQuery) -> str:
        m = query.metrics
        if m.trucks == 0:
            return f"No hay ingresos registrados en {m.range_label}, así que no hay datos para responder."
        question = _norm(query.question)
        for keywords, handler in self._intents(query):
            if any(word in question for word in keywords):
                return handler(m)
        return (
            "No puedo responder esa pregunta con los datos disponibles. Puedo ayudar con: proveedores, horas pico, "
            "novedades, contenedores ISO, sellos, revisiones pendientes, volumen por día y resumen del periodo."
        )

    def _intents(self, query: AskQuery):
        return [
            (("recomien", "sugier", "que hago", "que hacer", "que deberia", "accion", "priorizar"), lambda m: self._recommend(m)),
            (("manana", "pronostic", "predic", "proyecc", "esperar", "proximo", "se viene"), lambda m: self._forecast(m, query)),
            (("patron", "recurrente", "se repite"), lambda m: self._patterns(m, query)),
            (("proveedor", "transportadora", "empresa"), self._suppliers),
            (("sello", "precinto"), self._seals),
            (("iso", "contenedor"), self._iso),
            (("pendiente", "revision", "revisar", "sin revisar"), self._pending),
            (("novedad", "problema", "incidencia", "humedad", "plaga"), self._novelty),
            (("hora", "pico", "horario", "cuando llegan"), self._hours),
            (("dia", "semana", "tendencia", "fin de semana", "lunes", "martes", "sabado", "domingo"), self._days),
            (("caja", "estiba", "muestra", "carga", "promedio"), self._cargo),
            (("resumen", "como va", "estado", "panorama", "general"), self._summary),
            (("camion", "ingreso", "volumen", "cuantos", "llegaron"), self._trucks),
        ]

    # -- respuestas ---------------------------------------------------------------------
    @staticmethod
    def _recommend(m: DashboardMetricsDTO) -> str:
        actions = []
        if m.pending_review and m.pending_review / m.trucks > 0.3:
            actions.append(f"Priorizar la revisión de los {m.pending_review} ingresos pendientes ({m.pending_review / m.trucks * 100:.0f} %).")
        if m.supplier_issues and m.supplier_issues[0].issue_rate_pct >= 35:
            w = m.supplier_issues[0]
            actions.append(f"Inspeccionar con prioridad los ingresos de {w.supplier}: {w.issue_rate_pct:.0f} % tuvo novedad, sello roto o ISO inválido.")
        if m.seals_not_ok:
            actions.append(f"Verificar los {m.seals_not_ok} ingresos con sello no intacto.")
        if m.iso_valid_pct is not None and m.iso_valid_pct < 90:
            actions.append(f"Reforzar la verificación de códigos de contenedor (solo {m.iso_valid_pct:.0f} % pasa ISO 6346).")
        peak = _top(m.by_hour)
        if peak:
            actions.append(f"Reforzar la portería hacia las {peak[0].label}, que es la hora de mayor carga.")
        late = sum(p.value for p in m.by_hour if int(p.label[:2]) >= EVENING_HOUR)
        if late:
            actions.append(f"Revisar los {int(late)} ingresos fuera de horario (desde las {EVENING_HOUR}h).")
        if not actions:
            return "Los datos del periodo no muestran desviaciones relevantes: se sugiere mantener la operación actual."
        numbered = " ".join(f"{i}) {text}" for i, text in enumerate(actions[:4], start=1))
        return f"Sugerencias según los datos de {m.range_label}: {numbered}"

    @staticmethod
    def _forecast(m: DashboardMetricsDTO, query: AskQuery) -> str:
        ref = query.reference or m
        if query.today is None or ref.days < 7 or not any(p.value for p in ref.weekday_average):
            return "No hay suficiente historial por día de la semana para estimar el volumen de mañana."
        point = ref.weekday_average[(query.today + timedelta(days=1)).weekday()]
        active = [p.value for p in ref.weekday_average if p.value]
        typical = sum(active) / len(active)
        if point.value == 0:
            return f"Mañana es {point.label.lower()}: en los últimos {ref.days} días no hubo ingresos ese día de la semana."
        level = "por encima" if point.value > typical * 1.15 else ("por debajo" if point.value < typical * 0.85 else "en línea")
        return (f"Mañana es {point.label.lower()}. En los últimos {ref.days} días ese día promedió {point.value:.0f} camiones, "
                f"{level} del promedio general ({typical:.0f}). Es una estimación basada en el histórico, no una certeza.")

    def _patterns(self, m: DashboardMetricsDTO, query: AskQuery) -> str:
        ref = query.reference or m
        parts = []
        weekday = _top(ref.weekday_average)
        if weekday:
            parts.append(f"El día de la semana con más movimiento es el {weekday[0].label.lower()} (promedio {weekday[0].value:.0f} camiones).")
        peak = _top(ref.by_hour)
        if peak:
            parts.append(f"La hora más cargada es {peak[0].label} ({int(peak[0].value)} ingresos).")
        if ref.novelty_by_type:
            parts.append(f"La novedad más repetida es «{ref.novelty_by_type[0].label}» ({int(ref.novelty_by_type[0].value)} reportes).")
        if ref.supplier_issues:
            w = ref.supplier_issues[0]
            parts.append(f"El proveedor que más repite incidencias es {w.supplier} ({w.issue_rate_pct:.0f} % de sus ingresos).")
        return f"Patrones en los últimos {ref.days} días: " + " ".join(parts) if parts else "No hay datos suficientes para identificar patrones."

    @staticmethod
    def _suppliers(m: DashboardMetricsDTO) -> str:
        parts = []
        if m.supplier_issues:
            w = m.supplier_issues[0]
            parts.append(
                f"El proveedor con mayor proporción de incidencias es {w.supplier}: {w.with_issue} de {w.entries} ingresos "
                f"({w.issue_rate_pct:.0f} %) con novedad, sello no intacto o ISO inválido."
            )
        if m.top_suppliers:
            t = m.top_suppliers[0]
            parts.append(f"El que más ingresos tiene es {t.label} con {int(t.value)}.")
        return " ".join(parts) or "No hay datos de proveedores en el periodo."

    @staticmethod
    def _seals(m: DashboardMetricsDTO) -> str:
        if not m.seals_not_ok:
            return "Ningún ingreso con contenedor reportó sello no intacto en el periodo."
        return f"{m.seals_not_ok} ingreso(s) reportaron sello no intacto en {m.range_label}. Conviene una inspección prioritaria."

    @staticmethod
    def _iso(m: DashboardMetricsDTO) -> str:
        if not m.containers_total:
            return "No hubo ingresos con contenedor en el periodo."
        invalid = m.containers_total - m.containers_iso_valid
        return (f"De {m.containers_total} contenedores, {m.containers_iso_valid} pasaron la validación ISO 6346 "
                f"({m.iso_valid_pct:.0f} %) y {invalid} no.")

    @staticmethod
    def _pending(m: DashboardMetricsDTO) -> str:
        return f"Hay {m.pending_review} de {m.trucks} ingresos pendientes de revisión ({m.pending_review / m.trucks * 100:.0f} %)."

    @staticmethod
    def _novelty(m: DashboardMetricsDTO) -> str:
        text = f"{m.novelty_entries} de {m.trucks} ingresos ({m.novelty_entries / m.trucks * 100:.0f} %) reportaron novedad."
        if m.novelty_by_type:
            top = m.novelty_by_type[0]
            text += f" La más frecuente es «{top.label}» con {int(top.value)} reportes."
        worst = _top(m.novelty_by_day)
        if worst and m.days > 1:
            text += f" El día con más novedades fue el {worst[0].label} ({int(worst[0].value)})."
        return text

    @staticmethod
    def _hours(m: DashboardMetricsDTO) -> str:
        top = _top(m.by_hour, 2)
        if not top:
            return "No hay ingresos con hora registrada en el periodo."
        text = f"La hora pico es {top[0].label} con {int(top[0].value)} ingresos"
        text += f" y le sigue {top[1].label} con {int(top[1].value)}." if len(top) > 1 else "."
        late = sum(p.value for p in m.by_hour if int(p.label[:2]) >= EVENING_HOUR)
        if late:
            text += f" Hubo {int(late)} ingreso(s) fuera del horario habitual (desde las {EVENING_HOUR}h)."
        return text

    @staticmethod
    def _days(m: DashboardMetricsDTO) -> str:
        parts = []
        busiest = _top(m.by_day)
        if busiest and m.days > 1:
            parts.append(f"El día con más ingresos fue el {busiest[0].label} ({int(busiest[0].value)}).")
        weekday = _top(m.by_weekday)
        if weekday and m.days > 1:
            parts.append(f"Por día de la semana, el de mayor movimiento es el {weekday[0].label.lower()} ({int(weekday[0].value)} ingresos).")
        change = m.deltas.get("trucks")
        if change is not None:
            parts.append(f"El volumen {'subió' if change > 0 else 'bajó'} {abs(change):.0f} % frente al periodo anterior.")
        return " ".join(parts) or "El periodo es de un solo día; amplíe el rango para ver tendencias."

    @staticmethod
    def _cargo(m: DashboardMetricsDTO) -> str:
        per_truck = m.boxes / m.trucks
        return (f"Se recibieron {m.boxes:,} cajas, {m.pallets:,} estibas y {m.witness_samples:,} muestras testigo "
                f"en {m.trucks} ingresos (promedio {per_truck:.0f} cajas por camión).").replace(",", ".")

    def _summary(self, m: DashboardMetricsDTO) -> str:
        return " ".join([self._trucks(m), self._novelty(m), self._iso(m), self._pending(m)])

    @staticmethod
    def _trucks(m: DashboardMetricsDTO) -> str:
        text = f"Ingresaron {m.trucks} camiones en {m.range_label}."
        change = m.deltas.get("trucks")
        if change is not None:
            text += f" Es {abs(change):.0f} % {'más' if change > 0 else 'menos'} que el periodo anterior."
        return text
