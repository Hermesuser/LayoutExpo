"""Cálculo de homografía 2D (DLT 4-puntos) y segmentación de muro para proyector en sala.

Permite calibrar una salida de proyector (escala real + corrección keystone) contra 4
puntos de referencia medidos físicamente en el muro sin requerir dependencias nativas externas.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

Point2D = tuple[float, float]
HomographyMatrix = tuple[
    tuple[float, float, float],
    tuple[float, float, float],
    tuple[float, float, float],
]

_SINGULAR_EPS = 1e-10


class CalibrationError(ValueError):
    """Error geométrico cuando los 4 puntos de calibración son colineales o inválidos."""


@dataclass(frozen=True, slots=True)
class WallTileBounds:
    """Tramo horizontal activo del muro para proyectar paredes largas por secciones."""

    x_start_dmm: int
    x_end_dmm: int
    width_dmm: int


def _solve_linear_system(matrix: list[list[float]], rhs: list[float]) -> list[float]:
    """Resuelve Ax = b mediante eliminación gaussiana con pivoteo parcial."""
    n = len(rhs)
    aug = [row[:] + [rhs[idx]] for idx, row in enumerate(matrix)]

    for col in range(n):
        pivot_row = max(range(col, n), key=lambda r: abs(aug[r][col]))
        if abs(aug[pivot_row][col]) < _SINGULAR_EPS:
            raise CalibrationError(
                "Los 4 puntos de calibración son colineales o degenerados; no forman un plano."
            )
        aug[col], aug[pivot_row] = aug[pivot_row], aug[col]

        pivot_val = aug[col][col]
        for j in range(col, n + 1):
            aug[col][j] /= pivot_val

        for r in range(n):
            if r == col:
                continue
            factor = aug[r][col]
            if factor == 0.0:
                continue
            for j in range(col, n + 1):
                aug[r][j] -= factor * aug[col][j]

    return [aug[i][n] for i in range(n)]


def _validate_quad(points: Sequence[Point2D], label: str) -> None:
    if len(points) != 4:
        raise CalibrationError(f"'{label}' requiere exactamente 4 puntos.")
    for idx, (x, y) in enumerate(points):
        for other_idx in range(idx + 1, 4):
            ox, oy = points[other_idx]
            if abs(x - ox) < 1e-9 and abs(y - oy) < 1e-9:
                raise CalibrationError(f"'{label}' contiene puntos duplicados.")


def compute_homography(
    src_points: Sequence[Point2D], dst_points: Sequence[Point2D]
) -> HomographyMatrix:
    """Calcula la matriz de homografía 3x3 (h22 = 1.0) que mapea src_points -> dst_points."""
    _validate_quad(src_points, "src_points")
    _validate_quad(dst_points, "dst_points")

    a_rows: list[list[float]] = []
    b_vals: list[float] = []

    for (x, y), (u, v) in zip(src_points, dst_points, strict=True):
        a_rows.append([x, y, 1.0, 0.0, 0.0, 0.0, -u * x, -u * y])
        b_vals.append(u)
        a_rows.append([0.0, 0.0, 0.0, x, y, 1.0, -v * x, -v * y])
        b_vals.append(v)

    h = _solve_linear_system(a_rows, b_vals)
    return (
        (h[0], h[1], h[2]),
        (h[3], h[4], h[5]),
        (h[6], h[7], 1.0),
    )


def apply_homography(matrix: HomographyMatrix, x: float, y: float) -> Point2D:
    """Proyecta un punto 2D mediante la matriz de homografía 3x3."""
    w = matrix[2][0] * x + matrix[2][1] * y + matrix[2][2]
    if abs(w) < _SINGULAR_EPS:
        raise CalibrationError("El punto cae en la línea del horizonte proyectivo (w ≈ 0).")
    px = (matrix[0][0] * x + matrix[0][1] * y + matrix[0][2]) / w
    py = (matrix[1][0] * x + matrix[1][1] * y + matrix[1][2]) / w
    return (px, py)


def css_matrix3d_from_homography(matrix: HomographyMatrix) -> str:
    """Convierte una homografía 3x3 en una cadena CSS `matrix3d(...)` column-major."""
    h00, h01, h02 = matrix[0]
    h10, h11, h12 = matrix[1]
    h20, h21, h22 = matrix[2]
    values = (
        h00,
        h10,
        0.0,
        h20,
        h01,
        h11,
        0.0,
        h21,
        0.0,
        0.0,
        1.0,
        0.0,
        h02,
        h12,
        0.0,
        h22,
    )
    formatted = ", ".join(f"{val:.8f}" for val in values)
    return f"matrix3d({formatted})"


def compute_wall_tile_bounds(
    wall_width_dmm: int, viewport_x_dmm: int, viewport_width_dmm: int
) -> WallTileBounds:
    """Calcula el tramo horizontal proyectable del muro sin exceder sus límites."""
    if wall_width_dmm <= 0:
        raise ValueError("wall_width_dmm debe ser mayor que 0.")
    if viewport_x_dmm < 0 or viewport_width_dmm < 0:
        raise ValueError("Los parámetros de tramo no pueden ser negativos.")

    if viewport_width_dmm == 0:
        return WallTileBounds(x_start_dmm=0, x_end_dmm=wall_width_dmm, width_dmm=wall_width_dmm)

    clamped_start = min(viewport_x_dmm, wall_width_dmm)
    clamped_end = min(clamped_start + viewport_width_dmm, wall_width_dmm)
    if clamped_end <= clamped_start:
        raise ValueError("El tramo de proyección quedó vacío fuera del ancho del muro.")
    return WallTileBounds(
        x_start_dmm=clamped_start,
        x_end_dmm=clamped_end,
        width_dmm=clamped_end - clamped_start,
    )
