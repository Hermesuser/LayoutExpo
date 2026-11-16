"""Motor heurístico determinista de reorganización armónica y compositiva (ADR-006).

Opera exclusivamente en décimas de milímetro (dmm) sin mutar el proyecto de entrada,
produciendo un layout equilibrado y una justificación curatorial verificable.
"""

from __future__ import annotations

import copy
import itertools
import math
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from core.geometry import RectDmm, placement_outer_rect
from core.project import (
    Artwork,
    ExhibitionProject,
    Placement,
    Wall,
    WallNarrativeRole,
)
from core.units import cm_to_dmm, format_metric

PERIMETER_MARGIN_DMM = cm_to_dmm(50)
CONSTELLATION_V_GAP_DMM = cm_to_dmm(8)
CurationScope = Literal["active_wall", "all_walls"]


class Orientation(StrEnum):
    """Clasificación de formato exterior de la obra en el muro."""

    VERTICAL = "V"
    HORIZONTAL = "H"
    SQUARE = "C"
    BLOCK = "B"


class SizeBand(StrEnum):
    """Banda relativa de peso visual dentro del proyecto."""

    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"


@dataclass(frozen=True, slots=True)
class _MemberOffset:
    placement: Placement
    artwork: Artwork
    dx_dmm: int
    dy_dmm: int


@dataclass(frozen=True, slots=True)
class _CurationBlock:
    block_id: str
    width_dmm: int
    height_dmm: int
    visual_weight: int
    orientation: Orientation
    size_band: SizeBand
    is_anchor: bool
    is_constellation: bool
    members: tuple[_MemberOffset, ...]


@dataclass(frozen=True, slots=True)
class CurationResult:
    """Resultado completo de la reorganización armónica."""

    project: ExhibitionProject
    rationale: tuple[str, ...]
    warnings: tuple[str, ...]
    metrics: dict[str, object]


def classify_orientation(width_dmm: int, height_dmm: int) -> Orientation:
    """Clasifica una obra en Vertical (V), Horizontal (H) o Cuadrada (C)."""
    if width_dmm <= 0 or height_dmm <= 0:
        raise ValueError("Las dimensiones deben ser positivas.")
    ratio = width_dmm / height_dmm
    if 0.90 <= ratio <= 1.10:
        return Orientation.SQUARE
    return Orientation.VERTICAL if ratio < 0.90 else Orientation.HORIZONTAL


def _compute_size_bands(areas: list[int]) -> tuple[int, int]:
    if not areas:
        return (0, 0)
    min_a = min(areas)
    max_a = max(areas)
    span = max_a - min_a
    if span == 0:
        return (0, max_a + 1)
    return (min_a + span // 3, min_a + (2 * span) // 3)


def _band_for_area(area: int, low_cut: int, high_cut: int) -> SizeBand:
    if area < low_cut:
        return SizeBand.SMALL
    if area > high_cut:
        return SizeBand.LARGE
    return SizeBand.MEDIUM


def _build_initial_blocks(
    placements: list[Placement],
    artworks_by_id: dict[str, Artwork],
    low_cut: int,
    high_cut: int,
) -> list[_CurationBlock]:
    """Agrupa piezas por `group_id` (dípticos/polípticos) o como bloques individuales."""
    grouped: dict[str, list[Placement]] = {}
    singles: list[Placement] = []

    for pl in placements:
        # Disolver constelaciones automáticas previas ("const:...") para recalcular óptimamente
        if pl.group_id and not pl.group_id.startswith("const:"):
            grouped.setdefault(pl.group_id, []).append(pl)
        else:
            singles.append(pl)

    blocks: list[_CurationBlock] = []
    for pl in singles:
        art = artworks_by_id[pl.artwork_id]
        ow, oh = art.outer_size_dmm()
        area = ow * oh
        blocks.append(
            _CurationBlock(
                block_id=pl.id,
                width_dmm=ow,
                height_dmm=oh,
                visual_weight=area,
                orientation=classify_orientation(ow, oh),
                size_band=_band_for_area(area, low_cut, high_cut),
                is_anchor=art.is_anchor,
                is_constellation=False,
                members=(_MemberOffset(placement=pl, artwork=art, dx_dmm=0, dy_dmm=0),),
            )
        )

    for grp_id, grp_pls in sorted(grouped.items()):
        ordered = sorted(grp_pls, key=lambda p: (p.x_dmm, -p.y_dmm))
        min_x = min(p.x_dmm for p in ordered)
        min_y = min(p.y_dmm for p in ordered)
        max_r = max(p.x_dmm + artworks_by_id[p.artwork_id].outer_size_dmm()[0] for p in ordered)
        max_t = max(p.y_dmm + artworks_by_id[p.artwork_id].outer_size_dmm()[1] for p in ordered)
        gw = max(1, max_r - min_x)
        gh = max(1, max_t - min_y)
        total_area = sum(
            artworks_by_id[p.artwork_id].outer_size_dmm()[0]
            * artworks_by_id[p.artwork_id].outer_size_dmm()[1]
            for p in ordered
        )
        members = tuple(
            _MemberOffset(
                placement=p,
                artwork=artworks_by_id[p.artwork_id],
                dx_dmm=p.x_dmm - min_x,
                dy_dmm=p.y_dmm - min_y,
            )
            for p in ordered
        )
        blocks.append(
            _CurationBlock(
                block_id=f"grp:{grp_id}",
                width_dmm=gw,
                height_dmm=gh,
                visual_weight=total_area,
                orientation=Orientation.BLOCK,
                size_band=_band_for_area(total_area, low_cut, high_cut),
                is_anchor=any(m.artwork.is_anchor for m in members),
                is_constellation=False,
                members=members,
            )
        )

    return blocks


def _synthesize_constellations(
    blocks: list[_CurationBlock],
    wall: Wall,
    low_cut: int,
    high_cut: int,
) -> tuple[list[_CurationBlock], int]:
    """Agrupa pares de obras pequeñas en columnas 2×1 cuando compensan obras pesadas."""
    if not blocks:
        return (blocks, 0)

    usable_span = wall.width_dmm - 2 * PERIMETER_MARGIN_DMM
    is_tight = sum(b.width_dmm for b in blocks) > usable_span
    if len(blocks) < 4 and not is_tight:
        return (blocks, 0)

    has_heavy = any(
        b.size_band == SizeBand.LARGE or b.orientation == Orientation.HORIZONTAL for b in blocks
    )
    if not has_heavy:
        return (blocks, 0)

    max_weight = max(b.visual_weight for b in blocks)
    usable_h = wall.height_dmm - wall.baseboard_height_dmm - cm_to_dmm(20)
    small_singles = [
        b
        for b in blocks
        if len(b.members) == 1
        and not b.is_anchor
        and (b.size_band == SizeBand.SMALL or is_tight)
        and b.visual_weight * 2 <= max_weight
    ]
    if len(small_singles) < 2:
        return (blocks, 0)

    small_singles.sort(key=lambda b: (b.visual_weight, b.block_id))
    consumed: set[str] = set()
    new_constellations: list[_CurationBlock] = []

    idx = 0
    while idx + 1 < len(small_singles):
        bottom_b = small_singles[idx]
        top_b = small_singles[idx + 1]
        combined_h = bottom_b.height_dmm + CONSTELLATION_V_GAP_DMM + top_b.height_dmm
        if combined_h <= usable_h:
            col_w = max(bottom_b.width_dmm, top_b.width_dmm)
            m_bot = bottom_b.members[0]
            m_top = top_b.members[0]
            dx_bot = (col_w - bottom_b.width_dmm) // 2
            dx_top = (col_w - top_b.width_dmm) // 2
            dy_top = bottom_b.height_dmm + CONSTELLATION_V_GAP_DMM
            total_area = bottom_b.visual_weight + top_b.visual_weight
            new_constellations.append(
                _CurationBlock(
                    block_id=f"const:{bottom_b.block_id}+{top_b.block_id}",
                    width_dmm=col_w,
                    height_dmm=combined_h,
                    visual_weight=total_area,
                    orientation=Orientation.BLOCK,
                    size_band=_band_for_area(total_area, low_cut, high_cut),
                    is_anchor=False,
                    is_constellation=True,
                    members=(
                        _MemberOffset(m_bot.placement, m_bot.artwork, dx_bot, 0),
                        _MemberOffset(m_top.placement, m_top.artwork, dx_top, dy_top),
                    ),
                )
            )
            consumed.add(bottom_b.block_id)
            consumed.add(top_b.block_id)
            idx += 2
        else:
            idx += 1

    if not new_constellations:
        return (blocks, 0)

    remaining = [b for b in blocks if b.block_id not in consumed]
    return (remaining + new_constellations, len(new_constellations))


def _sequence_cost(
    seq: list[_CurationBlock],
    interval_left: int,
    interval_right: int,
    wall_width_dmm: int,
    anchor_id: str | None,
) -> float:
    """Evalúa ritmo visual, centralidad del punto focal y balance de momento óptico."""
    if not seq:
        return 0.0

    cost = 0.0
    for i in range(len(seq) - 1):
        curr_b = seq[i]
        next_b = seq[i + 1]
        if curr_b.orientation == next_b.orientation and curr_b.orientation != Orientation.BLOCK:
            if curr_b.size_band == next_b.size_band:
                cost += 1000.0
            else:
                cost += 350.0
        else:
            cost -= 80.0

    # Estimar centros X rápidos para balance de momento óptico y centralidad de pieza ancla
    positions = _compute_block_x_positions(
        seq, interval_left, interval_right, wall_width_dmm, anchor_id
    )
    wall_mid = wall_width_dmm / 2.0
    total_w = sum(b.visual_weight for b in seq) or 1
    moment = 0.0
    for b, x_pos in zip(seq, positions, strict=True):
        cx = x_pos + b.width_dmm / 2.0
        moment += b.visual_weight * (cx - wall_mid)
        if anchor_id and b.block_id == anchor_id:
            cost += 1800.0 * abs(cx - wall_mid) / max(1.0, wall_mid)

    normalized_moment = abs(moment) / (total_w * max(1.0, wall_mid))
    cost += 650.0 * normalized_moment
    return cost


def _compute_block_x_positions(
    seq: list[_CurationBlock],
    interval_left: int,
    interval_right: int,
    wall_width_dmm: int,
    anchor_id: str | None,
) -> list[int]:
    """Calcula posiciones X exactas con gutters proporcionales al peso visual vecino."""
    count = len(seq)
    if count == 0:
        return []

    avail = max(0, interval_right - interval_left)
    total_widths = sum(b.width_dmm for b in seq)
    slack = max(0, avail - total_widths)

    if count == 1:
        b = seq[0]
        if anchor_id and b.block_id == anchor_id:
            ideal_x = wall_width_dmm // 2 - b.width_dmm // 2
            clamped = max(interval_left, min(ideal_x, interval_right - b.width_dmm))
            return [clamped]
        return [interval_left + slack // 2]

    # Gutters proporcionales al peso visual adyacente con techo museográfico realista
    avg_w = total_widths / count
    max_gap = max(cm_to_dmm(25), min(cm_to_dmm(85), round(avg_w * 0.90)))
    target_gutter_total = min(slack, max_gap * (count - 1))

    raw_weights = [
        math.sqrt(seq[i].visual_weight) + math.sqrt(seq[i + 1].visual_weight)
        for i in range(count - 1)
    ]
    weight_sum = sum(raw_weights) or 1.0
    gutters = [round(target_gutter_total * (rw / weight_sum)) for rw in raw_weights]
    diff = target_gutter_total - sum(gutters)
    if gutters:
        gutters[len(gutters) // 2] += diff

    cluster_w = total_widths + sum(gutters)
    leftover = max(0, avail - cluster_w)
    start_x = interval_left + leftover // 2

    if anchor_id:
        anchor_idx = next((i for i, b in enumerate(seq) if b.block_id == anchor_id), None)
        if anchor_idx is not None:
            rel_anchor_x = sum(seq[i].width_dmm + gutters[i] for i in range(anchor_idx))
            ideal_start = wall_width_dmm // 2 - (rel_anchor_x + seq[anchor_idx].width_dmm // 2)
            start_x = max(interval_left, min(ideal_start, interval_right - cluster_w))

    xs: list[int] = []
    cursor = start_x
    for idx, b in enumerate(seq):
        xs.append(cursor)
        cursor += b.width_dmm + (gutters[idx] if idx < len(gutters) else 0)
    return xs


def _optimize_sequence(
    blocks: list[_CurationBlock],
    interval_left: int,
    interval_right: int,
    wall_width_dmm: int,
    anchor_id: str | None,
) -> list[_CurationBlock]:
    if len(blocks) <= 1:
        return list(blocks)

    if len(blocks) <= 6:
        best_seq = list(blocks)
        best_cost = _sequence_cost(
            best_seq, interval_left, interval_right, wall_width_dmm, anchor_id
        )
        for perm in itertools.permutations(blocks):
            cand = list(perm)
            c = _sequence_cost(cand, interval_left, interval_right, wall_width_dmm, anchor_id)
            if c < best_cost:
                best_cost = c
                best_seq = cand
        return best_seq

    # Construcción determinista: ancla al centro + alternancia + búsqueda local 2-opt
    remaining = sorted(blocks, key=lambda b: (-b.visual_weight, b.block_id))
    seed: list[_CurationBlock] = []
    if anchor_id:
        anchor_list = [b for b in remaining if b.block_id == anchor_id]
        remaining = [b for b in remaining if b.block_id != anchor_id]
        seed.extend(anchor_list)
    while remaining:
        last_ori = seed[-1].orientation if seed else None
        pick = next((b for b in remaining if b.orientation != last_ori), remaining[0])
        remaining.remove(pick)
        if len(seed) % 2 == 1:
            seed.append(pick)
        else:
            seed.insert(0, pick)

    best_seq = seed
    best_cost = _sequence_cost(best_seq, interval_left, interval_right, wall_width_dmm, anchor_id)
    improved = True
    passes = 0
    while improved and passes < 60:
        improved = False
        passes += 1
        for i in range(len(best_seq)):
            for j in range(i + 1, len(best_seq)):
                cand = best_seq[:]
                cand[i], cand[j] = cand[j], cand[i]
                c = _sequence_cost(cand, interval_left, interval_right, wall_width_dmm, anchor_id)
                if c + 1e-6 < best_cost:
                    best_cost = c
                    best_seq = cand
                    improved = True
    return best_seq


def _free_intervals_around_locked(
    wall: Wall,
    locked_rects: list[RectDmm],
    total_unlocked_width: int,
) -> tuple[list[tuple[int, int]], int, list[str]]:
    """Calcula intervalos horizontales libres respetando margen de 50 cm cuando es factible."""
    warnings: list[str] = []
    min_gap_to_locked = cm_to_dmm(10)

    if not locked_rects:
        ideal_span = wall.width_dmm - 2 * PERIMETER_MARGIN_DMM
        if total_unlocked_width <= ideal_span:
            return (
                [(PERIMETER_MARGIN_DMM, wall.width_dmm - PERIMETER_MARGIN_DMM)],
                PERIMETER_MARGIN_DMM,
                warnings,
            )
        eff_margin = max(0, (wall.width_dmm - total_unlocked_width) // 2)
        warnings.append(
            f"En '{wall.name}', el margen perimetral de 50 cm se redujo a "
            f"{format_metric(eff_margin)} para evitar solapamientos."
        )
        return ([(eff_margin, wall.width_dmm - eff_margin)], eff_margin, warnings)

    # Con piezas bloqueadas: calcular huecos entre margen izquierdo, piezas fijas y margen derecho
    for margin in (PERIMETER_MARGIN_DMM, cm_to_dmm(20), 0):
        intervals: list[tuple[int, int]] = []
        cursor = margin
        right_limit = wall.width_dmm - margin
        for rect in sorted(locked_rects, key=lambda r: r.x):
            seg_end = min(right_limit, rect.x - min_gap_to_locked)
            if seg_end > cursor:
                intervals.append((cursor, seg_end))
            cursor = max(cursor, rect.right + min_gap_to_locked)
        if right_limit > cursor:
            intervals.append((cursor, right_limit))
        if sum(end - start for start, end in intervals) >= total_unlocked_width:
            if margin < PERIMETER_MARGIN_DMM:
                warnings.append(
                    f"En '{wall.name}', margen perimetral ajustado a {format_metric(margin)} "
                    "al convivir con obras bloqueadas."
                )
            return (intervals, margin, warnings)

    warnings.append(
        f"En '{wall.name}', las obras bloqueadas dejan poco espacio libre; "
        "verifica manualmente posibles solapamientos."
    )
    return ([(0, wall.width_dmm)], 0, warnings)


def _assign_blocks_to_intervals(
    blocks: list[_CurationBlock],
    intervals: list[tuple[int, int]],
    anchor_id: str | None,
    wall_mid: int,
) -> list[list[_CurationBlock]]:
    buckets: list[list[_CurationBlock]] = [[] for _ in intervals]
    capacities = [end - start for start, end in intervals]
    used = [0 for _ in intervals]

    def _place_in_best(block: _CurationBlock, prefer_center: bool) -> None:
        best_idx = 0
        best_score = float("inf")
        for idx, (start, end) in enumerate(intervals):
            rem = capacities[idx] - used[idx]
            overflow_pen = 100_000.0 if rem < block.width_dmm else 0.0
            center_dist = abs(((start + end) / 2.0) - wall_mid) if prefer_center else -rem
            score = overflow_pen + center_dist
            if score < best_score:
                best_score = score
                best_idx = idx
        buckets[best_idx].append(block)
        used[best_idx] += block.width_dmm

    ordered = sorted(blocks, key=lambda b: (b.block_id != anchor_id, -b.visual_weight, b.block_id))
    for blk in ordered:
        _place_in_best(blk, prefer_center=(blk.block_id == anchor_id))
    return buckets


def _layout_wall_blocks(
    wall: Wall,
    unlocked_blocks: list[_CurationBlock],
    locked_placements: list[Placement],
    artworks_by_id: dict[str, Artwork],
    anchor_block_id: str | None,
    allow_constellations: bool,
    low_cut: int,
    high_cut: int,
) -> tuple[list[Placement], list[str], list[str], dict[str, float]]:
    rationale: list[str] = []
    warnings: list[str] = []

    if not unlocked_blocks:
        return (
            list(locked_placements),
            rationale,
            warnings,
            {"symmetry": 1.0, "repeat_pairs": 0.0},
        )

    working_blocks = unlocked_blocks
    constellation_count = 0
    if allow_constellations:
        working_blocks, constellation_count = _synthesize_constellations(
            unlocked_blocks, wall, low_cut, high_cut
        )
        if constellation_count > 0:
            rationale.append(
                f"En '{wall.name}' se agruparon {constellation_count} "
                "constelación(es) vertical(es) 2×1 de piezas pequeñas para equilibrar "
                "obras de mayor formato."
            )

    locked_rects = [
        placement_outer_rect(pl, artworks_by_id[pl.artwork_id]) for pl in locked_placements
    ]
    total_unlocked_w = sum(b.width_dmm for b in working_blocks)
    intervals, eff_margin, interval_warnings = _free_intervals_around_locked(
        wall, locked_rects, total_unlocked_w
    )
    warnings.extend(interval_warnings)

    buckets = _assign_blocks_to_intervals(
        working_blocks, intervals, anchor_block_id, wall.width_dmm // 2
    )

    new_placements: list[Placement] = list(locked_placements)
    repeat_pairs = 0
    total_moment = 0.0
    total_weight = 0.0
    wall_mid = wall.width_dmm / 2.0

    for (seg_left, seg_right), seg_blocks in zip(intervals, buckets, strict=True):
        if not seg_blocks:
            continue
        seq = _optimize_sequence(seg_blocks, seg_left, seg_right, wall.width_dmm, anchor_block_id)
        xs = _compute_block_x_positions(seq, seg_left, seg_right, wall.width_dmm, anchor_block_id)

        for i in range(len(seq) - 1):
            if (
                seq[i].orientation == seq[i + 1].orientation
                and seq[i].orientation != Orientation.BLOCK
            ):
                repeat_pairs += 1

        for blk, bx in zip(seq, xs, strict=True):
            # Centrado vertical en eje visual respetando zócalo y techo
            min_y = wall.baseboard_height_dmm + cm_to_dmm(5)
            max_y = max(min_y, wall.height_dmm - blk.height_dmm - cm_to_dmm(5))
            ideal_by = wall.eye_level_dmm - blk.height_dmm // 2
            by = max(min_y, min(ideal_by, max_y))

            total_moment += blk.visual_weight * ((bx + blk.width_dmm / 2.0) - wall_mid)
            total_weight += blk.visual_weight

            for member in blk.members:
                pl = member.placement
                assigned_group = blk.block_id if blk.is_constellation else pl.group_id
                new_placements.append(
                    Placement(
                        id=pl.id,
                        artwork_id=pl.artwork_id,
                        x_dmm=bx + member.dx_dmm,
                        y_dmm=by + member.dy_dmm,
                        group_id=assigned_group,
                        z_order=pl.z_order,
                        locked=False,
                    )
                )

    for lr, lp in zip(locked_rects, locked_placements, strict=True):
        art = artworks_by_id[lp.artwork_id]
        w_area = art.outer_size_dmm()[0] * art.outer_size_dmm()[1]
        total_moment += w_area * (lr.center_x - wall_mid)
        total_weight += w_area

    imbalance = abs(total_moment) / (max(1.0, total_weight) * max(1.0, wall_mid))
    symmetry = max(0.0, 1.0 - imbalance)

    if anchor_block_id and any(b.block_id == anchor_block_id for b in working_blocks):
        anchor_blk = next(b for b in working_blocks if b.block_id == anchor_block_id)
        rationale.append(
            f"Pieza ancla '{anchor_blk.members[0].artwork.title}' ubicada como foco central "
            f"en '{wall.name}' (eje visual {format_metric(wall.eye_level_dmm)})."
        )

    if repeat_pairs == 0 and len(working_blocks) > 1:
        rationale.append(
            f"En '{wall.name}' se aplicó alternancia estricta de ritmos (V / H / C / Bloque) "
            "sin secuencias repetidas."
        )
    elif repeat_pairs > 0:
        warnings.append(
            f"En '{wall.name}' quedaron {repeat_pairs} par(es) adyacentes de igual orientación "
            "por predominio de formato en el inventario."
        )

    if eff_margin >= PERIMETER_MARGIN_DMM:
        rationale.append(
            f"Márgenes perimetrales de 50 cm y espaciamientos proporcionales al peso visual "
            f"aplicados en '{wall.name}' (simetría óptica {round(symmetry * 100)} %)."
        )

    return (
        new_placements,
        rationale,
        warnings,
        {"symmetry": round(symmetry, 3), "repeat_pairs": float(repeat_pairs)},
    )


def _pick_focal_wall_index(walls: list[Wall]) -> int:
    for idx, w in enumerate(walls):
        if w.narrative_role == WallNarrativeRole.CLIMAX:
            return idx
    for idx, w in enumerate(walls):
        if w.narrative_role == WallNarrativeRole.INITIAL:
            return idx
    return len(walls) - 1 if len(walls) > 1 else 0


def reorganize_exhibition(
    project: ExhibitionProject,
    *,
    active_wall_id: str,
    scope: CurationScope = "active_wall",
    allow_constellations: bool = True,
) -> CurationResult:
    """Reorganiza armónicamente un muro o toda la exposición sin mutar el proyecto original."""
    proj = copy.deepcopy(project)
    arts_by_id = proj.artworks_by_id()
    if not proj.walls:
        return CurationResult(
            project=proj,
            rationale=("No hay muros configurados en la exposición.",),
            warnings=(),
            metrics={},
        )

    all_areas = [a.outer_size_dmm()[0] * a.outer_size_dmm()[1] for a in proj.artworks]
    low_cut, high_cut = _compute_size_bands(all_areas)

    rationale: list[str] = []
    warnings: list[str] = []

    if scope == "active_wall":
        wall = next((w for w in proj.walls if w.id == active_wall_id), proj.walls[0])
        locked = [p for p in wall.placements if p.locked]
        unlocked = [p for p in wall.placements if not p.locked]
        if not unlocked and not locked:
            placed_ids = {p.artwork_id for w in proj.walls for p in w.placements}
            unplaced = [a for a in proj.artworks if a.id not in placed_ids]
            if unplaced:
                unlocked = [
                    Placement(
                        id=f"pl-auto-{art.id}",
                        artwork_id=art.id,
                        x_dmm=0,
                        y_dmm=0,
                        z_order=idx,
                    )
                    for idx, art in enumerate(unplaced)
                ]
                rationale.append(
                    f"Se incorporaron {len(unplaced)} obra(s) del catálogo al muro "
                    f"'{wall.name}' para componer el diseño."
                )

        if not unlocked:
            msg = (
                "Todas las obras del muro están bloqueadas."
                if locked
                else f"No hay obras colocadas en '{wall.name}' ni libres en el catálogo."
            )
            return CurationResult(project=proj, rationale=(msg,), warnings=(), metrics={})

        blocks = _build_initial_blocks(unlocked, arts_by_id, low_cut, high_cut)
        anchor_blk = next(
            (b for b in blocks if b.is_anchor),
            max(blocks, key=lambda b: b.visual_weight),
        )
        placements, w_rat, w_warn, w_metrics = _layout_wall_blocks(
            wall,
            blocks,
            locked,
            arts_by_id,
            anchor_blk.block_id,
            allow_constellations,
            low_cut,
            high_cut,
        )
        wall.placements = placements
        if locked:
            rationale.append(f"Se respetaron {len(locked)} posición(es) bloqueada(s) manualmente.")
        rationale.extend(w_rat)
        warnings.extend(w_warn)
        return CurationResult(
            project=proj,
            rationale=tuple(rationale),
            warnings=tuple(warnings),
            metrics={wall.id: w_metrics},
        )

    # scope == "all_walls": distribuir todo el inventario desbloqueado en el arco narrativo
    locked_by_wall: dict[str, list[Placement]] = {
        w.id: [p for p in w.placements if p.locked] for w in proj.walls
    }
    locked_art_ids = {p.artwork_id for pls in locked_by_wall.values() for p in pls}

    # Reutilizar placements desbloqueados o crear placements para catálogo libre
    unlocked_pool: list[Placement] = []
    seen_art_ids: set[str] = set(locked_art_ids)
    for w in proj.walls:
        for p in w.placements:
            if not p.locked and p.artwork_id not in seen_art_ids:
                unlocked_pool.append(p)
                seen_art_ids.add(p.artwork_id)
    for idx, art in enumerate(proj.artworks):
        if art.id not in seen_art_ids:
            unlocked_pool.append(
                Placement(id=f"pl-auto-{art.id}", artwork_id=art.id, x_dmm=0, y_dmm=0, z_order=idx)
            )
            seen_art_ids.add(art.id)

    if not unlocked_pool:
        return CurationResult(
            project=proj,
            rationale=("No hay obras desbloqueadas disponibles para redistribuir.",),
            warnings=(),
            metrics={},
        )

    all_blocks = _build_initial_blocks(unlocked_pool, arts_by_id, low_cut, high_cut)
    focal_wall_idx = _pick_focal_wall_index(proj.walls)
    anchor_blk = next(
        (b for b in all_blocks if b.is_anchor),
        max(all_blocks, key=lambda b: b.visual_weight),
    )

    wall_buckets: list[list[_CurationBlock]] = [[] for _ in proj.walls]
    wall_buckets[focal_wall_idx].append(anchor_blk)
    used_w = [0 for _ in proj.walls]
    used_w[focal_wall_idx] += anchor_blk.width_dmm
    capacities = [max(1, w.width_dmm - 2 * PERIMETER_MARGIN_DMM) for w in proj.walls]

    others = [b for b in all_blocks if b.block_id != anchor_blk.block_id]
    others.sort(key=lambda b: (-b.visual_weight, b.block_id))
    for blk in others:
        # Repartir equilibrando ocupación proporcional entre muros sin desbordar si hay alternativa
        target_idx = min(
            range(len(proj.walls)),
            key=lambda idx: (
                0 if used_w[idx] + blk.width_dmm <= capacities[idx] else 1,
                used_w[idx] / capacities[idx],
                len(wall_buckets[idx]),
                idx,
            ),
        )
        wall_buckets[target_idx].append(blk)
        used_w[target_idx] += blk.width_dmm

    all_metrics: dict[str, object] = {}
    for idx, wall in enumerate(proj.walls):
        locked = locked_by_wall[wall.id]
        anchor_id = anchor_blk.block_id if idx == focal_wall_idx else None
        placements, w_rat, w_warn, w_metrics = _layout_wall_blocks(
            wall,
            wall_buckets[idx],
            locked,
            arts_by_id,
            anchor_id,
            allow_constellations,
            low_cut,
            high_cut,
        )
        wall.placements = placements
        rationale.extend(w_rat)
        warnings.extend(w_warn)
        all_metrics[wall.id] = w_metrics

    total_locked = sum(len(v) for v in locked_by_wall.values())
    if total_locked > 0:
        rationale.insert(0, f"Se respetaron {total_locked} posición(es) bloqueada(s) en sala.")

    return CurationResult(
        project=proj,
        rationale=tuple(rationale),
        warnings=tuple(warnings),
        metrics=all_metrics,
    )
