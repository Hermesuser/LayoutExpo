"""Pruebas unitarias para core.media (ingesta no destructiva JPEG/PNG/TIFF)."""

from pathlib import Path

import pytest
from PIL import Image, ImageCms

from core.media import MediaImportError, compute_file_sha256, import_image


def test_import_jpeg_png_tiff_non_destructive_and_exif(tmp_path: Path) -> None:
    proxy_dir = tmp_path / "proxies"

    # JPEG con orientación EXIF rotada (tag 274 = 6 => 90° CW => ancho/alto se invierten)
    jpg_path = tmp_path / "portrait.jpg"
    img = Image.new("RGB", (400, 200), (180, 90, 40))
    exif = img.getexif()
    exif[274] = 6
    img.save(jpg_path, format="JPEG", exif=exif, dpi=(300, 300))
    orig_hash = compute_file_sha256(jpg_path)

    imported_jpg = import_image(jpg_path, proxy_dir, max_proxy_edge=300)
    assert imported_jpg.sha256 == orig_hash
    assert (imported_jpg.pixel_width, imported_jpg.pixel_height) == (200, 400)
    assert imported_jpg.dpi_x == pytest.approx(300.0, abs=0.5)
    assert Path(imported_jpg.proxy_path).is_file()
    # Original intacto
    assert compute_file_sha256(jpg_path) == orig_hash

    # PNG RGBA -> proxy RGB limpio
    png_path = tmp_path / "alpha.png"
    Image.new("RGBA", (320, 240), (10, 20, 30, 128)).save(png_path, format="PNG")
    imported_png = import_image(png_path, proxy_dir)
    assert (imported_png.pixel_width, imported_png.pixel_height) == (320, 240)
    assert Path(imported_png.proxy_path).is_file()

    # TIFF con perfil ICC embebido
    tiff_path = tmp_path / "master.tif"
    srgb_bytes = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    Image.new("RGB", (500, 350), (40, 120, 200)).save(
        tiff_path, format="TIFF", icc_profile=srgb_bytes
    )
    imported_tiff = import_image(tiff_path, proxy_dir)
    assert imported_tiff.icc_converted is True
    assert (imported_tiff.pixel_width, imported_tiff.pixel_height) == (500, 350)


def test_import_rejects_unsupported_and_missing_files(tmp_path: Path) -> None:
    proxy_dir = tmp_path / "proxies"
    bad_ext = tmp_path / "notes.txt"
    bad_ext.write_text("no soy imagen", encoding="utf-8")

    with pytest.raises(MediaImportError):
        import_image(bad_ext, proxy_dir)
    with pytest.raises(MediaImportError):
        import_image(tmp_path / "no_existe.jpg", proxy_dir)
