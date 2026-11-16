"""Pruebas unitarias para core.homography."""

import pytest

from core.homography import (
    CalibrationError,
    apply_homography,
    compute_homography,
    compute_wall_tile_bounds,
    css_matrix3d_from_homography,
)


def test_homography_maps_perspective_quad_accurately() -> None:
    src = [(0.0, 0.0), (1920.0, 0.0), (1920.0, 1080.0), (0.0, 1080.0)]
    # Trapecio típico de proyector inclinado hacia arriba (keystone)
    dst = [(120.0, 60.0), (1810.0, 80.0), (1900.0, 1020.0), (40.0, 1000.0)]

    h = compute_homography(src, dst)
    for (sx, sy), (dx, dy) in zip(src, dst, strict=True):
        px, py = apply_homography(h, sx, sy)
        assert px == pytest.approx(dx, abs=1e-6)
        assert py == pytest.approx(dy, abs=1e-6)

    # Centro proyectado debe caer dentro de la envolvente
    cx, cy = apply_homography(h, 960.0, 540.0)
    assert 40.0 < cx < 1900.0
    assert 60.0 < cy < 1020.0


def test_css_matrix3d_format() -> None:
    src = [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)]
    dst = [(10.0, 20.0), (210.0, 20.0), (210.0, 220.0), (10.0, 220.0)]
    h = compute_homography(src, dst)
    css = css_matrix3d_from_homography(h)
    assert css.startswith("matrix3d(")
    assert len(css[len("matrix3d(") : -1].split(",")) == 16


def test_homography_rejects_collinear_and_duplicate_points() -> None:
    src = [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)]
    collinear = [(0.0, 0.0), (50.0, 0.0), (100.0, 0.0), (150.0, 0.0)]
    with pytest.raises(CalibrationError):
        compute_homography(src, collinear)

    duplicate = [(0.0, 0.0), (0.0, 0.0), (100.0, 100.0), (0.0, 100.0)]
    with pytest.raises(CalibrationError):
        compute_homography(src, duplicate)


def test_compute_wall_tile_bounds() -> None:
    full = compute_wall_tile_bounds(60_000, viewport_x_dmm=0, viewport_width_dmm=0)
    assert (full.x_start_dmm, full.x_end_dmm, full.width_dmm) == (0, 60_000, 60_000)

    partial = compute_wall_tile_bounds(60_000, viewport_x_dmm=45_000, viewport_width_dmm=25_000)
    assert (partial.x_start_dmm, partial.x_end_dmm, partial.width_dmm) == (45_000, 60_000, 15_000)

    with pytest.raises(ValueError):
        compute_wall_tile_bounds(60_000, viewport_x_dmm=60_000, viewport_width_dmm=10_000)
