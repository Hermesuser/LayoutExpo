"""Pruebas unitarias para plantillas predefinidas y personalización de muros (V2.3)."""

from __future__ import annotations

from core import (
    Artwork,
    ExhibitionProject,
    FrameSpec,
    PassepartoutSpec,
    Wall,
    apply_layout_preset,
    list_layout_presets,
    project_from_dict,
    project_to_dict,
)
from core.units import cm_to_dmm


def test_list_layout_presets_contains_all_six_templates_with_valid_preview() -> None:
    presets = list_layout_presets()
    ids = {p["id"] for p in presets}
    assert ids == {
        "diamante_clasico",
        "salon_escalonado",
        "asimetrico_diagonal",
        "reticula_compacta",
        "triptico_clasico",
        "linea_museo",
    }
    for p in presets:
        preview = p["preview"]
        assert isinstance(preview, dict)
        assert preview["width"] > 0
        assert preview["height"] > 0
        assert len(preview["rects"]) == p["slot_count"]


def test_apply_all_presets_on_empty_wall_creates_non_overlapping_samples() -> None:
    for preset in list_layout_presets():
        wall = Wall(id="w1", name="Principal", width_dmm=cm_to_dmm(400), height_dmm=cm_to_dmm(280))
        proj = ExhibitionProject(title="Base", artworks=[], walls=[wall])
        res = apply_layout_preset(proj, wall_id="w1", preset_id=str(preset["id"]))

        assert len(proj.walls[0].placements) == 0  # Inmutabilidad
        new_wall = res.project.walls[0]
        assert len(new_wall.placements) == preset["slot_count"]
        arts = res.project.artworks_by_id()
        boxes: list[tuple[int, int, int, int]] = []
        for pl in new_wall.placements:
            ow, oh = arts[pl.artwork_id].outer_size_dmm()
            boxes.append((pl.x_dmm, pl.y_dmm, pl.x_dmm + ow, pl.y_dmm + oh))
        for i in range(len(boxes)):
            ax1, ay1, ax2, ay2 = boxes[i]
            for j in range(i + 1, len(boxes)):
                bx1, by1, bx2, by2 = boxes[j]
                overlaps = not (ax2 <= bx1 or bx2 <= ax1 or ay2 <= by1 or by2 <= ay1)
                assert not overlaps, f"Solapamiento en preset {preset['id']}"


def test_apply_preset_uses_existing_artworks_and_preserves_aspect_ratio() -> None:
    wall = Wall(id="w1", name="Muro", width_dmm=cm_to_dmm(400), height_dmm=cm_to_dmm(280))
    a1 = Artwork(
        id="a1",
        title="Panorámica",
        image_width_dmm=cm_to_dmm(80),
        image_height_dmm=cm_to_dmm(40),
        frame=FrameSpec.uniform(0),
        passepartout=PassepartoutSpec.uniform(0),
        is_anchor=True,
    )
    proj = ExhibitionProject(title="Foto", artworks=[a1], walls=[wall])

    res = apply_layout_preset(
        proj,
        wall_id="w1",
        preset_id="triptico_clasico",
        preserve_aspect=True,
        create_placeholders=True,
    )
    assert res.used_existing == 1
    assert res.created_samples == 2
    updated_a1 = res.project.artworks_by_id()["a1"]
    assert abs((updated_a1.image_width_dmm / updated_a1.image_height_dmm) - 2.0) < 0.05


def test_wall_texture_and_image_fields_roundtrip() -> None:
    wall = Wall(
        id="w1",
        name="Hormigón",
        width_dmm=cm_to_dmm(400),
        height_dmm=cm_to_dmm(300),
        wall_texture_preset="concrete",
        wall_image_path="assets/muro.jpg",
        wall_image_sha256="abcdef1234567890",
        wall_image_fit="tile",
        wall_image_opacity=0.65,
    )
    proj = ExhibitionProject(title="Textura", artworks=[], walls=[wall])
    restored = project_from_dict(project_to_dict(proj))
    rw = restored.walls[0]
    assert rw.wall_texture_preset == "concrete"
    assert rw.wall_image_sha256 == "abcdef1234567890"
    assert rw.wall_image_fit == "tile"
    assert rw.wall_image_opacity == 0.65
