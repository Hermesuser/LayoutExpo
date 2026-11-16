"""Detección de pantallas y selección automática de proyector externo."""

from __future__ import annotations

from dataclasses import dataclass

import webview


@dataclass(frozen=True, slots=True)
class DisplayInfo:
    """Descripción normalizada de una pantalla conectada al equipo."""

    index: int
    name: str
    x: int
    y: int
    width: int
    height: int
    is_primary: bool


def list_displays() -> list[DisplayInfo]:
    """Enumera pantallas conectadas usando la capa nativa de pywebview."""
    try:
        screens = webview.screens
    except Exception:
        screens = []

    displays: list[DisplayInfo] = []
    for idx, screen in enumerate(screens):
        x = int(getattr(screen, "x", 0))
        y = int(getattr(screen, "y", 0))
        width = int(getattr(screen, "width", 1920))
        height = int(getattr(screen, "height", 1080))
        name = str(getattr(screen, "title", "") or f"Pantalla {idx + 1}")
        displays.append(
            DisplayInfo(
                index=idx,
                name=name,
                x=x,
                y=y,
                width=width,
                height=height,
                is_primary=(idx == 0),
            )
        )
    return displays


def pick_projector_display(displays: list[DisplayInfo]) -> DisplayInfo | None:
    """Selecciona la primera pantalla secundaria (proyector), o None si solo hay una."""
    for disp in displays:
        if not disp.is_primary:
            return disp
    return displays[0] if displays else None
