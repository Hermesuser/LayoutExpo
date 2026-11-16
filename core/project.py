"""Modelo de datos del proyecto `.layoutexpo` y persistencia atómica."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import cast

from core.units import cm_to_dmm

SCHEMA_VERSION = 1


class ProjectValidationError(ValueError):
    """Error de validación estructural o dimensional en un proyecto .layoutexpo."""


class MountingType(StrEnum):
    """Modalidades físicas de montaje de obra soportadas."""

    FRAMED = "framed"
    DIRECT = "direct"
    CANVAS = "canvas"
    POLYPTYCH_PART = "polyptych_part"


class HangingType(StrEnum):
    """Sistema físico de fijación al muro."""

    SINGLE_CENTER = "single_center"
    DUAL_POINTS = "dual_points"


class WallNarrativeRole(StrEnum):
    """Rol narrativo del muro dentro del arco curatorial de la exposición."""

    STANDARD = "standard"
    INITIAL = "initial"
    DEVELOPMENT = "development"
    CLIMAX = "climax"
    EPILOGUE = "epilogue"


def _ensure_non_negative(value: int, field_name: str) -> None:
    if value < 0:
        raise ProjectValidationError(f"{field_name} no puede ser negativo (recibido {value}).")


def _ensure_positive(value: int, field_name: str) -> None:
    if value <= 0:
        raise ProjectValidationError(f"{field_name} debe ser mayor que 0 (recibido {value}).")


@dataclass(frozen=True, slots=True)
class FrameSpec:
    """Dimensiones físicas del marco exterior en décimas de milímetro (dmm)."""

    top_dmm: int = 0
    bottom_dmm: int = 0
    left_dmm: int = 0
    right_dmm: int = 0
    depth_dmm: int = 200  # 2 cm por defecto
    color_hex: str = "#1C1C1E"

    def __post_init__(self) -> None:
        for attr in ("top_dmm", "bottom_dmm", "left_dmm", "right_dmm", "depth_dmm"):
            _ensure_non_negative(getattr(self, attr), f"FrameSpec.{attr}")

    @classmethod
    def uniform(cls, width_dmm: int, depth_dmm: int = 200, color_hex: str = "#1C1C1E") -> FrameSpec:
        """Crea un marco simétrico de ancho uniforme en los cuatro lados."""
        return cls(
            top_dmm=width_dmm,
            bottom_dmm=width_dmm,
            left_dmm=width_dmm,
            right_dmm=width_dmm,
            depth_dmm=depth_dmm,
            color_hex=color_hex,
        )


@dataclass(frozen=True, slots=True)
class PassepartoutSpec:
    """Márgenes interiores (marialuisa / passepartout) en dmm."""

    top_dmm: int = 0
    bottom_dmm: int = 0
    left_dmm: int = 0
    right_dmm: int = 0
    color_hex: str = "#F7F6F2"

    def __post_init__(self) -> None:
        for attr in ("top_dmm", "bottom_dmm", "left_dmm", "right_dmm"):
            _ensure_non_negative(getattr(self, attr), f"PassepartoutSpec.{attr}")

    @classmethod
    def uniform(cls, margin_dmm: int, color_hex: str = "#F7F6F2") -> PassepartoutSpec:
        """Crea un passepartout simétrico."""
        return cls(
            top_dmm=margin_dmm,
            bottom_dmm=margin_dmm,
            left_dmm=margin_dmm,
            right_dmm=margin_dmm,
            color_hex=color_hex,
        )


@dataclass(frozen=True, slots=True)
class HangingHardware:
    """Configuración física de los puntos de anclaje al muro en dmm."""

    hanging_type: HangingType = HangingType.SINGLE_CENTER
    offset_from_top_dmm: int = 300  # 3 cm desde borde superior del marco/obra
    wire_drop_dmm: int = 0  # Caída adicional de alambre bajo tensión
    lateral_inset_dmm: int = 500  # 5 cm desde borde izq/der si hanging_type == DUAL_POINTS

    def __post_init__(self) -> None:
        _ensure_non_negative(self.offset_from_top_dmm, "HangingHardware.offset_from_top_dmm")
        _ensure_non_negative(self.wire_drop_dmm, "HangingHardware.wire_drop_dmm")
        _ensure_non_negative(self.lateral_inset_dmm, "HangingHardware.lateral_inset_dmm")


@dataclass(slots=True)
class Artwork:
    """Obra fotográfica del catálogo (referencia no destructiva + medidas físicas)."""

    id: str
    title: str
    image_width_dmm: int
    image_height_dmm: int
    author: str = ""
    year: str = ""
    medium: str = ""
    source_path: str = ""
    sha256: str = ""
    mounting_type: MountingType = MountingType.FRAMED
    frame: FrameSpec = field(default_factory=FrameSpec)
    passepartout: PassepartoutSpec = field(default_factory=PassepartoutSpec)
    hardware: HangingHardware = field(default_factory=HangingHardware)
    is_anchor: bool = False

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ProjectValidationError("Artwork.id no puede estar vacío.")
        if not self.title.strip():
            raise ProjectValidationError("Artwork.title no puede estar vacío.")
        _ensure_positive(self.image_width_dmm, "Artwork.image_width_dmm")
        _ensure_positive(self.image_height_dmm, "Artwork.image_height_dmm")

    def outer_size_dmm(self) -> tuple[int, int]:
        """Retorna (ancho_exterior, alto_exterior) en dmm incluyendo marco y passepartout."""
        if self.mounting_type in (MountingType.DIRECT, MountingType.CANVAS):
            return (self.image_width_dmm, self.image_height_dmm)
        width = (
            self.image_width_dmm
            + self.passepartout.left_dmm
            + self.passepartout.right_dmm
            + self.frame.left_dmm
            + self.frame.right_dmm
        )
        height = (
            self.image_height_dmm
            + self.passepartout.top_dmm
            + self.passepartout.bottom_dmm
            + self.frame.top_dmm
            + self.frame.bottom_dmm
        )
        return (width, height)

    def image_origin_offset_dmm(self) -> tuple[int, int]:
        """Desplazamiento (dx, dy) de la imagen respecto a la esquina inferior-izq exterior."""
        if self.mounting_type in (MountingType.DIRECT, MountingType.CANVAS):
            return (0, 0)
        return (
            self.frame.left_dmm + self.passepartout.left_dmm,
            self.frame.bottom_dmm + self.passepartout.bottom_dmm,
        )


@dataclass(slots=True)
class Placement:
    """Instancia de una obra posicionada sobre un muro específico (origen inferior-izquierdo)."""

    id: str
    artwork_id: str
    x_dmm: int
    y_dmm: int
    group_id: str | None = None
    z_order: int = 0
    locked: bool = False

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ProjectValidationError("Placement.id no puede estar vacío.")
        if not self.artwork_id.strip():
            raise ProjectValidationError("Placement.artwork_id no puede estar vacío.")


@dataclass(slots=True)
class ProjectorCalibration:
    """Calibración de homografía 4-puntos y tramo visible para proyección en sala."""

    # Puntos en muro (dmm): esquina sup-izq, sup-der, inf-der, inf-izq del rectángulo patrón
    wall_points_dmm: tuple[tuple[int, int], tuple[int, int], tuple[int, int], tuple[int, int]] = (
        (0, 20000),
        (20000, 20000),
        (20000, 10000),
        (0, 10000),
    )
    # Puntos normalizados en pantalla del proyector (0..1, origen superior-izquierdo)
    projector_points_norm: tuple[
        tuple[float, float], tuple[float, float], tuple[float, float], tuple[float, float]
    ] = (
        (0.1, 0.1),
        (0.9, 0.1),
        (0.9, 0.9),
        (0.1, 0.9),
    )
    viewport_x_dmm: int = 0
    viewport_width_dmm: int = 0  # 0 => muro completo
    guide_color: str = "cyan"
    stroke_width_px: int = 2
    show_ghost_image: bool = False
    ghost_opacity: float = 0.25
    show_calibration_grid: bool = False

    def __post_init__(self) -> None:
        _ensure_non_negative(self.viewport_x_dmm, "ProjectorCalibration.viewport_x_dmm")
        _ensure_non_negative(self.viewport_width_dmm, "ProjectorCalibration.viewport_width_dmm")
        _ensure_positive(self.stroke_width_px, "ProjectorCalibration.stroke_width_px")
        if not 0.0 <= self.ghost_opacity <= 1.0:
            raise ProjectValidationError("ProjectorCalibration.ghost_opacity debe estar en [0, 1].")


VALID_WALL_TEXTURES = frozenset({"none", "plaster", "concrete", "brick", "wood"})
VALID_WALL_IMAGE_FITS = frozenset({"cover", "contain", "tile"})


@dataclass(slots=True)
class Wall:
    """Muro físico de la exposición (sistema de coordenadas con origen inferior-izquierdo)."""

    id: str
    name: str
    width_dmm: int
    height_dmm: int
    baseboard_height_dmm: int = 0
    eye_level_dmm: int = field(default_factory=lambda: cm_to_dmm(150))
    wall_color_hex: str = "#F4F3EF"
    wall_texture_preset: str = "none"
    wall_image_path: str = ""
    wall_image_sha256: str = ""
    wall_image_fit: str = "cover"
    wall_image_opacity: float = 1.0
    narrative_role: WallNarrativeRole = WallNarrativeRole.STANDARD
    placements: list[Placement] = field(default_factory=list)
    calibration: ProjectorCalibration = field(default_factory=ProjectorCalibration)

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ProjectValidationError("Wall.id no puede estar vacío.")
        if not self.name.strip():
            raise ProjectValidationError("Wall.name no puede estar vacío.")
        if self.wall_texture_preset not in VALID_WALL_TEXTURES:
            raise ProjectValidationError(f"Textura de muro inválida: '{self.wall_texture_preset}'.")
        if self.wall_image_fit not in VALID_WALL_IMAGE_FITS:
            raise ProjectValidationError(
                f"Ajuste de imagen de muro inválido: '{self.wall_image_fit}'."
            )
        if not 0.0 <= self.wall_image_opacity <= 1.0:
            raise ProjectValidationError("Wall.wall_image_opacity debe estar en [0, 1].")
        _ensure_positive(self.width_dmm, "Wall.width_dmm")
        _ensure_positive(self.height_dmm, "Wall.height_dmm")
        _ensure_non_negative(self.baseboard_height_dmm, "Wall.baseboard_height_dmm")
        if self.baseboard_height_dmm >= self.height_dmm:
            raise ProjectValidationError("El zócalo no puede ser mayor o igual a la altura.")
        _ensure_non_negative(self.eye_level_dmm, "Wall.eye_level_dmm")


@dataclass(slots=True)
class ExhibitionProject:
    """Raíz serializable de un proyecto `.layoutexpo`."""

    title: str
    curator: str = ""
    venue: str = ""
    default_eye_level_dmm: int = field(default_factory=lambda: cm_to_dmm(150))
    schema_version: int = SCHEMA_VERSION
    artworks: list[Artwork] = field(default_factory=list)
    walls: list[Wall] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ProjectValidationError("ExhibitionProject.title no puede estar vacío.")
        if self.schema_version != SCHEMA_VERSION:
            raise ProjectValidationError(
                f"Versión de esquema no soportada: {self.schema_version} "
                f"(esperada {SCHEMA_VERSION})."
            )
        _ensure_non_negative(self.default_eye_level_dmm, "ExhibitionProject.default_eye_level_dmm")
        artwork_ids = [a.id for a in self.artworks]
        if len(artwork_ids) != len(set(artwork_ids)):
            raise ProjectValidationError("Existen IDs de obra duplicados en el proyecto.")
        wall_ids = [w.id for w in self.walls]
        if len(wall_ids) != len(set(wall_ids)):
            raise ProjectValidationError("Existen IDs de muro duplicados en el proyecto.")

    def artworks_by_id(self) -> dict[str, Artwork]:
        """Devuelve un índice por id de obra para consultas O(1)."""
        return {art.id: art for art in self.artworks}


# ---------------------------------------------------------------------------
# Serialización y parsing estricto
# ---------------------------------------------------------------------------


def _req_map(obj: object, ctx: str) -> Mapping[str, object]:
    if not isinstance(obj, Mapping):
        raise ProjectValidationError(f"Se esperaba un objeto en '{ctx}'.")
    return cast(Mapping[str, object], obj)


def _req_list(obj: object, ctx: str) -> list[object]:
    if not isinstance(obj, list):
        raise ProjectValidationError(f"Se esperaba una lista en '{ctx}'.")
    return obj


def _req_str(data: Mapping[str, object], key: str, ctx: str, default: str | None = None) -> str:
    val = data.get(key, default)
    if not isinstance(val, str):
        raise ProjectValidationError(f"Se esperaba texto en '{ctx}.{key}'.")
    return val


def _req_int(data: Mapping[str, object], key: str, ctx: str, default: int | None = None) -> int:
    val = data.get(key, default)
    if isinstance(val, bool) or not isinstance(val, int):
        raise ProjectValidationError(f"Se esperaba entero en '{ctx}.{key}'.")
    return val


def _req_float(
    data: Mapping[str, object], key: str, ctx: str, default: float | None = None
) -> float:
    val = data.get(key, default)
    if isinstance(val, bool) or not isinstance(val, int | float):
        raise ProjectValidationError(f"Se esperaba número en '{ctx}.{key}'.")
    return float(val)


def _req_bool(data: Mapping[str, object], key: str, ctx: str, default: bool = False) -> bool:
    val = data.get(key, default)
    if not isinstance(val, bool):
        raise ProjectValidationError(f"Se esperaba booleano en '{ctx}.{key}'.")
    return val


def _parse_point_quad_int(
    raw: object, ctx: str
) -> tuple[tuple[int, int], tuple[int, int], tuple[int, int], tuple[int, int]]:
    items = _req_list(raw, ctx)
    if len(items) != 4:
        raise ProjectValidationError(f"'{ctx}' debe contener exactamente 4 puntos.")
    points: list[tuple[int, int]] = []
    for idx, item in enumerate(items):
        pair = _req_list(item, f"{ctx}[{idx}]")
        if len(pair) != 2 or any(isinstance(v, bool) or not isinstance(v, int) for v in pair):
            raise ProjectValidationError(f"'{ctx}[{idx}]' debe ser [int, int].")
        points.append((cast(int, pair[0]), cast(int, pair[1])))
    return (points[0], points[1], points[2], points[3])


def _parse_point_quad_float(
    raw: object, ctx: str
) -> tuple[tuple[float, float], tuple[float, float], tuple[float, float], tuple[float, float]]:
    items = _req_list(raw, ctx)
    if len(items) != 4:
        raise ProjectValidationError(f"'{ctx}' debe contener exactamente 4 puntos.")
    points: list[tuple[float, float]] = []
    for idx, item in enumerate(items):
        pair = _req_list(item, f"{ctx}[{idx}]")
        if len(pair) != 2 or any(
            isinstance(v, bool) or not isinstance(v, int | float) for v in pair
        ):
            raise ProjectValidationError(f"'{ctx}[{idx}]' debe ser [float, float].")
        points.append((float(cast(float, pair[0])), float(cast(float, pair[1]))))
    return (points[0], points[1], points[2], points[3])


def project_to_dict(project: ExhibitionProject) -> dict[str, object]:
    """Serializa el proyecto a un diccionario JSON-safe."""
    return {
        "schema_version": project.schema_version,
        "title": project.title,
        "curator": project.curator,
        "venue": project.venue,
        "default_eye_level_dmm": project.default_eye_level_dmm,
        "artworks": [
            {
                "id": art.id,
                "title": art.title,
                "author": art.author,
                "year": art.year,
                "medium": art.medium,
                "source_path": art.source_path,
                "sha256": art.sha256,
                "image_width_dmm": art.image_width_dmm,
                "image_height_dmm": art.image_height_dmm,
                "mounting_type": art.mounting_type.value,
                "is_anchor": art.is_anchor,
                "frame": {
                    "top_dmm": art.frame.top_dmm,
                    "bottom_dmm": art.frame.bottom_dmm,
                    "left_dmm": art.frame.left_dmm,
                    "right_dmm": art.frame.right_dmm,
                    "depth_dmm": art.frame.depth_dmm,
                    "color_hex": art.frame.color_hex,
                },
                "passepartout": {
                    "top_dmm": art.passepartout.top_dmm,
                    "bottom_dmm": art.passepartout.bottom_dmm,
                    "left_dmm": art.passepartout.left_dmm,
                    "right_dmm": art.passepartout.right_dmm,
                    "color_hex": art.passepartout.color_hex,
                },
                "hardware": {
                    "hanging_type": art.hardware.hanging_type.value,
                    "offset_from_top_dmm": art.hardware.offset_from_top_dmm,
                    "wire_drop_dmm": art.hardware.wire_drop_dmm,
                    "lateral_inset_dmm": art.hardware.lateral_inset_dmm,
                },
            }
            for art in project.artworks
        ],
        "walls": [
            {
                "id": wall.id,
                "name": wall.name,
                "width_dmm": wall.width_dmm,
                "height_dmm": wall.height_dmm,
                "baseboard_height_dmm": wall.baseboard_height_dmm,
                "eye_level_dmm": wall.eye_level_dmm,
                "wall_color_hex": wall.wall_color_hex,
                "wall_texture_preset": wall.wall_texture_preset,
                "wall_image_path": wall.wall_image_path,
                "wall_image_sha256": wall.wall_image_sha256,
                "wall_image_fit": wall.wall_image_fit,
                "wall_image_opacity": wall.wall_image_opacity,
                "narrative_role": wall.narrative_role.value,
                "calibration": {
                    "wall_points_dmm": [list(pt) for pt in wall.calibration.wall_points_dmm],
                    "projector_points_norm": [
                        list(pt) for pt in wall.calibration.projector_points_norm
                    ],
                    "viewport_x_dmm": wall.calibration.viewport_x_dmm,
                    "viewport_width_dmm": wall.calibration.viewport_width_dmm,
                    "guide_color": wall.calibration.guide_color,
                    "stroke_width_px": wall.calibration.stroke_width_px,
                    "show_ghost_image": wall.calibration.show_ghost_image,
                    "ghost_opacity": wall.calibration.ghost_opacity,
                    "show_calibration_grid": wall.calibration.show_calibration_grid,
                },
                "placements": [
                    {
                        "id": pl.id,
                        "artwork_id": pl.artwork_id,
                        "x_dmm": pl.x_dmm,
                        "y_dmm": pl.y_dmm,
                        "group_id": pl.group_id,
                        "z_order": pl.z_order,
                        "locked": pl.locked,
                    }
                    for pl in wall.placements
                ],
            }
            for wall in project.walls
        ],
    }


def _parse_artwork(raw: object, idx: int) -> Artwork:
    ctx = f"artworks[{idx}]"
    d = _req_map(raw, ctx)
    frame_map = _req_map(d.get("frame", {}), f"{ctx}.frame")
    pp_map = _req_map(d.get("passepartout", {}), f"{ctx}.passepartout")
    hw_map = _req_map(d.get("hardware", {}), f"{ctx}.hardware")

    try:
        mounting = MountingType(_req_str(d, "mounting_type", ctx, MountingType.FRAMED.value))
        hanging = HangingType(_req_str(hw_map, "hanging_type", f"{ctx}.hardware", "single_center"))
    except ValueError as exc:
        raise ProjectValidationError(f"Tipo de montaje/anclaje inválido en {ctx}: {exc}") from exc

    return Artwork(
        id=_req_str(d, "id", ctx),
        title=_req_str(d, "title", ctx),
        author=_req_str(d, "author", ctx, ""),
        year=_req_str(d, "year", ctx, ""),
        medium=_req_str(d, "medium", ctx, ""),
        source_path=_req_str(d, "source_path", ctx, ""),
        sha256=_req_str(d, "sha256", ctx, ""),
        image_width_dmm=_req_int(d, "image_width_dmm", ctx),
        image_height_dmm=_req_int(d, "image_height_dmm", ctx),
        mounting_type=mounting,
        is_anchor=_req_bool(d, "is_anchor", ctx, False),
        frame=FrameSpec(
            top_dmm=_req_int(frame_map, "top_dmm", f"{ctx}.frame", 0),
            bottom_dmm=_req_int(frame_map, "bottom_dmm", f"{ctx}.frame", 0),
            left_dmm=_req_int(frame_map, "left_dmm", f"{ctx}.frame", 0),
            right_dmm=_req_int(frame_map, "right_dmm", f"{ctx}.frame", 0),
            depth_dmm=_req_int(frame_map, "depth_dmm", f"{ctx}.frame", 200),
            color_hex=_req_str(frame_map, "color_hex", f"{ctx}.frame", "#1C1C1E"),
        ),
        passepartout=PassepartoutSpec(
            top_dmm=_req_int(pp_map, "top_dmm", f"{ctx}.passepartout", 0),
            bottom_dmm=_req_int(pp_map, "bottom_dmm", f"{ctx}.passepartout", 0),
            left_dmm=_req_int(pp_map, "left_dmm", f"{ctx}.passepartout", 0),
            right_dmm=_req_int(pp_map, "right_dmm", f"{ctx}.passepartout", 0),
            color_hex=_req_str(pp_map, "color_hex", f"{ctx}.passepartout", "#F7F6F2"),
        ),
        hardware=HangingHardware(
            hanging_type=hanging,
            offset_from_top_dmm=_req_int(hw_map, "offset_from_top_dmm", f"{ctx}.hardware", 300),
            wire_drop_dmm=_req_int(hw_map, "wire_drop_dmm", f"{ctx}.hardware", 0),
            lateral_inset_dmm=_req_int(hw_map, "lateral_inset_dmm", f"{ctx}.hardware", 500),
        ),
    )


def _parse_wall(raw: object, idx: int, known_artworks: set[str]) -> Wall:
    ctx = f"walls[{idx}]"
    d = _req_map(raw, ctx)
    cal_raw = d.get("calibration")
    if cal_raw is None:
        calibration = ProjectorCalibration()
    else:
        cal_map = _req_map(cal_raw, f"{ctx}.calibration")
        defaults = ProjectorCalibration()
        wall_pts = (
            _parse_point_quad_int(cal_map["wall_points_dmm"], f"{ctx}.calibration.wall_points_dmm")
            if "wall_points_dmm" in cal_map
            else defaults.wall_points_dmm
        )
        proj_pts = (
            _parse_point_quad_float(
                cal_map["projector_points_norm"], f"{ctx}.calibration.projector_points_norm"
            )
            if "projector_points_norm" in cal_map
            else defaults.projector_points_norm
        )
        calibration = ProjectorCalibration(
            wall_points_dmm=wall_pts,
            projector_points_norm=proj_pts,
            viewport_x_dmm=_req_int(cal_map, "viewport_x_dmm", f"{ctx}.calibration", 0),
            viewport_width_dmm=_req_int(cal_map, "viewport_width_dmm", f"{ctx}.calibration", 0),
            guide_color=_req_str(cal_map, "guide_color", f"{ctx}.calibration", "cyan"),
            stroke_width_px=_req_int(cal_map, "stroke_width_px", f"{ctx}.calibration", 2),
            show_ghost_image=_req_bool(cal_map, "show_ghost_image", f"{ctx}.calibration", False),
            ghost_opacity=_req_float(cal_map, "ghost_opacity", f"{ctx}.calibration", 0.25),
            show_calibration_grid=_req_bool(
                cal_map, "show_calibration_grid", f"{ctx}.calibration", False
            ),
        )

    placements: list[Placement] = []
    for p_idx, p_raw in enumerate(_req_list(d.get("placements", []), f"{ctx}.placements")):
        p_ctx = f"{ctx}.placements[{p_idx}]"
        pm = _req_map(p_raw, p_ctx)
        art_id = _req_str(pm, "artwork_id", p_ctx)
        if art_id not in known_artworks:
            raise ProjectValidationError(
                f"'{p_ctx}.artwork_id' referencia una obra inexistente: '{art_id}'."
            )
        raw_group = pm.get("group_id")
        if raw_group is not None and not isinstance(raw_group, str):
            raise ProjectValidationError(f"'{p_ctx}.group_id' debe ser texto o null.")
        placements.append(
            Placement(
                id=_req_str(pm, "id", p_ctx),
                artwork_id=art_id,
                x_dmm=_req_int(pm, "x_dmm", p_ctx),
                y_dmm=_req_int(pm, "y_dmm", p_ctx),
                group_id=raw_group,
                z_order=_req_int(pm, "z_order", p_ctx, 0),
                locked=_req_bool(pm, "locked", p_ctx, False),
            )
        )

    try:
        narrative_role = WallNarrativeRole(
            _req_str(d, "narrative_role", ctx, WallNarrativeRole.STANDARD.value)
        )
    except ValueError as exc:
        raise ProjectValidationError(f"Rol narrativo inválido en {ctx}: {exc}") from exc

    return Wall(
        id=_req_str(d, "id", ctx),
        name=_req_str(d, "name", ctx),
        width_dmm=_req_int(d, "width_dmm", ctx),
        height_dmm=_req_int(d, "height_dmm", ctx),
        baseboard_height_dmm=_req_int(d, "baseboard_height_dmm", ctx, 0),
        eye_level_dmm=_req_int(d, "eye_level_dmm", ctx, cm_to_dmm(150)),
        wall_color_hex=_req_str(d, "wall_color_hex", ctx, "#F4F3EF"),
        wall_texture_preset=_req_str(d, "wall_texture_preset", ctx, "none"),
        wall_image_path=_req_str(d, "wall_image_path", ctx, ""),
        wall_image_sha256=_req_str(d, "wall_image_sha256", ctx, ""),
        wall_image_fit=_req_str(d, "wall_image_fit", ctx, "cover"),
        wall_image_opacity=_req_float(d, "wall_image_opacity", ctx, 1.0),
        narrative_role=narrative_role,
        placements=placements,
        calibration=calibration,
    )


def project_from_dict(raw: object) -> ExhibitionProject:
    """Reconstruye y valida un `ExhibitionProject` desde un JSON decodificado."""
    root = _req_map(raw, "root")
    schema_version = _req_int(root, "schema_version", "root")
    if schema_version != SCHEMA_VERSION:
        raise ProjectValidationError(
            f"Versión de esquema no soportada: {schema_version} (esperada {SCHEMA_VERSION})."
        )

    raw_artworks = _req_list(root.get("artworks", []), "artworks")
    artworks = [_parse_artwork(item, idx) for idx, item in enumerate(raw_artworks)]
    known_ids = {art.id for art in artworks}
    walls = [
        _parse_wall(item, idx, known_ids)
        for idx, item in enumerate(_req_list(root.get("walls", []), "walls"))
    ]

    return ExhibitionProject(
        schema_version=schema_version,
        title=_req_str(root, "title", "root"),
        curator=_req_str(root, "curator", "root", ""),
        venue=_req_str(root, "venue", "root", ""),
        default_eye_level_dmm=_req_int(root, "default_eye_level_dmm", "root", cm_to_dmm(150)),
        artworks=artworks,
        walls=walls,
    )


def save_project_atomic(project: ExhibitionProject, path: Path) -> None:
    """Guarda el proyecto de forma atómica (temp file en mismo directorio + fsync + replace)."""
    target = path.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(project_to_dict(project), indent=2, ensure_ascii=False)

    fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, target)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise


def load_project(path: Path) -> ExhibitionProject:
    """Carga y valida un proyecto `.layoutexpo` desde disco."""
    try:
        text = path.read_text(encoding="utf-8")
        decoded: object = json.loads(text)
    except (OSError, json.JSONDecodeError) as exc:
        raise ProjectValidationError(f"No se pudo leer el proyecto '{path}': {exc}") from exc
    return project_from_dict(decoded)
