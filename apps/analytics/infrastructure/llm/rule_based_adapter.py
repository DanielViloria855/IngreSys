"""Infraestructura (analytics): generador de insights por reglas fijas (respaldo y demo sin internet)."""
from apps.analytics.application.dtos import DashboardMetricsDTO
from apps.analytics.application.ports import InsightGenerator
from apps.analytics.domain.insight import Insight, InsightLevel

SEVERITY = {InsightLevel.ALERT: 0, InsightLevel.WARNING: 1, InsightLevel.INFO: 2}


class RuleBasedInsightAdapter(InsightGenerator):
    """Adaptador secundario: reglas fijas (p. ej. novedades > 20 % → alerta). Mismo puerto que Groq (polimorfismo)."""

    model_name = "Reglas automáticas"

    def generate(self, metrics: DashboardMetricsDTO) -> list[Insight]:
        m = metrics
        if m.trucks == 0:
            return [Insight(InsightLevel.INFO, "Sin ingresos", f"No hay camiones registrados en {m.range_label.lower()}.")]

        found: list[Insight] = []
        novelty_rate = m.novelty_entries / m.trucks * 100
        if novelty_rate > 20:
            found.append(Insight(InsightLevel.ALERT, "Novedades por encima del límite",
                                 f"{m.novelty_entries} de {m.trucks} ingresos ({novelty_rate:.0f} %) reportan novedad. Revisa las causas."))
        elif novelty_rate > 10:
            found.append(Insight(InsightLevel.WARNING, "Novedades en aumento",
                                 f"{novelty_rate:.0f} % de los ingresos tienen novedad ({m.novelty_entries} de {m.trucks})."))
        if m.novelty_by_type:
            top = m.novelty_by_type[0]
            found.append(Insight(InsightLevel.INFO, "Novedad más frecuente", f"«{top.label}» aparece {int(top.value)} veces en el periodo."))

        if m.iso_valid_pct is not None:
            if m.iso_valid_pct < 70:
                found.append(Insight(InsightLevel.ALERT, "Contenedores con ISO inválido",
                                     f"Solo {m.iso_valid_pct:.0f} % de los contenedores pasa la validación ISO 6346."))
            elif m.iso_valid_pct < 90:
                found.append(Insight(InsightLevel.WARNING, "Revisar códigos de contenedor",
                                     f"{m.iso_valid_pct:.0f} % de los contenedores es válido; el resto requiere verificación."))
        if m.seals_not_ok > 0:
            found.append(Insight(InsightLevel.ALERT, "Sellos no intactos",
                                 f"{m.seals_not_ok} ingreso(s) con sello no intacto. Conviene inspección prioritaria."))
        if m.pending_review and m.pending_review / m.trucks > 0.5:
            found.append(Insight(InsightLevel.WARNING, "Revisiones pendientes",
                                 f"{m.pending_review} de {m.trucks} ingresos aún no se revisan."))

        if m.supplier_issues:
            worst = m.supplier_issues[0]
            overall = sum(s.with_issue for s in m.supplier_issues) / max(sum(s.entries for s in m.supplier_issues), 1) * 100
            if worst.issue_rate_pct >= 35 and worst.issue_rate_pct >= overall * 1.4:
                found.append(Insight(
                    InsightLevel.WARNING, f"Proveedor con más incidencias: {worst.supplier}",
                    f"{worst.with_issue} de {worst.entries} ingresos ({worst.issue_rate_pct:.0f} %) tuvieron novedad, sello no intacto o ISO inválido "
                    f"(novedades {worst.novelty}, sellos {worst.seals_not_ok}, ISO {worst.iso_invalid}).",
                ))

        peak = max(m.by_hour, key=lambda p: p.value)
        if peak.value > 0:
            found.append(Insight(InsightLevel.INFO, "Hora pico", f"La mayor carga llega hacia las {peak.label} ({int(peak.value)} ingresos)."))
        change = m.deltas.get("trucks")
        if change is not None and abs(change) >= 25:
            direction = "subió" if change > 0 else "bajó"
            found.append(Insight(InsightLevel.INFO, "Cambio de volumen", f"El volumen de camiones {direction} {abs(change):.0f} % frente al periodo anterior."))

        if not found:
            found.append(Insight(InsightLevel.INFO, "Operación estable", "No se detectan desviaciones relevantes en el periodo."))
        found.sort(key=lambda i: SEVERITY[i.level])
        return found[:5]
