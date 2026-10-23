"""Mismas reglas de puntaje que pages/0_Actas.py, para no divergir de Looker."""

from __future__ import annotations

import re
import unicodedata
from typing import Optional, Tuple


def _normalizar_desde_hoja(x: float) -> float:
    if x != x or x <= 0:
        return x
    x = float(x)
    while x > 1000 and abs(x - round(x)) < 1e-4:
        ri = int(round(x))
        if ri % 100 != 0:
            break
        x = x / 100.0
    return x


def parse_puntaje_valor(val) -> Optional[float]:
    if val is None or val == "":
        return None
    if isinstance(val, (int, float)):
        x = float(val)
        if x != x:
            return None
        return _normalizar_desde_hoja(x)
    s = unicodedata.normalize("NFKC", str(val))
    s = re.sub(r"\s+", "", s)
    if not s or s.lower() in ("nan", "none"):
        return None
    m = re.match(r"^(\d{1,4})([.,])(\d{1,4})$", s)
    if m:
        whole, _sep, frac = m.groups()
        try:
            return _normalizar_desde_hoja(float("{}.{}".format(whole, frac)))
        except ValueError:
            return None
    m2 = re.match(r"^(\d{1,3}(?:\.\d{3})+),(\d+)$", s)
    if m2:
        whole = m2.group(1).replace(".", "")
        try:
            return _normalizar_desde_hoja(float("{}.{}".format(whole, m2.group(2))))
        except ValueError:
            return None
    if re.match(r"^(\d{1,4})$", s):
        return _normalizar_desde_hoja(float(s))
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    else:
        s = s.replace(",", ".")
    try:
        return _normalizar_desde_hoja(float(s))
    except ValueError:
        return None


def puntaje_a_texto_celda(x: float) -> str:
    x = float(x)
    if abs(x - round(x)) < 1e-9:
        return str(int(round(x)))
    return "{:.4f}".format(x).rstrip("0").rstrip(".")


def parse_anio(s) -> Optional[int]:
    if s is None or not str(s).strip():
        return None
    texto = str(s).strip()
    if not re.fullmatch(r"\d{4}", texto):
        return None
    n = int(texto)
    if n < 1990 or n > 2100:
        return None
    return n


def parse_puntaje_formulario(s) -> Tuple[float, Optional[str]]:
    if s is None or not str(s).strip():
        return 0.0, None
    n = parse_puntaje_valor(s)
    if n is None:
        return 0.0, "Use solo números; decimales con coma o punto (ej: 87,9)."
    if n < 0 or n > 1000:
        return 0.0, "El puntaje debe estar entre 0 y 1000."
    return n, None


def contar_palabras(texto: str) -> int:
    return len(re.findall(r"\S+", str(texto or "").strip()))


def puntaje_texto_para_word(raw) -> Optional[str]:
    if raw in (None, ""):
        return None
    n = parse_puntaje_valor(raw)
    if n is None or n <= 0:
        return None
    x = float(n)
    for _ in range(10):
        if x <= 1000:
            break
        if abs(x - round(x)) >= 1e-4:
            break
        ri = int(round(x))
        if ri % 100 != 0:
            break
        x = x / 100.0
    if x <= 0 or x > 1000:
        return None
    return "{:.2f}".format(x).replace(".", ",")
