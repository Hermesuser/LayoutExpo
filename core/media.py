"""Ingesta no destructiva de fotografías (JPEG, PNG, TIFF), perfiles ICC y caché de proxies."""

from __future__ import annotations

import hashlib
import io
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageCms, ImageOps, UnidentifiedImageError

ALLOWED_IMAGE_EXTENSIONS: frozenset[str] = frozenset({".jpg", ".jpeg", ".png", ".tif", ".tiff"})
_HASH_CHUNK_BYTES = 65_536
_SRGB_PROFILE = ImageCms.createProfile("sRGB")


class MediaImportError(ValueError):
    """Error al validar o procesar una fotografía local."""


@dataclass(frozen=True, slots=True)
class ImportedMedia:
    """Metadatos extraídos de una fotografía importada en modo solo lectura."""

    source_path: str
    sha256: str
    pixel_width: int
    pixel_height: int
    dpi_x: float | None
    dpi_y: float | None
    proxy_path: str
    icc_converted: bool


def compute_file_sha256(path: Path) -> str:
    """Calcula SHA-256 de un archivo leyendo por bloques sin cargarlo completo en RAM."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_HASH_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def _extract_dpi(info: Mapping[str | tuple[int, int], object]) -> tuple[float | None, float | None]:
    raw_dpi = info.get("dpi")
    if isinstance(raw_dpi, tuple) and len(raw_dpi) == 2:
        dx, dy = raw_dpi
        if isinstance(dx, int | float) and isinstance(dy, int | float) and dx > 0 and dy > 0:
            return (float(dx), float(dy))
    return (None, None)


def _convert_to_srgb_rgb(image: Image.Image) -> tuple[Image.Image, bool]:
    """Normaliza modo de color y convierte perfil ICC embebido a sRGB cuando existe."""
    icc_bytes = image.info.get("icc_profile")
    icc_converted = False

    # Normalizar paletas, 16-bit o canales alfa antes de convertir ICC
    working = image
    if working.mode in ("I;16", "I;16B", "I;16L", "I"):
        # Escalar imágenes TIFF de 16 bits a 8 bits de forma segura
        working = working.point(lambda px: px >> 8).convert("RGB")
    elif working.mode == "RGBA":
        background = Image.new("RGB", working.size, (255, 255, 255))
        background.paste(working, mask=working.getchannel("A"))
        working = background
    elif working.mode not in ("RGB", "L", "CMYK"):
        working = working.convert("RGB")

    if isinstance(icc_bytes, bytes) and icc_bytes:
        try:
            src_profile = ImageCms.ImageCmsProfile(io.BytesIO(icc_bytes))
            target_mode = "RGB"
            converted = ImageCms.profileToProfile(
                working,
                src_profile,
                _SRGB_PROFILE,
                renderingIntent=ImageCms.Intent.PERCEPTUAL,
                outputMode=target_mode,
            )
            if converted is not None:
                working = converted
                icc_converted = True
        except (ImageCms.PyCMSError, OSError, ValueError):
            pass

    if working.mode != "RGB":
        working = working.convert("RGB")
    return (working, icc_converted)


def import_image(
    source_path: Path,
    proxy_dir: Path,
    *,
    max_proxy_edge: int = 1600,
) -> ImportedMedia:
    """Importa un archivo JPEG/PNG/TIFF sin modificar el original y genera proxy sRGB."""
    if max_proxy_edge <= 0:
        raise ValueError("max_proxy_edge debe ser mayor que 0.")

    resolved = source_path.expanduser().resolve()
    if not resolved.is_file():
        raise MediaImportError(f"El archivo no existe o no es un fichero regular: '{source_path}'.")
    if resolved.suffix.lower() not in ALLOWED_IMAGE_EXTENSIONS:
        raise MediaImportError(
            f"Formato no soportado '{resolved.suffix}'. Permitidos: JPEG, PNG, TIFF."
        )

    sha256 = compute_file_sha256(resolved)
    proxy_dir.mkdir(parents=True, exist_ok=True)
    proxy_file = (proxy_dir / f"{sha256[:16]}.jpg").resolve()

    try:
        with Image.open(resolved) as raw_img:
            dpi_x, dpi_y = _extract_dpi(raw_img.info)
            oriented = ImageOps.exif_transpose(raw_img)
            pixel_width, pixel_height = oriented.size
            if pixel_width <= 0 or pixel_height <= 0:
                raise MediaImportError("La imagen tiene dimensiones inválidas.")
            rgb_img, icc_converted = _convert_to_srgb_rgb(oriented)
            rgb_img.thumbnail((max_proxy_edge, max_proxy_edge), Image.Resampling.LANCZOS)
            rgb_img.save(proxy_file, format="JPEG", quality=88, optimize=True)
    except (UnidentifiedImageError, OSError) as exc:
        raise MediaImportError(
            f"No se pudo decodificar la imagen '{resolved.name}': {exc}"
        ) from exc

    return ImportedMedia(
        source_path=str(resolved),
        sha256=sha256,
        pixel_width=pixel_width,
        pixel_height=pixel_height,
        dpi_x=dpi_x,
        dpi_y=dpi_y,
        proxy_path=str(proxy_file),
        icc_converted=icc_converted,
    )
