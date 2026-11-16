"""Plantillas predefinidas de composición museográfica y galería para LayoutExpo."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass

from core.project import (
    Artwork,
    ExhibitionProject,
    FrameSpec,
    HangingHardware,
    MountingType,
    PassepartoutSpec,
    Placement,
    ProjectValidationError,
    Wall,
)
from core.units import cm_to_dmm


@dataclass(frozen=True, slots=True)
class PresetSlot:
    """Ranura geométrica dentro de una plantilla (coordenadas en cm desde origen del bloque)."""

    x_cm: float
    y_cm: float
    width_cm: float
    height_cm: float
    priority: int = 1


@dataclass(frozen=True, slots=True)
class PresetDefinition:
    """Definición completa de una plantilla reutilizable de montaje."""

    id: str
    name: str
    category: str
    description: str
    slots: tuple[PresetSlot, ...]


@dataclass(frozen=True, slots=True)
class PresetResult:
    """Resultado inmutable tras aplicar una plantilla sobre un muro."""

    project: ExhibitionProject
    preset_id: str
    preset_name: str
    used_existing: int
    created_samples: int
    rationale: list[str]
    warnings: list[str]


_PRESETS: tuple[PresetDefinition, ...] = (
    PresetDefinition(
        id="diamante_clasico",
        name="Diamante Simétrico",
        category="Galería",
        description="Foco central doble rodeado de satélites equilibrados (10 piezas).",
        slots=(
            PresetSlot(39.0, 44.0, 21.0, 30.0, priority=10),
            PresetSlot(34.5, 20.0, 30.0, 21.0, priority=9),
            PresetSlot(18.5, 36.0, 13.0, 18.0, priority=6),
            PresetSlot(16.5, 13.0, 15.0, 20.0, priority=7),
            PresetSlot(3.5, 24.0, 10.0, 15.0, priority=3),
            PresetSlot(63.0, 44.0, 15.0, 20.0, priority=8),
            PresetSlot(67.5, 20.0, 15.0, 20.0, priority=7),
            PresetSlot(85.5, 22.0, 10.0, 15.0, priority=3),
            PresetSlot(34.5, -1.0, 13.0, 18.0, priority=5),
            PresetSlot(50.5, 7.0, 15.0, 10.0, priority=4),
        ),
    ),
    PresetDefinition(
        id="salon_escalonado",
        name="Salón Escalonado",
        category="Galería",
        description="Ritmo horizontal en dos niveles alternando alturas (10 piezas).",
        slots=(
            PresetSlot(51.0, 37.0, 21.0, 30.0, priority=10),
            PresetSlot(18.0, 4.0, 21.0, 30.0, priority=9),
            PresetSlot(0.0, 14.0, 15.0, 20.0, priority=6),
            PresetSlot(42.0, 14.0, 15.0, 20.0, priority=7),
            PresetSlot(75.0, 37.0, 15.0, 20.0, priority=7),
            PresetSlot(35.0, 37.0, 13.0, 18.0, priority=5),
            PresetSlot(60.0, 16.0, 13.0, 18.0, priority=5),
            PresetSlot(22.0, 37.0, 10.0, 15.0, priority=4),
            PresetSlot(76.0, 19.0, 10.0, 15.0, priority=3),
            PresetSlot(93.0, 39.0, 10.0, 15.0, priority=2),
        ),
    ),
    PresetDefinition(
        id="asimetrico_diagonal",
        name="Asimétrico Diagonal",
        category="Galería",
        description="Composición ascendente compensada con dos piezas ancla (10 piezas).",
        slots=(
            PresetSlot(31.0, 17.0, 30.0, 21.0, priority=10),
            PresetSlot(64.0, 26.0, 21.0, 30.0, priority=9),
            PresetSlot(13.0, 21.0, 15.0, 20.0, priority=7),
            PresetSlot(41.0, 41.0, 20.0, 15.0, priority=8),
            PresetSlot(31.0, -6.0, 15.0, 20.0, priority=6),
            PresetSlot(10.0, 5.0, 18.0, 13.0, priority=5),
            PresetSlot(64.0, 5.0, 13.0, 18.0, priority=5),
            PresetSlot(0.0, 26.0, 10.0, 15.0, priority=3),
            PresetSlot(64.0, 59.0, 10.0, 15.0, priority=3),
            PresetSlot(88.0, 34.0, 10.0, 15.0, priority=2),
        ),
    ),
    PresetDefinition(
        id="reticula_compacta",
        name="Retícula Compacta",
        category="Galería",
        description="Bloque rectangular con perímetro alineado y calles uniformes (10 piezas).",
        slots=(
            PresetSlot(0.0, 23.0, 21.0, 30.0, priority=10),
            PresetSlot(58.0, 23.0, 21.0, 30.0, priority=9),
            PresetSlot(0.0, 5.0, 20.0, 15.0, priority=7),
            PresetSlot(23.0, 5.0, 20.0, 15.0, priority=7),
            PresetSlot(59.0, 5.0, 20.0, 15.0, priority=6),
            PresetSlot(24.0, 40.0, 18.0, 13.0, priority=5),
            PresetSlot(37.0, 23.0, 18.0, 13.0, priority=5),
            PresetSlot(45.0, 38.0, 10.0, 15.0, priority=4),
            PresetSlot(24.0, 23.0, 10.0, 15.0, priority=4),
            PresetSlot(46.0, 5.0, 10.0, 15.0, priority=3),
        ),
    ),
    PresetDefinition(
        id="triptico_clasico",
        name="Tríptico Clásico",
        category="Museo",
        description="Tres obras centradas en eje visual con foco central (3 piezas).",
        slots=(
            PresetSlot(58.0, 0.0, 60.0, 50.0, priority=10),
            PresetSlot(0.0, 0.0, 40.0, 50.0, priority=7),
            PresetSlot(136.0, 0.0, 40.0, 50.0, priority=7),
        ),
    ),
    PresetDefinition(
        id="linea_museo",
        name="Línea de Museo",
        category="Museo",
        description="Secuencia horizontal equilibrada sobre la línea de horizonte (5 piezas).",
        slots=(
            PresetSlot(154.0, 2.5, 75.0, 55.0, priority=10),
            PresetSlot(67.0, 7.5, 65.0, 45.0, priority=8),
            PresetSlot(251.0, 7.5, 65.0, 45.0, priority=8),
            PresetSlot(0.0, 0.0, 45.0, 60.0, priority=6),
            PresetSlot(338.0, 0.0, 45.0, 60.0, priority=6),
        ),
    ),
)

_PRESETS_BY_ID: dict[str, PresetDefinition] = {p.id: p for p in _PRESETS}


def list_layout_presets() -> list[dict[str, object]]:
    """Devuelve el catálogo de plantillas con rectángulos normalizados para vista previa SVG."""
    out: list[dict[str, object]] = []
    for preset in _PRESETS:
        min_x = min(s.x_cm for s in preset.slots)
        min_y = min(s.y_cm for s in preset.slots)
        max_x = max(s.x_cm + s.width_cm for s in preset.slots)
        max_y = max(s.y_cm + s.height_cm for s in preset.slots)
        span_w = max(1.0, max_x - min_x)
        span_h = max(1.0, max_y - min_y)
        out.append(
            {
                "id": preset.id,
                "name": preset.name,
                "category": preset.category,
                "description": preset.description,
                "slot_count": len(preset.slots),
                "preview": {
                    "width": round(span_w, 2),
                    "height": round(span_h, 2),
                    "rects": [
                        {
                            "x": round(s.x_cm - min_x, 2),
                            # Coordenadas SVG superiores para previsualización
                            "y": round(max_y - (s.y_cm + s.height_cm), 2),
                            "width": s.width_cm,
                            "height": s.height_cm,
                        }
                        for s in preset.slots
                    ],
                },
            }
        )
    return out


def _make_sample_artwork(idx: int, width_dmm: int, height_dmm: int) -> Artwork:
    w_cm = round(width_dmm / 100.0)
    h_cm = round(height_dmm / 100.0)
    return Artwork(
        id=f"art-tpl-{idx}",
        title=f"Marco {w_cm}×{h_cm} cm",
        medium="Plantilla",
        image_width_dmm=max(600, width_dmm - 400),
        image_height_dmm=max(600, height_dmm - 400),
        mounting_type=MountingType.FRAMED,
        frame=FrameSpec.uniform(200, color_hex="#1C1C1E"),
        passepartout=PassepartoutSpec.uniform(0),
        hardware=HangingHardware(),
        is_anchor=(idx == 1),
    )


def _scale_artwork_to_slot(
    art: Artwork,
    slot_w_dmm: int,
    slot_h_dmm: int,
    *,
    preserve_aspect: bool,
) -> Artwork:
    """Ajusta una obra al tamaño objetivo del hueco preservando la proporción si se solicita."""
    copied = deepcopy(art)
    frame_dx = (
        0
        if copied.mounting_type in (MountingType.DIRECT, MountingType.CANVAS)
        else copied.frame.left_dmm
        + copied.frame.right_dmm
        + copied.passepartout.left_dmm
        + copied.passepartout.right_dmm
    )
    frame_dy = (
        0
        if copied.mounting_type in (MountingType.DIRECT, MountingType.CANVAS)
        else copied.frame.top_dmm
        + copied.frame.bottom_dmm
        + copied.passepartout.top_dmm
        + copied.passepartout.bottom_dmm
    )
    target_w = max(800, slot_w_dmm - frame_dx)
    target_h = max(800, slot_h_dmm - frame_dy)
    if preserve_aspect:
        ratio = copied.image_width_dmm / max(1, copied.image_height_dmm)
        if target_w / max(1, target_h) > ratio:
            new_h = target_h
            new_w = max(800, round(new_h * ratio))
        else:
            new_w = target_w
            new_h = max(800, round(new_w / max(0.05, ratio)))
        copied.image_width_dmm = new_w
        copied.image_height_dmm = new_h
    else:
        copied.image_width_dmm = target_w
        copied.image_height_dmm = target_h
    return copied


def apply_layout_preset(
    project: ExhibitionProject,
    *,
    wall_id: str,
    preset_id: str,
    scale_factor: float = 1.0,
    preserve_aspect: bool = True,
    create_placeholders: bool = True,
) -> PresetResult:
    """Aplica una plantilla predefinida centrándola en el muro sin mutar el proyecto."""
    preset = _PRESETS_BY_ID.get(preset_id)
    if preset is None:
        raise ProjectValidationError(f"Plantilla desconocida: '{preset_id}'.")
    if scale_factor <= 0 or scale_factor > 4.0:
        raise ProjectValidationError("scale_factor debe estar entre 0 y 4.0.")

    next_proj = deepcopy(project)
    wall: Wall | None = next((w for w in next_proj.walls if w.id == wall_id), None)
    if wall is None:
        raise ProjectValidationError(f"Muro '{wall_id}' no encontrado.")

    locked_pls = [pl for pl in wall.placements if pl.locked]
    used_elsewhere = {
        pl.artwork_id for w in next_proj.walls if w.id != wall.id for pl in w.placements
    }
    locked_art_ids = {pl.artwork_id for pl in locked_pls}

    # Candidatos: primero obras ya en el muro (no bloqueadas), luego disponibles en catálogo
    on_wall_ids = [pl.artwork_id for pl in wall.placements if not pl.locked]
    available_catalog = [
        art.id
        for art in next_proj.artworks
        if art.id not in locked_art_ids
        and art.id not in set(on_wall_ids)
        and art.id not in used_elsewhere
    ]
    candidate_ids = on_wall_ids + available_catalog
    arts_by_id = next_proj.artworks_by_id()
    candidates = [arts_by_id[aid] for aid in candidate_ids if aid in arts_by_id]
    candidates.sort(
        key=lambda a: (1 if a.is_anchor else 0, a.image_width_dmm * a.image_height_dmm),
        reverse=True,
    )

    ordered_slots = sorted(preset.slots, key=lambda s: s.priority, reverse=True)
    min_x = min(s.x_cm for s in preset.slots)
    min_y = min(s.y_cm for s in preset.slots)
    max_x = max(s.x_cm + s.width_cm for s in preset.slots)
    max_y = max(s.y_cm + s.height_cm for s in preset.slots)
    cluster_w_dmm = cm_to_dmm((max_x - min_x) * scale_factor)
    cluster_h_dmm = cm_to_dmm((max_y - min_y) * scale_factor)

    # Limitar escala si el bloque supera el área utilizable del muro
    usable_w = max(cm_to_dmm(60), wall.width_dmm - cm_to_dmm(40))
    usable_h = max(cm_to_dmm(60), wall.height_dmm - wall.baseboard_height_dmm - cm_to_dmm(30))
    fit_ratio = min(1.0, usable_w / max(1, cluster_w_dmm), usable_h / max(1, cluster_h_dmm))
    eff_scale = scale_factor * fit_ratio

    eff_w_dmm = cm_to_dmm((max_x - min_x) * eff_scale)
    eff_h_dmm = cm_to_dmm((max_y - min_y) * eff_scale)
    origin_x = (wall.width_dmm - eff_w_dmm) // 2
    min_floor_y = wall.baseboard_height_dmm + cm_to_dmm(15)
    max_bottom_y = max(min_floor_y, wall.height_dmm - eff_h_dmm - cm_to_dmm(10))
    origin_y = max(min_floor_y, min(max_bottom_y, wall.eye_level_dmm - eff_h_dmm // 2))

    new_placements: list[Placement] = list(locked_pls)
    used_existing = 0
    created_samples = 0
    existing_art_ids = {a.id for a in next_proj.artworks}

    for idx, slot in enumerate(ordered_slots):
        slot_w_dmm = cm_to_dmm(slot.width_cm * eff_scale)
        slot_h_dmm = cm_to_dmm(slot.height_cm * eff_scale)
        slot_x_dmm = origin_x + cm_to_dmm((slot.x_cm - min_x) * eff_scale)
        slot_y_dmm = origin_y + cm_to_dmm((slot.y_cm - min_y) * eff_scale)

        if idx < len(candidates):
            art = _scale_artwork_to_slot(
                candidates[idx], slot_w_dmm, slot_h_dmm, preserve_aspect=preserve_aspect
            )
            # Reemplazar medidas en catálogo si la escala del preset las adaptó
            for i, item in enumerate(next_proj.artworks):
                if item.id == art.id:
                    next_proj.artworks[i] = art
                    break
            ow, oh = art.outer_size_dmm()
            px = slot_x_dmm + (slot_w_dmm - ow) // 2
            py = slot_y_dmm + (slot_h_dmm - oh) // 2
            used_existing += 1
            art_id = art.id
        elif create_placeholders:
            sample_num = len(next_proj.artworks) + 1
            sample = _make_sample_artwork(sample_num, slot_w_dmm, slot_h_dmm)
            while sample.id in existing_art_ids:
                sample_num += 1
                sample = _make_sample_artwork(sample_num, slot_w_dmm, slot_h_dmm)
            existing_art_ids.add(sample.id)
            next_proj.artworks.append(sample)
            px = slot_x_dmm
            py = slot_y_dmm
            created_samples += 1
            art_id = sample.id
        else:
            break

        new_placements.append(
            Placement(
                id=f"pl-tpl-{idx + 1}",
                artwork_id=art_id,
                x_dmm=max(0, min(wall.width_dmm - cm_to_dmm(10), px)),
                y_dmm=max(wall.baseboard_height_dmm, py),
                group_id=f"preset:{preset.id}",
                z_order=idx,
                locked=False,
            )
        )

    wall.placements = new_placements
    warnings: list[str] = []
    if fit_ratio < 0.99:
        warnings.append(
            "La plantilla se escaló proporcionalmente para encajar dentro del ancho/alto del muro."
        )
    if locked_pls:
        warnings.append(
            f"Se conservaron {len(locked_pls)} obra(s) bloqueada(s) en su posición original."
        )

    eye_cm = round(wall.eye_level_dmm / 100, 1)
    rationale = [
        f"Se aplicó la plantilla '{preset.name}' centrada en el eje visual ({eye_cm} cm).",
    ]
    if used_existing:
        rationale.append(
            f"Se ubicaron {used_existing} obra(s) priorizando el foco principal en el ancla."
        )
    if created_samples:
        rationale.append(
            f"Se generaron {created_samples} marco(s) de muestra editables para completar."
        )

    return PresetResult(
        project=next_proj,
        preset_id=preset.id,
        preset_name=preset.name,
        used_existing=used_existing,
        created_samples=created_samples,
        rationale=rationale,
        warnings=warnings,
    )
