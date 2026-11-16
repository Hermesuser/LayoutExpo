"""Pruebas unitarias del motor heurístico de reorganización armónica (ADR-006)."""

from __future__ import annotations

import pytest

from core import (
    Artwork,
    ExhibitionProject,
    FrameSpec,
    PassepartoutSpec,
    Placement,
    Wall,
    WallNarrativeRole,
    classify_orientation,
    reorganize_exhibition,
)
from core.units import cm_to_dmm


def _make_artwork(
    art_id: str,
    width_cm: float,
    height_cm: float,
    *,
    is_anchor: bool = False,
) -> Artwork:
    return Artwork(
        id=art_id,
        title=f"Obra {art_id}",
        image_width_dmm=cm_to_dmm(width_cm),
        image_height_dmm=cm_to_dmm(height_cm),
        frame=FrameSpec.uniform(0),
        passepartout=PassepartoutSpec.uniform(0),
        is_anchor=is_anchor,
    )


def test_classify_orientation_variants() -> None:
    assert classify_orientation(3000, 5000) == "V"
    assert classify_orientation(5000, 3000) == "H"
    assert classify_orientation(4000, 4000) == "C"
    assert classify_orientation(4400, 4000) == "C"
    with pytest.raises(ValueError):
        classify_orientation(0, 4000)


def test_anchor_placement_and_50cm_margin_with_immutability() -> None:
    wall = Wall(id="w1", name="Principal", width_dmm=cm_to_dmm(600), height_dmm=cm_to_dmm(300))
    a1 = _make_artwork("v1", 40, 60)
    a2 = _make_artwork("anchor", 70, 50, is_anchor=True)
    a3 = _make_artwork("v2", 40, 60)
    wall.placements = [
        Placement(id="p1", artwork_id="v1", x_dmm=cm_to_dmm(60), y_dmm=cm_to_dmm(100)),
        Placement(id="p2", artwork_id="anchor", x_dmm=cm_to_dmm(120), y_dmm=cm_to_dmm(100)),
        Placement(id="p3", artwork_id="v2", x_dmm=cm_to_dmm(220), y_dmm=cm_to_dmm(100)),
    ]
    proj = ExhibitionProject(title="Expo Test", artworks=[a1, a2, a3], walls=[wall])
    original_x = [p.x_dmm for p in proj.walls[0].placements]

    res = reorganize_exhibition(proj, active_wall_id="w1", scope="active_wall")

    # El proyecto original permanece inmutable
    assert [p.x_dmm for p in proj.walls[0].placements] == original_x

    placed = sorted(res.project.walls[0].placements, key=lambda p: p.x_dmm)
    assert len(placed) == 3
    assert [p.artwork_id for p in placed] == ["v1", "anchor", "v2"] or [
        p.artwork_id for p in placed
    ] == ["v2", "anchor", "v1"]

    # Ancla centrada alrededor del eje del muro (300 cm)
    anchor_pl = next(p for p in placed if p.artwork_id == "anchor")
    anchor_center = anchor_pl.x_dmm + cm_to_dmm(70) // 2
    assert abs(anchor_center - cm_to_dmm(300)) <= cm_to_dmm(5)

    # Margen perimetral >= 50 cm en ambos extremos
    arts = res.project.artworks_by_id()
    leftmost = placed[0]
    rightmost = placed[-1]
    rw, _ = arts[rightmost.artwork_id].outer_size_dmm()
    assert leftmost.x_dmm >= cm_to_dmm(50)
    assert rightmost.x_dmm + rw <= wall.width_dmm - cm_to_dmm(50)
    assert any("márgenes" in r.lower() or "ancla" in r.lower() for r in res.rationale)


def test_rhythm_alternation_avoids_consecutive_identical_large_verticals() -> None:
    wall = Wall(id="w1", name="Ritmo", width_dmm=cm_to_dmm(700), height_dmm=cm_to_dmm(300))
    arts = [
        _make_artwork("v_big1", 60, 90),
        _make_artwork("v_big2", 60, 90),
        _make_artwork("h1", 80, 50),
        _make_artwork("c1", 55, 55),
    ]
    wall.placements = [
        Placement(id=f"p{i}", artwork_id=a.id, x_dmm=cm_to_dmm(50 + i * 90), y_dmm=cm_to_dmm(100))
        for i, a in enumerate(arts)
    ]
    proj = ExhibitionProject(title="Ritmo", artworks=arts, walls=[wall])

    res = reorganize_exhibition(proj, active_wall_id="w1", allow_constellations=False)
    ordered = [p.artwork_id for p in sorted(res.project.walls[0].placements, key=lambda p: p.x_dmm)]
    # Las dos verticales grandes no deben quedar adyacentes cuando hay H/C disponibles
    idx1 = ordered.index("v_big1")
    idx2 = ordered.index("v_big2")
    assert abs(idx1 - idx2) > 1


def test_constellation_pairing_and_optical_balance() -> None:
    wall = Wall(id="w1", name="Balance", width_dmm=cm_to_dmm(600), height_dmm=cm_to_dmm(320))
    arts = [
        _make_artwork("heavy_h", 140, 80, is_anchor=True),
        _make_artwork("small_1", 30, 35),
        _make_artwork("small_2", 30, 35),
        _make_artwork("med_v", 50, 75),
    ]
    wall.placements = [
        Placement(id=f"p{i}", artwork_id=a.id, x_dmm=cm_to_dmm(60 + i * 80), y_dmm=cm_to_dmm(100))
        for i, a in enumerate(arts)
    ]
    proj = ExhibitionProject(title="Balance", artworks=arts, walls=[wall])

    res = reorganize_exhibition(proj, active_wall_id="w1", allow_constellations=True)
    grouped = [p for p in res.project.walls[0].placements if p.group_id is not None]
    assert len(grouped) == 2
    assert abs(grouped[0].x_dmm - grouped[1].x_dmm) <= cm_to_dmm(2)
    assert grouped[0].y_dmm != grouped[1].y_dmm


def test_locked_placements_preserved_and_narrow_wall_emits_warning() -> None:
    wall = Wall(id="w1", name="Estrecho", width_dmm=cm_to_dmm(220), height_dmm=cm_to_dmm(260))
    a_lock = _make_artwork("locked_art", 50, 60)
    a_free1 = _make_artwork("free1", 60, 70)
    a_free2 = _make_artwork("free2", 60, 70)
    wall.placements = [
        Placement(
            id="p_lock",
            artwork_id="locked_art",
            x_dmm=cm_to_dmm(60),
            y_dmm=cm_to_dmm(110),
            locked=True,
        ),
        Placement(id="p_f1", artwork_id="free1", x_dmm=cm_to_dmm(120), y_dmm=cm_to_dmm(100)),
        Placement(id="p_f2", artwork_id="free2", x_dmm=cm_to_dmm(150), y_dmm=cm_to_dmm(100)),
    ]
    proj = ExhibitionProject(title="Bloqueo", artworks=[a_lock, a_free1, a_free2], walls=[wall])

    res = reorganize_exhibition(proj, active_wall_id="w1", allow_constellations=False)
    locked_after = next(p for p in res.project.walls[0].placements if p.id == "p_lock")
    assert locked_after.x_dmm == cm_to_dmm(60)
    assert locked_after.y_dmm == cm_to_dmm(110)
    assert locked_after.locked is True
    assert len(res.warnings) >= 1


def test_all_walls_places_anchor_on_climax_wall() -> None:
    w_init = Wall(
        id="w-init",
        name="Inicio",
        width_dmm=cm_to_dmm(500),
        height_dmm=cm_to_dmm(300),
        narrative_role=WallNarrativeRole.INITIAL,
    )
    w_climax = Wall(
        id="w-climax",
        name="Climax",
        width_dmm=cm_to_dmm(500),
        height_dmm=cm_to_dmm(300),
        narrative_role=WallNarrativeRole.CLIMAX,
    )
    arts = [
        _make_artwork("a1", 50, 70),
        _make_artwork("a_anchor", 90, 60, is_anchor=True),
        _make_artwork("a3", 60, 45),
        _make_artwork("a4", 45, 65),
    ]
    # Todas sin colocar aún o en w-init
    w_init.placements = [
        Placement(id="p1", artwork_id="a1", x_dmm=cm_to_dmm(60), y_dmm=cm_to_dmm(100)),
        Placement(id="p2", artwork_id="a_anchor", x_dmm=cm_to_dmm(160), y_dmm=cm_to_dmm(100)),
    ]
    proj = ExhibitionProject(title="Arco", artworks=arts, walls=[w_init, w_climax])

    res = reorganize_exhibition(proj, active_wall_id="w-init", scope="all_walls")
    climax_wall = next(w for w in res.project.walls if w.id == "w-climax")
    climax_art_ids = {p.artwork_id for p in climax_wall.placements}
    assert "a_anchor" in climax_art_ids
    total_placed = sum(len(w.placements) for w in res.project.walls)
    assert total_placed == 4


def test_wide_wall_two_works_uses_natural_museum_gutter_and_centering() -> None:
    wall = Wall(id="w1", name="Galeria", width_dmm=cm_to_dmm(600), height_dmm=cm_to_dmm(300))
    arts = [_make_artwork("a1", 50, 70), _make_artwork("a2", 60, 45)]
    wall.placements = [
        Placement(id="p1", artwork_id="a1", x_dmm=cm_to_dmm(50), y_dmm=cm_to_dmm(100)),
        Placement(id="p2", artwork_id="a2", x_dmm=cm_to_dmm(490), y_dmm=cm_to_dmm(100)),
    ]
    proj = ExhibitionProject(title="Dos obras", artworks=arts, walls=[wall])

    res = reorganize_exhibition(proj, active_wall_id="w1", scope="active_wall")
    placed = sorted(res.project.walls[0].placements, key=lambda p: p.x_dmm)
    w_first = res.project.artworks_by_id()[placed[0].artwork_id].outer_size_dmm()[0]
    gap_dmm = placed[1].x_dmm - (placed[0].x_dmm + w_first)
    assert cm_to_dmm(20) <= gap_dmm <= cm_to_dmm(90)
    # Ambos quedan centrados en la zona media del muro en vez de pegados a x=50 y x=490
    assert placed[0].x_dmm > cm_to_dmm(120)
    assert placed[1].x_dmm < cm_to_dmm(420)


def test_rerun_dissolves_previous_auto_constellation() -> None:
    wall = Wall(id="w1", name="Reejecucion", width_dmm=cm_to_dmm(600), height_dmm=cm_to_dmm(320))
    arts = [
        _make_artwork("heavy_h", 140, 80, is_anchor=True),
        _make_artwork("small_1", 30, 35),
        _make_artwork("small_2", 30, 35),
        _make_artwork("med_v", 50, 75),
    ]
    wall.placements = [
        Placement(id=f"p{i}", artwork_id=a.id, x_dmm=cm_to_dmm(60 + i * 80), y_dmm=cm_to_dmm(100))
        for i, a in enumerate(arts)
    ]
    proj = ExhibitionProject(title="ReRun", artworks=arts, walls=[wall])

    first = reorganize_exhibition(proj, active_wall_id="w1", allow_constellations=True)
    # Añadir una 5ta obra y volver a reorganizar: no debe conservar group_id congelado ni solapar
    extra = _make_artwork("h2", 75, 50)
    second_proj = first.project
    second_proj.artworks.append(extra)
    second_proj.walls[0].placements.append(
        Placement(id="p_extra", artwork_id="h2", x_dmm=cm_to_dmm(55), y_dmm=cm_to_dmm(110))
    )
    second = reorganize_exhibition(second_proj, active_wall_id="w1", allow_constellations=True)
    assert len(second.project.walls[0].placements) == 5


def test_active_wall_empty_picks_up_unplaced_catalog_artworks() -> None:
    wall = Wall(id="w1", name="Vacio", width_dmm=cm_to_dmm(500), height_dmm=cm_to_dmm(300))
    arts = [_make_artwork("a1", 50, 70), _make_artwork("a2", 80, 50, is_anchor=True)]
    proj = ExhibitionProject(title="Pendientes", artworks=arts, walls=[wall])

    res = reorganize_exhibition(proj, active_wall_id="w1", scope="active_wall")
    assert {p.artwork_id for p in res.project.walls[0].placements} == {"a1", "a2"}
    assert any("incorporaron" in r.lower() for r in res.rationale)
