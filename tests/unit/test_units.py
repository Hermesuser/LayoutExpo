"""Pruebas unitarias para core.units."""

from decimal import Decimal

import pytest

from core.units import (
    DMM_PER_CM,
    DMM_PER_MM,
    cm_to_dmm,
    dmm_to_cm,
    dmm_to_mm,
    dmm_to_pt,
    dmm_to_px,
    format_metric,
    m_to_dmm,
    mm_to_dmm,
    px_to_dmm,
)


def test_exact_metric_conversions() -> None:
    assert mm_to_dmm(1) == DMM_PER_MM
    assert cm_to_dmm(1) == DMM_PER_CM
    assert m_to_dmm(2.5) == 25_000
    assert cm_to_dmm(Decimal("0.1")) + cm_to_dmm(Decimal("0.2")) == cm_to_dmm(Decimal("0.3"))
    assert cm_to_dmm(0.1) + cm_to_dmm(0.2) == cm_to_dmm(0.3)
    assert dmm_to_mm(155) == 15.5
    assert dmm_to_cm(15000) == 150.0


def test_pdf_points_conversion() -> None:
    # 25.4 mm == 1 inch == 72 pt exactos
    assert dmm_to_pt(mm_to_dmm(Decimal("25.4"))) == pytest.approx(72.0, abs=1e-9)


def test_px_conversions_and_validation() -> None:
    assert dmm_to_px(100, px_per_mm=2.0) == pytest.approx(20.0)
    assert px_to_dmm(20.0, px_per_mm=2.0) == 100

    with pytest.raises(ValueError):
        dmm_to_px(100, px_per_mm=0)
    with pytest.raises(ValueError):
        px_to_dmm(100, px_per_mm=-1.5)


def test_format_metric_clean_output() -> None:
    assert format_metric(15000, "cm") == "150 cm"
    assert format_metric(15250, "cm") == "152.5 cm"
    assert format_metric(15255, "cm", decimals=2) == "152.55 cm"
    assert format_metric(355, "mm") == "35.5 mm"
    assert format_metric(350, "mm") == "35 mm"
