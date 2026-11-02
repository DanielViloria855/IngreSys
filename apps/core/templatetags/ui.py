"""Infraestructura: filtros de presentación (solo formato, sin lógica de negocio)."""
from django import template
from django.utils.html import format_html

register = template.Library()


@register.filter
def container_fmt(code: str):
    """CSQU3054383 → «CSQU 305438 3» con el dígito de control resaltado."""
    code = (code or "").strip()
    if len(code) != 11:
        return code
    return format_html('{} {} <span class="cd">{}</span>', code[:4], code[4:10], code[10])
