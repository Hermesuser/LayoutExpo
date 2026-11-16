"""Exportación de planos técnicos acotados, lista de obra y cartelas en PDF vectorial."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Mapping
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm as rl_mm
from reportlab.pdfgen.canvas import Canvas

from core.geometry import PlacementDimensions, WallDimensionReport, wall_dimension_report
from core.project import Artwork, ExhibitionProject, MountingType, Wall
from core.units import DMM_PER_MM, format_metric

_PAGE_LANDSCAPE = landscape(A4)
_PAGE_PORTRAIT = A4


def _hex_to_color(hex_code: str, fallback: colors.Color) -> colors.Color:
    cleaned = hex_code.strip()
    if len(cleaned) == 7 and cleaned.startswith("#"):
        try:
            return colors.HexColor(cleaned)
        except ValueError:
            return fallback
    return fallback


def _draw_header(c: Canvas, page_w: float, page_h: float, title: str, subtitle: str) -> float:
    margin_x = 16 * rl_mm
    top_y = page_h - 14 * rl_mm
    c.setFillColor(colors.HexColor("#141416"))
    c.setFont("Helvetica-Bold", 13)
    c.drawString(margin_x, top_y, title)
    c.setFillColor(colors.HexColor("#52525B"))
    c.setFont("Helvetica", 9)
    c.drawString(margin_x, top_y - 5 * rl_mm, subtitle)
    c.setStrokeColor(colors.HexColor("#D4D4D8"))
    c.setLineWidth(0.5)
    c.line(margin_x, top_y - 8 * rl_mm, page_w - margin_x, top_y - 8 * rl_mm)
    return float(top_y - 11 * rl_mm)


def _draw_dimension_line(
    c: Canvas,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    label: str,
    *,
    vertical: bool = False,
) -> None:
    """Dibuja una cota técnica con remates y etiqueta centrada."""
    c.saveState()
    c.setStrokeColor(colors.HexColor("#27272A"))
    c.setFillColor(colors.HexColor("#18181B"))
    c.setLineWidth(0.55)
    c.line(x1, y1, x2, y2)

    tick = 1.6 * rl_mm
    if vertical:
        c.line(x1 - tick, y1, x1 + tick, y1)
        c.line(x2 - tick, y2, x2 + tick, y2)
    else:
        c.line(x1, y1 - tick, x1, y1 + tick)
        c.line(x2, y2 - tick, x2, y2 + tick)

    c.setFont("Helvetica", 6.8)
    mx = (x1 + x2) / 2.0
    my = (y1 + y2) / 2.0
    if vertical:
        c.drawString(mx + 1.8 * rl_mm, my - 1 * rl_mm, label)
    else:
        c.drawCentredString(mx, my + 1.5 * rl_mm, label)
    c.restoreState()


def _draw_anchor_crosshair(c: Canvas, cx: float, cy: float) -> None:
    r = 1.6 * rl_mm
    c.saveState()
    c.setStrokeColor(colors.HexColor("#B91C1C"))
    c.setLineWidth(0.75)
    c.circle(cx, cy, r, stroke=1, fill=0)
    c.line(cx - r * 1.4, cy, cx + r * 1.4, cy)
    c.line(cx, cy - r * 1.4, cx, cy + r * 1.4)
    c.restoreState()


def _draw_wall_elevation_page(
    c: Canvas,
    project: ExhibitionProject,
    wall: Wall,
    report: WallDimensionReport,
    artworks_by_id: dict[str, Artwork],
    proxy_paths: Mapping[str, Path],
) -> None:
    page_w, page_h = _PAGE_LANDSCAPE
    subtitle = (
        f"Muro: {wall.name} ({format_metric(wall.width_dmm)} × {format_metric(wall.height_dmm)})"
        f" · Eje visual: {format_metric(wall.eye_level_dmm)}"
    )
    if project.venue:
        subtitle += f" · Sede: {project.venue}"
    content_top = _draw_header(c, page_w, page_h, f"{project.title} — Plano Técnico", subtitle)

    margin_x = 18 * rl_mm
    table_height = 42 * rl_mm
    draw_bottom = 14 * rl_mm + table_height + 12 * rl_mm
    avail_w = page_w - 2 * margin_x
    avail_h = content_top - draw_bottom - 10 * rl_mm

    wall_w_pt = (wall.width_dmm / DMM_PER_MM) * rl_mm
    wall_h_pt = (wall.height_dmm / DMM_PER_MM) * rl_mm
    scale = min(avail_w / wall_w_pt, avail_h / wall_h_pt)

    scaled_w = wall_w_pt * scale
    scaled_h = wall_h_pt * scale
    origin_x = margin_x + (avail_w - scaled_w) / 2.0
    origin_y = draw_bottom + (avail_h - scaled_h) / 2.0

    def to_pt(dmm_val: int) -> float:
        return float((dmm_val / DMM_PER_MM) * float(rl_mm) * scale)

    # Muro base
    c.setFillColor(_hex_to_color(wall.wall_color_hex, colors.HexColor("#F4F3EF")))
    c.setStrokeColor(colors.HexColor("#18181B"))
    c.setLineWidth(1.0)
    c.rect(origin_x, origin_y, scaled_w, scaled_h, stroke=1, fill=1)

    # Zócalo
    if wall.baseboard_height_dmm > 0:
        bb_h = to_pt(wall.baseboard_height_dmm)
        c.setFillColor(colors.HexColor("#E4E4E7"))
        c.rect(origin_x, origin_y, scaled_w, bb_h, stroke=0, fill=1)

    # Línea de eje visual / horizonte
    eye_y = origin_y + to_pt(wall.eye_level_dmm)
    c.saveState()
    c.setStrokeColor(colors.HexColor("#0284C7"))
    c.setDash(4, 3)
    c.setLineWidth(0.65)
    c.line(origin_x, eye_y, origin_x + scaled_w, eye_y)
    c.setFont("Helvetica", 6.8)
    c.setFillColor(colors.HexColor("#0369A1"))
    c.drawString(origin_x + 2 * rl_mm, eye_y + 1.2 * rl_mm, format_metric(wall.eye_level_dmm))
    c.restoreState()

    # Obras + anclajes + cotas
    for idx, item in enumerate(report.items, start=1):
        art = artworks_by_id[item.artwork_id]
        ox = origin_x + to_pt(item.outer_rect.x)
        oy = origin_y + to_pt(item.outer_rect.y)
        ow = to_pt(item.outer_rect.width)
        oh = to_pt(item.outer_rect.height)

        if art.mounting_type in (MountingType.FRAMED, MountingType.POLYPTYCH_PART):
            c.setFillColor(_hex_to_color(art.frame.color_hex, colors.HexColor("#1C1C1E")))
            c.rect(ox, oy, ow, oh, stroke=1, fill=1)
            pp_x = ox + to_pt(art.frame.left_dmm)
            pp_y = oy + to_pt(art.frame.bottom_dmm)
            pp_w = ow - to_pt(art.frame.left_dmm + art.frame.right_dmm)
            pp_h = oh - to_pt(art.frame.top_dmm + art.frame.bottom_dmm)
            c.setFillColor(_hex_to_color(art.passepartout.color_hex, colors.HexColor("#F7F6F2")))
            c.rect(pp_x, pp_y, pp_w, pp_h, stroke=0, fill=1)
        else:
            c.setFillColor(colors.HexColor("#FFFFFF"))
            c.setStrokeColor(colors.HexColor("#18181B"))
            c.rect(ox, oy, ow, oh, stroke=1, fill=1)

        ix = origin_x + to_pt(item.image_rect.x)
        iy = origin_y + to_pt(item.image_rect.y)
        iw = to_pt(item.image_rect.width)
        ih = to_pt(item.image_rect.height)
        proxy_file = proxy_paths.get(art.id)
        if proxy_file is not None and proxy_file.is_file():
            c.drawImage(str(proxy_file), ix, iy, width=iw, height=ih, preserveAspectRatio=False)
        else:
            c.setFillColor(colors.HexColor("#D4D4D8"))
            c.rect(ix, iy, iw, ih, stroke=1, fill=1)

        for anchor in item.anchors:
            _draw_anchor_crosshair(
                c, origin_x + to_pt(anchor.x_dmm), origin_y + to_pt(anchor.y_dmm)
            )

        # Etiqueta numérica sobre la obra
        c.setFillColor(colors.HexColor("#18181B"))
        c.setFont("Helvetica-Bold", 7)
        c.drawCentredString(ox + ow / 2.0, oy - 3.5 * rl_mm, f"#{idx}")

        # Cota altura desde suelo (solo primera obra o cuando cambie para legibilidad)
        _draw_dimension_line(
            c,
            ox + ow / 2.0,
            origin_y,
            ox + ow / 2.0,
            oy,
            format_metric(item.distance_from_floor_dmm),
            vertical=True,
        )

    # Cotas horizontales: borde izquierdo -> primera obra -> gaps -> borde derecho
    dim_y = origin_y - 8 * rl_mm
    if report.items:
        first = report.items[0]
        _draw_dimension_line(
            c,
            origin_x,
            dim_y,
            origin_x + to_pt(first.outer_rect.x),
            dim_y,
            format_metric(first.distance_from_left_wall_dmm),
        )
        for pos in range(len(report.items) - 1):
            left_item = report.items[pos]
            right_item = report.items[pos + 1]
            gap = report.horizontal_gaps[pos]
            _draw_dimension_line(
                c,
                origin_x + to_pt(left_item.outer_rect.right),
                dim_y,
                origin_x + to_pt(right_item.outer_rect.x),
                dim_y,
                format_metric(gap.gap_dmm),
            )
        last = report.items[-1]
        _draw_dimension_line(
            c,
            origin_x + to_pt(last.outer_rect.right),
            dim_y,
            origin_x + scaled_w,
            dim_y,
            format_metric(last.distance_from_right_wall_dmm),
        )

    _draw_anchor_summary_table(c, margin_x, 12 * rl_mm, page_w - 2 * margin_x, report.items)
    c.showPage()


def _draw_anchor_summary_table(
    c: Canvas, x: float, y: float, width: float, items: tuple[PlacementDimensions, ...]
) -> None:
    c.saveState()
    c.setFont("Helvetica-Bold", 8)
    c.setFillColor(colors.HexColor("#18181B"))
    c.drawString(
        x, y + 36 * rl_mm, "Puntos de anclaje / perforación (desde esquina inferior izq.):"
    )

    c.setFont("Helvetica", 7.2)
    row_y = y + 31 * rl_mm
    for idx, item in enumerate(items[:8], start=1):
        coords = ", ".join(
            f"{a.label}: X={format_metric(a.x_dmm)} · Y={format_metric(a.y_dmm)} "
            f"(↓{format_metric(a.distance_from_top_edge_dmm)})"
            for a in item.anchors
        )
        base_txt = format_metric(item.distance_from_floor_dmm)
        c.drawString(x, row_y, f"#{idx} {item.title[:26]} — Base={base_txt} · {coords}")
        row_y -= 4.2 * rl_mm
    if len(items) > 8:
        c.drawString(x, row_y, f"... y {len(items) - 8} obra(s) más en la Lista de Obra.")
    c.restoreState()


def _draw_inventory_pages(
    c: Canvas, project: ExhibitionProject, artworks_by_id: dict[str, Artwork]
) -> None:
    page_w, page_h = _PAGE_PORTRAIT
    margin_x = 16 * rl_mm
    y = _draw_header(
        c,
        page_w,
        page_h,
        f"{project.title} — Lista de Obra y Montaje",
        f"Curaduría: {project.curator or '—'} · Sede: {project.venue or '—'}",
    )

    c.setFont("Helvetica-Bold", 8)
    cols = [margin_x, margin_x + 10 * rl_mm, margin_x + 64 * rl_mm, margin_x + 105 * rl_mm]
    c.drawString(cols[0], y, "#")
    c.drawString(cols[1], y, "Título / Autor")
    c.drawString(cols[2], y, "Muro")
    c.drawString(cols[3], y, "Exterior · Base · Anclajes")
    y -= 5 * rl_mm

    c.setFont("Helvetica", 7.8)
    counter = 0
    for wall in project.walls:
        report = wall_dimension_report(wall, artworks_by_id)
        for item in report.items:
            counter += 1
            if y < 22 * rl_mm:
                c.showPage()
                y = _draw_header(c, page_w, page_h, f"{project.title} — Lista de Obra (cont.)", "")
                c.setFont("Helvetica", 7.8)

            art = artworks_by_id[item.artwork_id]
            ow, oh = art.outer_size_dmm()
            anchor_txt = "; ".join(
                f"({format_metric(a.x_dmm)}, {format_metric(a.y_dmm)})" for a in item.anchors
            )
            c.drawString(cols[0], y, f"{counter}")
            title_author = f"{art.title[:26]} — {art.author[:18] or 'S/A'}"
            c.drawString(cols[1], y, title_author)
            c.drawString(cols[2], y, wall.name[:20])
            base_txt = format_metric(item.distance_from_floor_dmm)
            c.drawString(
                cols[3],
                y,
                f"{format_metric(ow)}×{format_metric(oh)} · Base {base_txt} · {anchor_txt}",
            )
            y -= 5.2 * rl_mm
    c.showPage()


def _draw_labels_pages(c: Canvas, project: ExhibitionProject) -> None:
    page_w, page_h = _PAGE_PORTRAIT
    margin_x = 16 * rl_mm
    top_y = _draw_header(
        c, page_w, page_h, f"{project.title} — Cartelas de Sala", "Guías de corte a tamaño real"
    )

    card_w = (page_w - 2 * margin_x - 8 * rl_mm) / 2.0
    card_h = 52 * rl_mm
    gap = 8 * rl_mm

    col = 0
    row_y = top_y - card_h - 4 * rl_mm
    for art in project.artworks:
        if row_y < 16 * rl_mm:
            c.showPage()
            top_y = _draw_header(c, page_w, page_h, f"{project.title} — Cartelas (cont.)", "")
            row_y = top_y - card_h - 4 * rl_mm
            col = 0

        cx = margin_x + col * (card_w + gap)
        c.setStrokeColor(colors.HexColor("#D4D4D8"))
        c.setDash(2, 2)
        c.rect(cx, row_y, card_w, card_h, stroke=1, fill=0)
        c.setDash()

        pad = 6 * rl_mm
        c.setFillColor(colors.HexColor("#18181B"))
        c.setFont("Helvetica-Bold", 10)
        c.drawString(cx + pad, row_y + card_h - 11 * rl_mm, art.author or "Autor por definir")
        c.setFont("Helvetica-Oblique", 10)
        year_suffix = f", {art.year}" if art.year else ""
        c.drawString(cx + pad, row_y + card_h - 18 * rl_mm, f"{art.title}{year_suffix}"[:42])
        c.setFillColor(colors.HexColor("#52525B"))
        c.setFont("Helvetica", 8.5)
        c.drawString(
            cx + pad, row_y + card_h - 26 * rl_mm, (art.medium or art.mounting_type.value)[:46]
        )
        c.drawString(
            cx + pad,
            row_y + card_h - 32 * rl_mm,
            f"Imagen: {format_metric(art.image_width_dmm)} × {format_metric(art.image_height_dmm)}",
        )

        col += 1
        if col >= 2:
            col = 0
            row_y -= card_h + gap
    c.showPage()


def export_exhibition_pdf(
    project: ExhibitionProject,
    output_path: Path,
    *,
    proxy_paths: Mapping[str, Path] | None = None,
    include_elevations: bool = True,
    include_inventory: bool = True,
    include_labels: bool = True,
) -> Path:
    """Genera el PDF técnico vectorial de forma atómica y retorna la ruta final."""
    if not (include_elevations or include_inventory or include_labels):
        raise ValueError("Debe seleccionarse al menos una sección para exportar el PDF.")

    target = output_path.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    proxies = proxy_paths or {}
    artworks_by_id = project.artworks_by_id()

    fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".pdf.tmp", dir=target.parent)
    os.close(fd)
    tmp_path = Path(tmp_name)

    try:
        canvas = Canvas(str(tmp_path), pagesize=_PAGE_LANDSCAPE)
        canvas.setTitle(f"{project.title} — Montaje LayoutExpo")
        canvas.setAuthor(project.curator or "LayoutExpo")

        if include_elevations:
            canvas.setPageSize(_PAGE_LANDSCAPE)
            for wall in project.walls:
                report = wall_dimension_report(wall, artworks_by_id)
                _draw_wall_elevation_page(canvas, project, wall, report, artworks_by_id, proxies)

        if include_inventory:
            canvas.setPageSize(_PAGE_PORTRAIT)
            _draw_inventory_pages(canvas, project, artworks_by_id)

        if include_labels:
            canvas.setPageSize(_PAGE_PORTRAIT)
            _draw_labels_pages(canvas, project)

        canvas.save()
        os.replace(tmp_path, target)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise

    return target
