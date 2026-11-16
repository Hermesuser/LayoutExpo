"""Motor geométrico de precisión en décimas de milímetro (dmm) para montaje en muro.

Sistema de coordenadas (ADR-002):
- Origen (0, 0) en la esquina inferior izquierda del muro.
- +X hacia la derecha; +Y hacia arriba (altura desde el suelo).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from core.project import Artwork, HangingType, Placement, Wall
from core.units import cm_to_dmm

AlignMode = Literal["top", "bottom", "center_y", "left", "right", "center_x", "eye_level"]
IssueSeverity = Literal["error", "warning"]


@dataclass(frozen=True, slots=True)
class RectDmm:
    """Rectángulo físico en dmm con origen inferior-izquierdo."""

    x: int
    y: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def top(self) -> int:
        return self.y + self.height

    @property
    def center_x(self) -> int:
        return self.x + self.width // 2

    @property
    def center_y(self) -> int:
        return self.y + self.height // 2

    def intersects(self, other: RectDmm) -> bool:
        """Retorna True si los interiores de ambos rectángulos se superponen."""
        return (
            self.x < other.right
            and self.right > other.x
            and self.y < other.top
            and self.top > other.y
        )


@dataclass(frozen=True, slots=True)
class AnchorPoint:
    """Punto exacto de perforación/clavo sobre el muro para asistir el montaje."""

    placement_id: str
    artwork_id: str
    label: str
    x_dmm: int
    y_dmm: int
    distance_from_top_edge_dmm: int


@dataclass(frozen=True, slots=True)
class LayoutIssue:
    """Problema de validez física detectado en un muro."""

    code: str
    severity: IssueSeverity
    message: str
    placement_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SnapGuide:
    """Línea guía sugerida durante un ajuste/snap."""

    axis: Literal["x", "y"]
    coord_dmm: int
    kind: str


@dataclass(frozen=True, slots=True)
class SnapResult:
    """Resultado de aplicar imán inteligente a un desplazamiento propuesto."""

    x_dmm: int
    y_dmm: int
    guides: tuple[SnapGuide, ...]


@dataclass(frozen=True, slots=True)
class PlacementDimensions:
    """Cotas físicas de una obra colocada respecto al muro y sus anclajes."""

    placement_id: str
    artwork_id: str
    title: str
    outer_rect: RectDmm
    image_rect: RectDmm
    distance_from_floor_dmm: int
    distance_from_left_wall_dmm: int
    distance_from_right_wall_dmm: int
    distance_from_ceiling_dmm: int
    center_height_dmm: int
    anchors: tuple[AnchorPoint, ...]


@dataclass(frozen=True, slots=True)
class HorizontalGap:
    """Separación libre horizontal entre dos obras consecutivas de izquierda a derecha."""

    left_placement_id: str
    right_placement_id: str
    gap_dmm: int


@dataclass(frozen=True, slots=True)
class WallDimensionReport:
    """Reporte completo de cotas de un muro para PDF técnico y lectores de pantalla."""

    wall_id: str
    wall_name: str
    wall_width_dmm: int
    wall_height_dmm: int
    eye_level_dmm: int
    items: tuple[PlacementDimensions, ...]
    horizontal_gaps: tuple[HorizontalGap, ...]
    issues: tuple[LayoutIssue, ...]


def _resolve_artwork(artwork_id: str, artworks_by_id: dict[str, Artwork]) -> Artwork:
    artwork = artworks_by_id.get(artwork_id)
    if artwork is None:
        raise KeyError(f"Obra '{artwork_id}' no encontrada en el catálogo del proyecto.")
    return artwork


def placement_outer_rect(placement: Placement, artwork: Artwork) -> RectDmm:
    """Retorna el rectángulo exterior físico (incluyendo marco y passepartout)."""
    w, h = artwork.outer_size_dmm()
    return RectDmm(x=placement.x_dmm, y=placement.y_dmm, width=w, height=h)


def placement_image_rect(placement: Placement, artwork: Artwork) -> RectDmm:
    """Retorna el rectángulo físico de la fotografía visible dentro del marco."""
    dx, dy = artwork.image_origin_offset_dmm()
    return RectDmm(
        x=placement.x_dmm + dx,
        y=placement.y_dmm + dy,
        width=artwork.image_width_dmm,
        height=artwork.image_height_dmm,
    )


def compute_anchor_points(placement: Placement, artwork: Artwork) -> list[AnchorPoint]:
    """Calcula coordenadas exactas (dmm) de los puntos de anclaje/clavos en el muro."""
    outer = placement_outer_rect(placement, artwork)
    hw = artwork.hardware
    drop = hw.offset_from_top_dmm + hw.wire_drop_dmm
    # Evitar anclajes por debajo del borde inferior en piezas extremadamente pequeñas
    drop = min(drop, outer.height)
    y_anchor = outer.top - drop

    if hw.hanging_type == HangingType.SINGLE_CENTER:
        return [
            AnchorPoint(
                placement_id=placement.id,
                artwork_id=artwork.id,
                label="Anclaje central",
                x_dmm=outer.center_x,
                y_dmm=y_anchor,
                distance_from_top_edge_dmm=drop,
            )
        ]

    # Dos puntos simétricos respetando margen lateral; si la pieza es estrecha, colapsa al centro
    inset = min(hw.lateral_inset_dmm, outer.width // 2)
    x_left = outer.x + inset
    x_right = outer.right - inset
    if x_left >= x_right:
        return [
            AnchorPoint(
                placement_id=placement.id,
                artwork_id=artwork.id,
                label="Anclaje central",
                x_dmm=outer.center_x,
                y_dmm=y_anchor,
                distance_from_top_edge_dmm=drop,
            )
        ]

    return [
        AnchorPoint(
            placement_id=placement.id,
            artwork_id=artwork.id,
            label="Anclaje izquierdo",
            x_dmm=x_left,
            y_dmm=y_anchor,
            distance_from_top_edge_dmm=drop,
        ),
        AnchorPoint(
            placement_id=placement.id,
            artwork_id=artwork.id,
            label="Anclaje derecho",
            x_dmm=x_right,
            y_dmm=y_anchor,
            distance_from_top_edge_dmm=drop,
        ),
    ]


def validate_wall_bounds(wall: Wall, artworks_by_id: dict[str, Artwork]) -> list[LayoutIssue]:
    """Detecta obras fuera de muro, invasión de zócalo y solapamientos entre obras."""
    issues: list[LayoutIssue] = []
    rects: list[tuple[Placement, RectDmm]] = []

    for pl in wall.placements:
        art = _resolve_artwork(pl.artwork_id, artworks_by_id)
        rect = placement_outer_rect(pl, art)
        rects.append((pl, rect))

        if rect.x < 0 or rect.right > wall.width_dmm or rect.top > wall.height_dmm or rect.y < 0:
            issues.append(
                LayoutIssue(
                    code="OUT_OF_WALL_BOUNDS",
                    severity="error",
                    message=f"La obra '{art.title}' excede los límites físicos del muro.",
                    placement_ids=(pl.id,),
                )
            )
        elif wall.baseboard_height_dmm > 0 and rect.y < wall.baseboard_height_dmm:
            issues.append(
                LayoutIssue(
                    code="OVERLAPS_BASEBOARD",
                    severity="warning",
                    message=f"La obra '{art.title}' invade la zona del zócalo/guardapolvo.",
                    placement_ids=(pl.id,),
                )
            )

    for i in range(len(rects)):
        pl_a, rect_a = rects[i]
        for j in range(i + 1, len(rects)):
            pl_b, rect_b = rects[j]
            if rect_a.intersects(rect_b):
                issues.append(
                    LayoutIssue(
                        code="ARTWORK_OVERLAP",
                        severity="error",
                        message="Dos obras se superponen físicamente en el muro.",
                        placement_ids=(pl_a.id, pl_b.id),
                    )
                )
    return issues


def snap_placement(
    target_x_dmm: int,
    target_y_dmm: int,
    moving_artwork: Artwork,
    wall: Wall,
    artworks_by_id: dict[str, Artwork],
    *,
    moving_placement_id: str | None = None,
    tolerance_dmm: int | None = None,
) -> SnapResult:
    """Ajusta una posición propuesta al eje visual y bordes/centros vecinos dentro de tolerancia."""
    tol = cm_to_dmm(2) if tolerance_dmm is None else tolerance_dmm
    if tol < 0:
        raise ValueError("tolerance_dmm no puede ser negativo.")

    width, height = moving_artwork.outer_size_dmm()

    # Candidatos en Y: (valor_y_resultante, coordenada_linea_guia, tipo)
    y_candidates: list[tuple[int, int, str]] = [
        (wall.eye_level_dmm - height // 2, wall.eye_level_dmm, "eye_level_center"),
    ]
    x_candidates: list[tuple[int, int, str]] = [
        (wall.width_dmm // 2 - width // 2, wall.width_dmm // 2, "wall_center_x"),
    ]

    for other in wall.placements:
        if other.id == moving_placement_id:
            continue
        other_rect = placement_outer_rect(other, _resolve_artwork(other.artwork_id, artworks_by_id))
        y_candidates.extend(
            [
                (other_rect.y, other_rect.y, "align_bottom"),
                (other_rect.top - height, other_rect.top, "align_top"),
                (other_rect.center_y - height // 2, other_rect.center_y, "align_center_y"),
            ]
        )
        x_candidates.extend(
            [
                (other_rect.x, other_rect.x, "align_left"),
                (other_rect.right - width, other_rect.right, "align_right"),
                (other_rect.center_x - width // 2, other_rect.center_x, "align_center_x"),
            ]
        )

    best_x = target_x_dmm
    best_x_guide: SnapGuide | None = None
    min_dx = tol + 1
    for cand_x, line_x, kind in x_candidates:
        dist = abs(target_x_dmm - cand_x)
        if dist < min_dx:
            min_dx = dist
            best_x = cand_x
            best_x_guide = SnapGuide(axis="x", coord_dmm=line_x, kind=kind)

    best_y = target_y_dmm
    best_y_guide: SnapGuide | None = None
    min_dy = tol + 1
    for cand_y, line_y, kind in y_candidates:
        dist = abs(target_y_dmm - cand_y)
        if dist < min_dy:
            min_dy = dist
            best_y = cand_y
            best_y_guide = SnapGuide(axis="y", coord_dmm=line_y, kind=kind)

    guides: list[SnapGuide] = []
    if best_x_guide is not None:
        guides.append(best_x_guide)
    if best_y_guide is not None:
        guides.append(best_y_guide)
    return SnapResult(x_dmm=best_x, y_dmm=best_y, guides=tuple(guides))


def align_placements(
    placements: list[Placement],
    artworks_by_id: dict[str, Artwork],
    mode: AlignMode,
    *,
    eye_level_dmm: int | None = None,
) -> dict[str, tuple[int, int]]:
    """Calcula nuevas coordenadas (x_dmm, y_dmm) para alinear un conjunto de obras."""
    if not placements:
        return {}

    rects = [
        (pl, placement_outer_rect(pl, _resolve_artwork(pl.artwork_id, artworks_by_id)))
        for pl in placements
    ]
    unlocked = [(pl, r) for pl, r in rects if not pl.locked]
    if not unlocked:
        return {pl.id: (pl.x_dmm, pl.y_dmm) for pl, _ in rects}

    if mode == "eye_level":
        if eye_level_dmm is None:
            raise ValueError("eye_level_dmm es obligatorio cuando mode == 'eye_level'.")
        return {
            pl.id: (
                (pl.x_dmm, pl.y_dmm) if pl.locked else (pl.x_dmm, eye_level_dmm - rect.height // 2)
            )
            for pl, rect in rects
        }

    # Referencia calculada sobre toda la selección
    min_x = min(r.x for _, r in rects)
    max_right = max(r.right for _, r in rects)
    min_y = min(r.y for _, r in rects)
    max_top = max(r.top for _, r in rects)
    avg_cx = round(sum(r.center_x for _, r in rects) / len(rects))
    avg_cy = round(sum(r.center_y for _, r in rects) / len(rects))

    result: dict[str, tuple[int, int]] = {}
    for pl, r in rects:
        if pl.locked:
            result[pl.id] = (pl.x_dmm, pl.y_dmm)
            continue
        if mode == "top":
            result[pl.id] = (pl.x_dmm, max_top - r.height)
        elif mode == "bottom":
            result[pl.id] = (pl.x_dmm, min_y)
        elif mode == "center_y":
            result[pl.id] = (pl.x_dmm, avg_cy - r.height // 2)
        elif mode == "left":
            result[pl.id] = (min_x, pl.y_dmm)
        elif mode == "right":
            result[pl.id] = (max_right - r.width, pl.y_dmm)
        elif mode == "center_x":
            result[pl.id] = (avg_cx - r.width // 2, pl.y_dmm)
    return result


def distribute_horizontally(
    placements: list[Placement],
    artworks_by_id: dict[str, Artwork],
    *,
    gap_dmm: int | None = None,
) -> dict[str, tuple[int, int]]:
    """Distribuye obras horizontalmente con separación fija o equidistante entre extremos."""
    if len(placements) <= 1:
        return {pl.id: (pl.x_dmm, pl.y_dmm) for pl in placements}
    if gap_dmm is not None and gap_dmm < 0:
        raise ValueError("gap_dmm no puede ser negativo.")

    ordered = sorted(
        (
            (pl, placement_outer_rect(pl, _resolve_artwork(pl.artwork_id, artworks_by_id)))
            for pl in placements
        ),
        key=lambda item: (item[1].x, item[1].y),
    )

    if gap_dmm is not None:
        cursor_x = ordered[0][1].x
        out: dict[str, tuple[int, int]] = {}
        for pl, rect in ordered:
            out[pl.id] = (cursor_x, pl.y_dmm)
            cursor_x += rect.width + gap_dmm
        return out

    # Distribución equidistante conservando borde izquierdo de la primera y derecho de la última
    if len(ordered) == 2:
        return {pl.id: (pl.x_dmm, pl.y_dmm) for pl, _ in ordered}

    span_left = ordered[0][1].x
    span_right = ordered[-1][1].right
    total_widths = sum(rect.width for _, rect in ordered)
    available_space = span_right - span_left - total_widths
    gaps_count = len(ordered) - 1
    base_gap, remainder = divmod(available_space, gaps_count)

    out = {}
    cursor_x = span_left
    for idx, (pl, rect) in enumerate(ordered):
        if idx == len(ordered) - 1:
            out[pl.id] = (span_right - rect.width, pl.y_dmm)
        else:
            out[pl.id] = (cursor_x, pl.y_dmm)
            extra = 1 if idx < remainder else 0
            cursor_x += rect.width + base_gap + extra
    return out


def wall_dimension_report(wall: Wall, artworks_by_id: dict[str, Artwork]) -> WallDimensionReport:
    """Genera el reporte dimensional completo del muro para planos PDF y accesibilidad."""
    items_with_rects: list[tuple[PlacementDimensions, RectDmm]] = []
    for pl in sorted(wall.placements, key=lambda p: (p.x_dmm, p.y_dmm)):
        art = _resolve_artwork(pl.artwork_id, artworks_by_id)
        outer = placement_outer_rect(pl, art)
        inner = placement_image_rect(pl, art)
        anchors = tuple(compute_anchor_points(pl, art))
        dim = PlacementDimensions(
            placement_id=pl.id,
            artwork_id=art.id,
            title=art.title,
            outer_rect=outer,
            image_rect=inner,
            distance_from_floor_dmm=outer.y,
            distance_from_left_wall_dmm=outer.x,
            distance_from_right_wall_dmm=wall.width_dmm - outer.right,
            distance_from_ceiling_dmm=wall.height_dmm - outer.top,
            center_height_dmm=outer.center_y,
            anchors=anchors,
        )
        items_with_rects.append((dim, outer))

    gaps: list[HorizontalGap] = []
    for idx in range(len(items_with_rects) - 1):
        left_dim, left_rect = items_with_rects[idx]
        right_dim, right_rect = items_with_rects[idx + 1]
        gaps.append(
            HorizontalGap(
                left_placement_id=left_dim.placement_id,
                right_placement_id=right_dim.placement_id,
                gap_dmm=right_rect.x - left_rect.right,
            )
        )

    issues = tuple(validate_wall_bounds(wall, artworks_by_id))
    return WallDimensionReport(
        wall_id=wall.id,
        wall_name=wall.name,
        wall_width_dmm=wall.width_dmm,
        wall_height_dmm=wall.height_dmm,
        eye_level_dmm=wall.eye_level_dmm,
        items=tuple(dim for dim, _ in items_with_rects),
        horizontal_gaps=tuple(gaps),
        issues=issues,
    )
