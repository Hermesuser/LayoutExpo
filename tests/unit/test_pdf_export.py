"""Pruebas unitarias para core.pdf_export."""

from pathlib import Path

import pytest
from PIL import Image

from core.pdf_export import export_exhibition_pdf
from core.project import (
    Artwork,
    ExhibitionProject,
    FrameSpec,
    HangingHardware,
    HangingType,
    MountingType,
    PassepartoutSpec,
    Placement,
    Wall,
)
from core.units import cm_to_dmm, m_to_dmm


def test_export_exhibition_pdf_creates_valid_vector_document(tmp_path: Path) -> None:
    proxy_img = tmp_path / "proxy_a1.jpg"
    Image.new("RGB", (400, 300), (90, 110, 130)).save(proxy_img, format="JPEG")

    a1 = Artwork(
        id="a1",
        title="Cordillera 01",
        author="M. Lagos",
        year="2025",
        medium="Plata sobre gelatina",
        image_width_dmm=cm_to_dmm(40),
        image_height_dmm=cm_to_dmm(30),
        mounting_type=MountingType.FRAMED,
        frame=FrameSpec.uniform(cm_to_dmm(2)),
        passepartout=PassepartoutSpec.uniform(cm_to_dmm(5)),
        hardware=HangingHardware(hanging_type=HangingType.DUAL_POINTS),
    )
    a2 = Artwork(
        id="a2",
        title="Borde Costero",
        author="M. Lagos",
        year="2026",
        image_width_dmm=cm_to_dmm(60),
        image_height_dmm=cm_to_dmm(40),
        mounting_type=MountingType.DIRECT,
    )
    wall = Wall(
        id="w1",
        name="Muro Principal",
        width_dmm=m_to_dmm(4),
        height_dmm=m_to_dmm(3),
        baseboard_height_dmm=cm_to_dmm(10),
        placements=[
            Placement(id="p1", artwork_id="a1", x_dmm=cm_to_dmm(60), y_dmm=cm_to_dmm(128)),
            Placement(id="p2", artwork_id="a2", x_dmm=cm_to_dmm(150), y_dmm=cm_to_dmm(130)),
        ],
    )
    project = ExhibitionProject(
        title="Horizontes",
        curator="C. Fernández",
        venue="Galería Sur",
        artworks=[a1, a2],
        walls=[wall],
    )

    out_pdf = tmp_path / "salida" / "montaje.pdf"
    result = export_exhibition_pdf(project, out_pdf, proxy_paths={"a1": proxy_img})
    assert result == out_pdf.resolve()
    raw = out_pdf.read_bytes()
    assert raw.startswith(b"%PDF-")
    assert len(raw) > 2000


def test_export_requires_at_least_one_section(tmp_path: Path) -> None:
    project = ExhibitionProject(title="Vacía")
    with pytest.raises(ValueError):
        export_exhibition_pdf(
            project,
            tmp_path / "empty.pdf",
            include_elevations=False,
            include_inventory=False,
            include_labels=False,
        )
