"""Conversión exacta de unidades métricas basadas en décimas de milímetro (dmm).

Por ADR-002, el dominio almacena toda longitud física como entero `int` en décimas de
milímetro (1 mm = 10 dmm, 1 cm = 100 dmm) para eliminar errores de punto flotante.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

DMM_PER_MM = 10
DMM_PER_CM = 100
DMM_PER_M = 10_000
MM_PER_INCH = Decimal("25.4")
PT_PER_INCH = Decimal("72")

MetricUnit = Literal["mm", "cm"]


def _round_decimal_to_int(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def mm_to_dmm(mm: int | float | Decimal) -> int:
    """Convierte milímetros a décimas de milímetro con redondeo exacto."""
    return _round_decimal_to_int(Decimal(str(mm)) * DMM_PER_MM)


def cm_to_dmm(cm: int | float | Decimal) -> int:
    """Convierte centímetros a décimas de milímetro con redondeo exacto."""
    return _round_decimal_to_int(Decimal(str(cm)) * DMM_PER_CM)


def m_to_dmm(meters: int | float | Decimal) -> int:
    """Convierte metros a décimas de milímetro con redondeo exacto."""
    return _round_decimal_to_int(Decimal(str(meters)) * DMM_PER_M)


def dmm_to_mm(dmm: int) -> float:
    """Convierte décimas de milímetro a milímetros."""
    return float(Decimal(dmm) / DMM_PER_MM)


def dmm_to_cm(dmm: int) -> float:
    """Convierte décimas de milímetro a centímetros."""
    return float(Decimal(dmm) / DMM_PER_CM)


def dmm_to_pt(dmm: int) -> float:
    """Convierte décimas de milímetro a puntos tipográficos PDF (72 pt/in)."""
    mm_val = Decimal(dmm) / DMM_PER_MM
    return float((mm_val / MM_PER_INCH) * PT_PER_INCH)


def dmm_to_px(dmm: int, px_per_mm: float) -> float:
    """Convierte décimas de milímetro a píxeles según escala de lienzo."""
    if px_per_mm <= 0:
        raise ValueError("px_per_mm debe ser mayor que 0.")
    return (dmm / DMM_PER_MM) * px_per_mm


def px_to_dmm(px: float, px_per_mm: float) -> int:
    """Convierte píxeles de lienzo a décimas de milímetro."""
    if px_per_mm <= 0:
        raise ValueError("px_per_mm debe ser mayor que 0.")
    mm_val = Decimal(str(px)) / Decimal(str(px_per_mm))
    return _round_decimal_to_int(mm_val * DMM_PER_MM)


def format_metric(dmm: int, unit: MetricUnit = "cm", decimals: int | None = None) -> str:
    """Formatea una magnitud en dmm usando aritmética Decimal sin artefactos binarios."""
    if unit == "mm":
        prec = 1 if decimals is None else decimals
        val = Decimal(dmm) / DMM_PER_MM
        quant = Decimal("1") if prec == 0 else Decimal(f"1e-{prec}")
        formatted = val.quantize(quant, rounding=ROUND_HALF_UP)
        text = f"{formatted:f}".rstrip("0").rstrip(".") if decimals is None else f"{formatted:f}"
        return f"{text} mm"

    prec = 1 if decimals is None else decimals
    val = Decimal(dmm) / DMM_PER_CM
    quant = Decimal("1") if prec == 0 else Decimal(f"1e-{prec}")
    formatted = val.quantize(quant, rounding=ROUND_HALF_UP)
    text = f"{formatted:f}".rstrip("0").rstrip(".") if decimals is None else f"{formatted:f}"
    return f"{text} cm"
