"""Punto de entrada principal de LayoutExpo (app nativa Dual-Screen o modo headless)."""

from __future__ import annotations

import argparse
import logging
import secrets
import sys

from werkzeug.serving import make_server

from desktop.launcher import get_default_data_dir, get_resource_root, launch_desktop_app
from server.app import create_app
from server.events import ProjectStateStore


def main(argv: list[str] | None = None) -> int:
    """Inicia LayoutExpo en ventana nativa OS o como servidor local de desarrollo."""
    parser = argparse.ArgumentParser(prog="layoutexpo", description="LayoutExpo Studio")
    parser.add_argument(
        "--browser",
        action="store_true",
        help="Ejecuta solo el servidor local e imprime la URL para navegador (desarrollo).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=0,
        help="Puerto local loopback cuando se usa --browser (0 = efímero).",
    )
    parser.add_argument(
        "--check-bundle",
        action="store_true",
        help="Verifica recursos empaquetados y finaliza con código 0.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if args.check_bundle:
        ui_dir = get_resource_root() / "ui"
        if not (ui_dir / "studio" / "index.html").is_file():
            return 1
        if not (ui_dir / "projector" / "index.html").is_file():
            return 1
        return 0

    if args.browser:
        cache_root = get_default_data_dir()
        proxy_dir = cache_root / "proxies"
        proxy_dir.mkdir(parents=True, exist_ok=True)
        token = secrets.token_urlsafe(24)
        store = ProjectStateStore(proxy_dir=proxy_dir)
        app = create_app(store, session_token=token, ui_dir=get_resource_root() / "ui")
        server = make_server("127.0.0.1", args.port, app, threaded=True)
        port = server.server_port
        print(f"Estudio:   http://127.0.0.1:{port}/?token={token}", flush=True)
        print(f"Proyector: http://127.0.0.1:{port}/projector?token={token}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            server.shutdown()
        return 0

    launch_desktop_app()
    return 0


if __name__ == "__main__":
    sys.exit(main())
