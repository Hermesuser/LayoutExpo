"""Pruebas unitarias para core.project y persistencia atómica."""

import json
from pathlib import Path

import pytest

from core.project import (
    Artwork,
    ExhibitionProject,
    FrameSpec,
    HangingHardware,
    HangingType,
    MountingType,
    PassepartoutSpec,
    Placement,
    ProjectorCalibration,
    ProjectValidationError,
    Wall,
    load_project,
    project_from_dict,
    save_project_atomic,
)
from core.units import cm_to_dmm, m_to_dmm


def _sample_project() -> ExhibitionProject:
    framed = Artwork(
        id="art-1",
        title="Atacama 01",
        author="C. Fernández",
        year="2026",
        medium="Inyección de tinta sobre algodón",
        source_path="/fotos/atacama_01.tif",
        image_width_dmm=cm_to_dmm(40),
        image_height_dmm=cm_to_dmm(30),
        mounting_type=MountingType.FRAMED,
        frame=FrameSpec.uniform(cm_to_dmm(2)),
        passepartout=PassepartoutSpec(
            top_dmm=cm_to_dmm(5),
            bottom_dmm=cm_to_dmm(6),
            left_dmm=cm_to_dmm(5),
            right_dmm=cm_to_dmm(5),
        ),
        hardware=HangingHardware(
            hanging_type=HangingType.DUAL_POINTS,
            offset_from_top_dmm=cm_to_dmm(3),
            lateral_inset_dmm=cm_to_dmm(5),
        ),
    )
    direct = Artwork(
        id="art-2",
        title="Salar Dibond",
        image_width_dmm=cm_to_dmm(60),
        image_height_dmm=cm_to_dmm(40),
        mounting_type=MountingType.DIRECT,
        frame=FrameSpec.uniform(cm_to_dmm(2)),  # debe ignorarse en montaje directo
    )
    wall = Wall(
        id="wall-a",
        name="Muro Norte",
        width_dmm=m_to_dmm(5),
        height_dmm=m_to_dmm(3),
        baseboard_height_dmm=cm_to_dmm(10),
        placements=[
            Placement(id="pl-1", artwork_id="art-1", x_dmm=cm_to_dmm(80), y_dmm=cm_to_dmm(127)),
            Placement(id="pl-2", artwork_id="art-2", x_dmm=cm_to_dmm(180), y_dmm=cm_to_dmm(130)),
        ],
    )
    return ExhibitionProject(
        title="Territorios Neutros",
        curator="Curaduría Test",
        venue="Sala 1",
        artworks=[framed, direct],
        walls=[wall],
    )


def test_outer_size_respects_mounting_type() -> None:
    proj = _sample_project()
    framed, direct = proj.artworks
    # 40 + 5+5 (pp) + 2+2 (frame) = 54 cm; 30 + 5+6 (pp) + 2+2 (frame) = 45 cm
    assert framed.outer_size_dmm() == (cm_to_dmm(54), cm_to_dmm(45))
    assert framed.image_origin_offset_dmm() == (cm_to_dmm(7), cm_to_dmm(8))
    # Montaje directo ignora marco y passepartout
    assert direct.outer_size_dmm() == (cm_to_dmm(60), cm_to_dmm(40))
    assert direct.image_origin_offset_dmm() == (0, 0)


def test_atomic_save_and_load_roundtrip(tmp_path: Path) -> None:
    project = _sample_project()
    target = tmp_path / "expo.layoutexpo"
    save_project_atomic(project, target)
    assert target.exists()

    loaded = load_project(target)
    assert loaded.title == project.title
    assert len(loaded.artworks) == 2
    assert loaded.walls[0].placements[0].x_dmm == cm_to_dmm(80)
    assert loaded.walls[0].calibration.guide_color == "cyan"


def test_validation_rejects_invalid_schema_and_orphan_placements(tmp_path: Path) -> None:
    bad_file = tmp_path / "bad.layoutexpo"
    bad_file.write_text(json.dumps({"schema_version": 99, "title": "X"}), encoding="utf-8")
    with pytest.raises(ProjectValidationError):
        load_project(bad_file)

    with pytest.raises(ProjectValidationError):
        project_from_dict(
            {
                "schema_version": 1,
                "title": "Test",
                "artworks": [],
                "walls": [
                    {
                        "id": "w1",
                        "name": "Muro",
                        "width_dmm": 30000,
                        "height_dmm": 25000,
                        "placements": [
                            {"id": "p1", "artwork_id": "missing", "x_dmm": 0, "y_dmm": 0}
                        ],
                    }
                ],
            }
        )


def test_validation_rejects_duplicates_and_bad_calibration() -> None:
    art = Artwork(id="a1", title="A", image_width_dmm=1000, image_height_dmm=1000)
    with pytest.raises(ProjectValidationError):
        ExhibitionProject(title="Dup", artworks=[art, art])

    with pytest.raises(ProjectValidationError):
        ProjectorCalibration(ghost_opacity=1.5)
