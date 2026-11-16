"""Arranque nativo Dual-Screen (Estudio + Proyector) para macOS y Windows 11."""

from __future__ import annotations

import ctypes
import logging
import os
import secrets
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any

import webview
from werkzeug.serving import make_server

from desktop.displays import DisplayInfo, list_displays, pick_projector_display
from server.app import ProjectorWindowController, create_app
from server.events import ProjectStateStore

logger = logging.getLogger(__name__)


def _enable_windows_high_dpi() -> None:
    """Activa Per-Monitor v2 High-DPI en Windows 11 para nitidez exacta en proyector."""
    if sys.platform != "win32":
        return
    try:
        user32 = getattr(ctypes, "windll", None)
        if user32 is not None:
            # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4
            user32.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except Exception as exc:
        logger.warning("No se pudo activar High-DPI en Windows: %s", exc)


class NativeWindowController(ProjectorWindowController):
    """Gestiona la ventana secundaria fullscreen del proyector y los diálogos del SO."""

    def __init__(self, session_token: str, base_url: str = "") -> None:
        self.base_url = base_url
        self._token = session_token
        self._lock = threading.Lock()
        self.studio_window: Any = None
        self.projector_window: Any = None
        self._active_display: DisplayInfo | None = None

    def list_displays(self) -> list[dict[str, object]]:
        return [
            {
                "index": d.index,
                "name": d.name,
                "x": d.x,
                "y": d.y,
                "width": d.width,
                "height": d.height,
                "is_primary": d.is_primary,
            }
            for d in list_displays()
        ]

    def open_projector(
        self, display_index: int | None = None, fullscreen: bool | None = None
    ) -> dict[str, object]:
        displays = list_displays()
        target: DisplayInfo | None = None
        if display_index is not None and 0 <= display_index < len(displays):
            target = displays[display_index]
        else:
            target = pick_projector_display(displays)

        # Seguridad pantalla única: si no hay 2ª pantalla externa, abrir ventana móvil en vez
        # de cubrir la pantalla principal del usuario con un fullscreen negro sin bordes.
        use_fullscreen = (
            fullscreen
            if fullscreen is not None
            else bool(target is not None and not target.is_primary)
        )

        url = f"{self.base_url}/projector?token={self._token}"
        with self._lock:
            if self.projector_window is not None:
                try:
                    self.projector_window.show()
                    return self.status()
                except Exception:
                    self.projector_window = None

            kwargs: dict[str, Any] = {
                "title": "LayoutExpo — Proyector en Sala",
                "url": url,
                "frameless": use_fullscreen,
                "background_color": "#000000",
                "fullscreen": use_fullscreen,
            }
            if target is not None:
                if use_fullscreen:
                    kwargs["x"] = target.x
                    kwargs["y"] = target.y
                    kwargs["width"] = target.width
                    kwargs["height"] = target.height
                else:
                    kwargs["width"] = min(1120, max(760, target.width - 140))
                    kwargs["height"] = min(720, max(520, target.height - 160))

            win = webview.create_window(**kwargs)

            if win is not None:

                def _on_closed() -> None:
                    with self._lock:
                        if self.projector_window is win:
                            self.projector_window = None
                            self._active_display = None

                try:
                    win.events.closed += _on_closed
                except Exception as exc:
                    logger.debug("No se pudo registrar callback de cierre del proyector: %s", exc)
                self.projector_window = win
                self._active_display = target
        return self.status()

    def close_projector(self) -> dict[str, object]:
        with self._lock:
            if self.projector_window is not None:
                try:
                    self.projector_window.destroy()
                except Exception as exc:
                    logger.debug("Ventana proyector ya cerrada al destruir: %s", exc)
                self.projector_window = None
                self._active_display = None
        return self.status()

    def status(self) -> dict[str, object]:
        return {
            "projector_open": self.projector_window is not None,
            "display_index": self._active_display.index if self._active_display else None,
            "display_name": self._active_display.name if self._active_display else None,
        }

    def choose_images(self) -> list[str]:
        win = self.studio_window
        if win is None:
            return []
        result = win.create_file_dialog(
            webview.FileDialog.OPEN,
            allow_multiple=True,
            file_types=("Imágenes (*.jpg;*.jpeg;*.png;*.tif;*.tiff)",),
        )
        return list(result) if result else []

    def choose_open_project(self) -> str | None:
        win = self.studio_window
        if win is None:
            return None
        result = win.create_file_dialog(
            webview.FileDialog.OPEN,
            allow_multiple=False,
            file_types=("Proyecto LayoutExpo (*.layoutexpo;*.json)",),
        )
        return str(result[0]) if result else None

    def choose_save_project(self, default_name: str = "exposicion.layoutexpo") -> str | None:
        win = self.studio_window
        if win is None:
            return None
        result = win.create_file_dialog(
            webview.FileDialog.SAVE,
            save_filename=default_name,
            file_types=("Proyecto LayoutExpo (*.layoutexpo)",),
        )
        chosen = (
            str(result[0])
            if isinstance(result, list | tuple) and result
            else (str(result) if result else None)
        )
        if chosen and not chosen.lower().endswith((".layoutexpo", ".json")):
            chosen = f"{chosen}.layoutexpo"
        return chosen

    def choose_save_pdf(self, default_name: str = "montaje_expo.pdf") -> str | None:
        win = self.studio_window
        if win is None:
            return None
        result = win.create_file_dialog(
            webview.FileDialog.SAVE,
            save_filename=default_name,
            file_types=("Documento PDF (*.pdf)",),
        )
        chosen = (
            str(result[0])
            if isinstance(result, list | tuple) and result
            else (str(result) if result else None)
        )
        if chosen and not chosen.lower().endswith(".pdf"):
            chosen = f"{chosen}.pdf"
        return chosen


class DesktopJsApi:
    """Adaptador de compatibilidad hacia diálogos nativos de archivo del SO."""

    def __init__(self, controller: NativeWindowController) -> None:
        self._controller = controller

    def choose_images(self) -> list[str]:
        return self._controller.choose_images()

    def choose_open_project(self) -> str | None:
        return self._controller.choose_open_project()

    def choose_save_project(self, default_name: str = "exposicion.layoutexpo") -> str | None:
        return self._controller.choose_save_project(default_name)

    def choose_save_pdf(self, default_name: str = "montaje_expo.pdf") -> str | None:
        return self._controller.choose_save_pdf(default_name)


def get_resource_root() -> Path:
    """Devuelve la raíz de recursos tanto en código fuente como en bundle PyInstaller."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(str(sys._MEIPASS)).resolve()
    return Path(__file__).resolve().parent.parent


def get_default_data_dir() -> Path:
    """Devuelve el directorio de caché/proxies estándar por sistema operativo."""
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "LayoutExpo"
    if sys.platform == "win32":
        local_app = os.environ.get("LOCALAPPDATA")
        base = Path(local_app) if local_app else Path(tempfile.gettempdir())
        return base / "LayoutExpo"
    return Path.home() / ".local" / "share" / "LayoutExpo"


def launch_desktop_app(data_dir: Path | None = None) -> None:
    """Inicia el servidor local loopback y abre la ventana nativa del Estudio."""
    _enable_windows_high_dpi()
    cache_root = data_dir or get_default_data_dir()
    proxy_dir = cache_root / "proxies"
    proxy_dir.mkdir(parents=True, exist_ok=True)
    ui_dir = get_resource_root() / "ui"

    token = secrets.token_urlsafe(32)
    store = ProjectStateStore(proxy_dir=proxy_dir)
    controller = NativeWindowController(session_token=token)
    app = create_app(
        store,
        session_token=token,
        ui_dir=ui_dir,
        window_controller=controller,
        dialog_controller=controller,
    )
    http_server = make_server("127.0.0.1", 0, app, threaded=True)
    port = http_server.server_port
    base_url = f"http://127.0.0.1:{port}"
    controller.base_url = base_url

    server_thread = threading.Thread(target=http_server.serve_forever, daemon=True)
    server_thread.start()

    try:
        icon_file = ui_dir / "assets" / "icon.png"
        controller.studio_window = webview.create_window(
            title="LayoutExpo — Estudio de Montaje",
            url=f"{base_url}/?token={token}",
            width=1400,
            height=900,
            min_size=(1024, 680),
            background_color="#1A1A1C",
        )
        webview.start(
            debug=False,
            icon=str(icon_file) if icon_file.is_file() else None,
        )
    finally:
        controller.close_projector()
        http_server.shutdown()


if __name__ == "__main__":
    launch_desktop_app()
