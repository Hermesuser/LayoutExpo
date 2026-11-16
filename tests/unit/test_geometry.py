"""Pruebas unitarias para core.geometry."""

import pytest

from core.geometry import (
    align_placements,
    compute_anchor_points,
    distribute_horizontally,
    placement_image_rect,
    placement_outer_rect,
    snap_placement,
    validate_wall_bounds,
    wall_dimension_report,
)
from core.project import (
    Artwork,
    FrameSpec,
    HangingHardware,
    HangingType,
    MountingType,
    Placement,
    Wall,
)
from core.units import cm_to_dmm, m_to_dmm


def _make_artwork(
    art_id: str,
    width_cm: int,
    height_cm: int,
    hanging_type: HangingType = HangingType.SINGLE_CENTER,
    wire_drop_cm: int = 0,
) -> Artwork:
    return Artwork(
        id=art_id,
        title=f"Obra {art_id}",
        image_width_dmm=cm_to_dmm(width_cm),
        image_height_dmm=cm_to_dmm(height_cm),
        mounting_type=MountingType.FRAMED,
        frame=FrameSpec.uniform(0),
        hardware=HangingHardware(
            hanging_type=hanging_type,
            offset_from_top_dmm=cm_to_dmm(4),
            wire_drop_dmm=cm_to_dmm(wire_drop_cm),
            lateral_inset_dmm=cm_to_dmm(10),
        ),
    )


def test_compute_anchor_points_single_with_wire_and_dual() -> None:
    single = _make_artwork("a1", 50, 40, HangingType.SINGLE_CENTER, wire_drop_cm=3)
    pl1 = Placement(id="p1", artwork_id="a1", x_dmm=cm_to_dmm(100), y_dmm=cm_to_dmm(130))
    anchors1 = compute_anchor_points(pl1, single)
    assert len(anchors1) == 1
    assert anchors1[0].x_dmm == cm_to_dmm(125)
    # top = 130 + 40 = 170; drop = 4 + 3 = 7 => y = 163 cm
    assert anchors1[0].y_dmm == cm_to_dmm(163)
    assert anchors1[0].distance_from_top_edge_dmm == cm_to_dmm(7)

    dual = _make_artwork("a2", 80, 60, HangingType.DUAL_POINTS)
    pl2 = Placement(id="p2", artwork_id="a2", x_dmm=cm_to_dmm(200), y_dmm=cm_to_dmm(120))
    anchors2 = compute_anchor_points(pl2, dual)
    assert [(a.x_dmm, a.y_dmm) for a in anchors2] == [
        (cm_to_dmm(210), cm_to_dmm(176)),
        (cm_to_dmm(270), cm_to_dmm(176)),
    ]


def test_validate_wall_bounds_detects_out_of_bounds_baseboard_and_overlap() -> None:
    a1 = _make_artwork("a1", 60, 40)
    a2 = _make_artwork("a2", 60, 40)
    arts = {"a1": a1, "a2": a2}

    wall = Wall(
        id="w1",
        name="Muro",
        width_dmm=m_to_dmm(3),
        height_dmm=m_to_dmm(2.5),
        baseboard_height_dmm=cm_to_dmm(12),
        placements=[
            Placement(id="p1", artwork_id="a1", x_dmm=cm_to_dmm(20), y_dmm=cm_to_dmm(8)),
            Placement(id="p2", artwork_id="a2", x_dmm=cm_to_dmm(50), y_dmm=cm_to_dmm(20)),
            Placement(id="p3", artwork_id="a2", x_dmm=cm_to_dmm(260), y_dmm=cm_to_dmm(100)),
        ],
    )
    codes = {issue.code for issue in validate_wall_bounds(wall, arts)}
    assert codes == {"OVERLAPS_BASEBOARD", "ARTWORK_OVERLAP", "OUT_OF_WALL_BOUNDS"}


def test_snap_placement_aligns_to_eye_level_and_neighbor() -> None:
    a1 = _make_artwork("a1", 50, 40)
    arts = {"a1": a1}
    wall = Wall(
        id="w1",
        name="Muro",
        width_dmm=m_to_dmm(4),
        height_dmm=m_to_dmm(3),
        eye_level_dmm=cm_to_dmm(150),
        placements=[
            Placement(id="p1", artwork_id="a1", x_dmm=cm_to_dmm(50), y_dmm=cm_to_dmm(130)),
        ],
    )
    # Mover una segunda obra a y=131 cm (centro a 151 cm, dentro de tolerancia 2 cm)
    res = snap_placement(
        target_x_dmm=cm_to_dmm(174),
        target_y_dmm=cm_to_dmm(131),
        moving_artwork=a1,
        wall=wall,
        artworks_by_id=arts,
        tolerance_dmm=cm_to_dmm(2),
    )
    # Centro muro X = 200 cm => borde izq = 175 cm; eye_level = 150 => y = 130 cm
    assert res.x_dmm == cm_to_dmm(175)
    assert res.y_dmm == cm_to_dmm(130)
    assert {g.kind for g in res.guides} == {"wall_center_x", "eye_level_center"}


def test_align_and_distribute_horizontally() -> None:
    a1 = _make_artwork("a1", 40, 40)
    a2 = _make_artwork("a2", 60, 40)
    a3 = _make_artwork("a3", 40, 40)
    arts = {"a1": a1, "a2": a2, "a3": a3}
    placements = [
        Placement(id="p1", artwork_id="a1", x_dmm=cm_to_dmm(20), y_dmm=cm_to_dmm(100)),
        Placement(id="p2", artwork_id="a2", x_dmm=cm_to_dmm(120), y_dmm=cm_to_dmm(140)),
        Placement(
            id="p3",
            artwork_id="a3",
            x_dmm=cm_to_dmm(240),
            y_dmm=cm_to_dmm(120),
            locked=True,
        ),
    ]

    aligned = align_placements(placements, arts, "eye_level", eye_level_dmm=cm_to_dmm(150))
    assert aligned["p1"] == (cm_to_dmm(20), cm_to_dmm(130))
    assert aligned["p2"] == (cm_to_dmm(120), cm_to_dmm(130))
    # Bloqueada conserva posición original
    assert aligned["p3"] == (cm_to_dmm(240), cm_to_dmm(120))

    # Distribución equidistante entre p1 (x=20, w=40) y p3 (right=280): gap = 60 cm
    dist = distribute_horizontally(placements, arts)
    assert dist["p1"][0] == cm_to_dmm(20)
    assert dist["p2"][0] == cm_to_dmm(120)
    assert dist["p3"][0] == cm_to_dmm(240)

    # Distribución con separación fija de 15 cm
    fixed = distribute_horizontally(placements, arts, gap_dmm=cm_to_dmm(15))
    assert fixed["p1"][0] == cm_to_dmm(20)
    assert fixed["p2"][0] == cm_to_dmm(75)
    assert fixed["p3"][0] == cm_to_dmm(150)

    with pytest.raises(ValueError):
        align_placements(placements, arts, "eye_level")


def test_wall_dimension_report_outputs_distances_and_gaps() -> None:
    a1 = _make_artwork("a1", 50, 40)
    a2 = _make_artwork("a2", 50, 40)
    arts = {"a1": a1, "a2": a2}
    wall = Wall(
        id="w1",
        name="Muro Sur",
        width_dmm=cm_to_dmm(300),
        height_dmm=cm_to_dmm(250),
        placements=[
            Placement(id="p2", artwork_id="a2", x_dmm=cm_to_dmm(150), y_dmm=cm_to_dmm(130)),
            Placement(id="p1", artwork_id="a1", x_dmm=cm_to_dmm(50), y_dmm=cm_to_dmm(130)),
        ],
    )
    report = wall_dimension_report(wall, arts)
    assert [item.placement_id for item in report.items] == ["p1", "p2"]
    assert report.items[0].distance_from_left_wall_dmm == cm_to_dmm(50)
    assert report.items[1].distance_from_right_wall_dmm == cm_to_dmm(100)
    assert report.horizontal_gaps[0].gap_dmm == cm_to_dmm(50)
    assert placement_outer_rect(wall.placements[1], a1) == placement_image_rect(
        wall.placements[1], a1
    )
