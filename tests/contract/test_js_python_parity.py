"""Contrato Python ↔ JavaScript: las reglas replicadas en el navegador deben coincidir con el dominio.

- static/js/ocr-capture.js replica ISO 6346 y el formato de placa (feedback inmediato al escribir).
- static/js/dynamic-form.js replica VisibilityRule (ramificación del formulario).
Se extraen las funciones del archivo JS y se ejecutan con Node sobre los mismos casos que Python.
"""
import json
import random
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from apps.entries.domain import iso6346
from apps.entries.domain.value_objects import TRAILER_PLATE, VEHICLE_PLATE, normalize
from apps.questionnaire.domain.visibility import _matches

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="Node.js no está instalado")
JS_DIR = Path(__file__).resolve().parents[2] / "static" / "js"


def extract(source: str, header: str) -> str:
    """Devuelve el texto desde `header` hasta su llave/; de cierre balanceada."""
    start = source.index(header)
    depth, i = 0, source.index("{", start)
    while True:
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                return source[start : end + (1 if source[end : end + 1] == ";" else 0)]
        i += 1


def run_node(script: str):
    completed = subprocess.run([NODE, "-e", script], capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


OCR_JS = (JS_DIR / "ocr-capture.js").read_text(encoding="utf-8")
FORM_JS = (JS_DIR / "dynamic-form.js").read_text(encoding="utf-8")


def sample_codes(n=300):
    rng = random.Random(6346)
    codes = ["CSQU3054383", "CSQU3054384", "MSKU9070323", "ABCJ0000000", "ABCZ9999999", "ABCX1234567", "AB1U1234567", "", "csqu 305438-3"]
    for _ in range(n):
        owner = "".join(rng.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ") for _ in range(3)) + rng.choice("UJZ")
        codes.append(owner + "".join(rng.choice("0123456789") for _ in range(7)))
    return codes


def test_iso6346_check_digit_parity():
    codes = [c for c in sample_codes() if iso6346.has_valid_format(c)]
    script = "\n".join([
        extract(OCR_JS, "var LETTER ="), extract(OCR_JS, "function checkDigit"),
        f"console.log(JSON.stringify({json.dumps(codes)}.map(c => checkDigit(c.slice(0, 10)))));",
    ])
    assert run_node(script) == [iso6346.compute_check_digit(c[:10]) for c in codes]


def python_evaluate(kind: str, value: str) -> str:
    v = normalize(value)
    if not v:
        return "idle"
    if kind == "plate":
        return "valid" if VEHICLE_PLATE.match(v) or TRAILER_PLATE.match(v) else "verify"
    if not iso6346.has_valid_format(v):
        return "verify"
    return "valid" if iso6346.is_valid(v) else "invalid"


def test_live_validation_states_parity():
    plates = ["abc123", "ABC-123", "R12345", "s 98765", "T12345", "AB1234", "", "  ", "abc.12.3", "ABC1234"]
    cases = [("plate", p) for p in plates] + [("container", c) for c in sample_codes(100)]
    script = "\n".join([
        extract(OCR_JS, "var LETTER ="), extract(OCR_JS, "function normalize"), extract(OCR_JS, "function checkDigit"),
        extract(OCR_JS, "function evaluate"),
        f"console.log(JSON.stringify({json.dumps(cases)}.map(([k, v]) => evaluate(k, v).state)));",
    ])
    assert run_node(script) == [python_evaluate(k, v) for k, v in cases]


def test_normalize_parity():
    samples = ["abc 123", "a-b.c", "\tx\ny ", "ÁÉÍ ñ", "", "CSQU 305438-3"]
    script = extract(OCR_JS, "function normalize") + f"\nconsole.log(JSON.stringify({json.dumps(samples)}.map(normalize)));"
    assert run_node(script) == [normalize(s) for s in samples]


def test_visibility_matching_parity():
    """El navegador recibe strings ("true"/"false", valores de opción) y listas para selección múltiple."""
    cases = [
        ("true", "true"), ("TRUE", "true"), (" true ", "true"), ("false", "true"), ("", "true"), (None, "true"),
        ([], "pests"), (["odors", "pests"], "pests"), (["odors"], "pests"), (["PESTS"], "pests"), ("otro", "Otro"),
    ]
    script = "\n".join([
        extract(FORM_JS, "function norm"), extract(FORM_JS, "function matches"),
        f"console.log(JSON.stringify({json.dumps(cases)}.map(([raw, exp]) => matches(raw, exp))));",
    ])
    assert run_node(script) == [_matches(raw, expected) for raw, expected in cases]


def test_extractor_finds_every_replicated_rule():
    """Si alguien renombra una función replicada, esta prueba avisa antes que las de paridad."""
    for header in ("var LETTER =", "function normalize", "function checkDigit", "function evaluate"):
        assert extract(OCR_JS, header)
    for header in ("function norm", "function matches"):
        assert extract(FORM_JS, header)
    assert re.search(r"/\^\[A-Z\]\{3\}\[UJZ\]\\d\{7\}\$/", OCR_JS), "el patrón ISO del JS cambió"
