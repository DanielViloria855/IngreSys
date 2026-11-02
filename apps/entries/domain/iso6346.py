"""Dominio (entries): regla ISO 6346 para códigos de contenedor (AAAU1234567)."""
import re

LETTER_VALUES = {
    "A": 10, "B": 12, "C": 13, "D": 14, "E": 15, "F": 16, "G": 17, "H": 18,
    "I": 19, "J": 20, "K": 21, "L": 23, "M": 24, "N": 25, "O": 26, "P": 27,
    "Q": 28, "R": 29, "S": 30, "T": 31, "U": 32, "V": 34, "W": 35, "X": 36,
    "Y": 37, "Z": 38,
}  # se saltan los múltiplos de 11

FORMAT_PATTERN = re.compile(r"^[A-Z]{3}[UJZ]\d{7}$")


def compute_check_digit(code10: str) -> int:
    """Dígito de control de los primeros 10 caracteres (3 letras de dueño + categoría + 6 dígitos)."""
    total = sum(
        (LETTER_VALUES[c] if c.isalpha() else int(c)) * (2**i)
        for i, c in enumerate(code10)
    )
    return (total % 11) % 10


def has_valid_format(code: str) -> bool:
    """¿Cumple `AAAU1234567`? (no revisa el dígito de control)."""
    return bool(FORMAT_PATTERN.match(code))


def is_valid(code: str) -> bool:
    """Formato correcto y dígito de control correcto."""
    return has_valid_format(code) and compute_check_digit(code[:10]) == int(code[10])
