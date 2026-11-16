"""Aplicación Flask local (127.0.0.1) con token efímero, CSP estricta y SSE para proyector."""

from __future__ import annotations

import hmac
import io
import json
import queue
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Protocol, cast

from flask import Flask, Response, jsonify, request, send_file, send_from_directory
from werkzeug.utils import secure_filename

from core.curation import CurationScope, reorganize_exhibition
from core.geometry import AlignMode, align_placements, distribute_horizontally, snap_placement
from core.media import ALLOWED_IMAGE_EXTENSIONS, MediaImportError, import_image
from core.pdf_export import export_exhibition_pdf
from core.presets import apply_layout_preset, list_layout_presets
from core.project import (
    ProjectValidationError,
    load_project,
    project_from_dict,
    project_to_dict,
    save_project_atomic,
)
from server.events import ProjectStateStore

_CSP_HEADER = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'none'"
)


class ProjectorWindowController(Protocol):
    """Contrato desacoplado para controlar pantallas y ventana del proyector."""

    def list_displays(self) -> list[dict[str, object]]: ...
    def open_projector(
        self, display_index: int | None = None, fullscreen: bool | None = None
    ) -> dict[str, object]: ...
    def close_projector(self) -> dict[str, object]: ...
    def status(self) -> dict[str, object]: ...


class NativeDialogController(Protocol):
    """Contrato desacoplado para abrir diálogos nativos de archivo del SO."""

    def choose_images(self) -> list[str]: ...
    def choose_open_project(self) -> str | None: ...
    def choose_save_project(self, default_name: str = "exposicion.layoutexpo") -> str | None: ...
    def choose_save_pdf(self, default_name: str = "montaje_expo.pdf") -> str | None: ...


def _is_token_valid(expected_token: str) -> bool:
    provided = request.headers.get("X-LayoutExpo-Token") or request.args.get("token") or ""
    return bool(provided) and hmac.compare_digest(provided, expected_token)


def _json_error(message: str, status_code: int = 400) -> tuple[Response, int]:
    return jsonify({"error": message}), status_code


def create_app(
    store: ProjectStateStore,
    *,
    session_token: str,
    ui_dir: Path | None = None,
    window_controller: ProjectorWindowController | None = None,
    dialog_controller: NativeDialogController | None = None,
) -> Flask:
    """Construye la aplicación Flask autenticada para Estudio y Proyector."""
    app = Flask(__name__, static_folder=None)
    resolved_ui = ui_dir.resolve() if ui_dir else (Path(__file__).resolve().parent.parent / "ui")

    @app.after_request
    def _apply_security_headers(response: Response) -> Response:
        response.headers["Content-Security-Policy"] = _CSP_HEADER
        response.headers["X-Content-Type-Options"] = "nosniff"
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.before_request
    def _require_auth_on_api() -> tuple[Response, int] | None:
        if request.path.startswith("/api/") and not _is_token_valid(session_token):
            return _json_error("Token de sesión inválido o ausente.", 401)
        return None

    @app.get("/")
    def serve_studio() -> Response:
        studio_index = resolved_ui / "studio" / "index.html"
        if studio_index.is_file():
            return send_file(studio_index)
        return Response("<h1>LayoutExpo Studio</h1>", mimetype="text/html")

    @app.get("/projector")
    def serve_projector() -> Response:
        proj_index = resolved_ui / "projector" / "index.html"
        if proj_index.is_file():
            return send_file(proj_index)
        return Response("<h1>LayoutExpo Projector</h1>", mimetype="text/html")

    @app.get("/ui/<path:asset_path>")
    def serve_ui_asset(asset_path: str) -> Response | tuple[Response, int]:
        if not resolved_ui.is_dir():
            return _json_error("UI no disponible.", 404)
        return send_from_directory(resolved_ui, asset_path)

    @app.get("/api/health")
    def api_health() -> Response:
        return jsonify({"status": "ok", "revision": store.revision})

    @app.get("/api/capabilities")
    def api_capabilities() -> Response:
        return jsonify(
            {
                "native_dialogs": dialog_controller is not None,
                "native_projector": window_controller is not None,
            }
        )

    @app.get("/api/project")
    def api_get_project() -> Response:
        return jsonify(store.snapshot_payload())

    @app.put("/api/project")
    def api_put_project() -> Response | tuple[Response, int]:
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return _json_error("Se esperaba un cuerpo JSON válido.")
        raw_project = body.get("project", body)
        active_wall_id = body.get("active_wall_id")
        if active_wall_id is not None and not isinstance(active_wall_id, str):
            return _json_error("active_wall_id debe ser texto.")
        try:
            validated = project_from_dict(raw_project)
        except ProjectValidationError as exc:
            return _json_error(str(exc), 422)

        store.replace_project(validated, active_wall_id=active_wall_id)
        return jsonify(store.snapshot_payload())

    @app.post("/api/project/save")
    def api_save_project() -> Response | tuple[Response, int]:
        body = request.get_json(silent=True) or {}
        if not isinstance(body, dict):
            return _json_error("Se esperaba JSON válido.")
        raw_path = body.get("path")
        target = (
            Path(raw_path) if isinstance(raw_path, str) and raw_path.strip() else store.project_path
        )
        if target is None:
            return _json_error("Debe indicar la ruta de guardado (.layoutexpo).")
        save_project_atomic(store.project, target)
        store.replace_project(store.project, project_path=target.resolve())
        return jsonify({"saved": True, "path": str(target.resolve())})

    @app.post("/api/project/open")
    def api_open_project() -> Response | tuple[Response, int]:
        body = request.get_json(silent=True) or {}
        raw_path = body.get("path") if isinstance(body, dict) else None
        if not isinstance(raw_path, str) or not raw_path.strip():
            return _json_error("Debe indicar la ruta del archivo .layoutexpo.")
        try:
            loaded = load_project(Path(raw_path))
        except ProjectValidationError as exc:
            return _json_error(str(exc), 422)
        store.replace_project(loaded, project_path=Path(raw_path).resolve())
        return jsonify(store.snapshot_payload())

    def _import_local_paths(
        raw_paths: list[str],
    ) -> tuple[list[dict[str, object]], list[dict[str, str]]]:
        imported: list[dict[str, object]] = []
        errors: list[dict[str, str]] = []
        for raw_p in raw_paths:
            try:
                item = import_image(Path(raw_p), store.proxy_dir)
                imported.append(
                    {
                        "source_path": item.source_path,
                        "sha256": item.sha256,
                        "pixel_width": item.pixel_width,
                        "pixel_height": item.pixel_height,
                        "dpi_x": item.dpi_x,
                        "dpi_y": item.dpi_y,
                        "proxy_path": item.proxy_path,
                        "icc_converted": item.icc_converted,
                    }
                )
            except MediaImportError as exc:
                errors.append({"path": raw_p, "error": str(exc)})
        return (imported, errors)

    @app.post("/api/media/import")
    def api_import_media() -> Response | tuple[Response, int]:
        body = request.get_json(silent=True) or {}
        raw_paths = body.get("paths") if isinstance(body, dict) else None
        if not isinstance(raw_paths, list) or not all(isinstance(p, str) for p in raw_paths):
            return _json_error("Se esperaba 'paths' como lista de rutas locales.")
        imported, errors = _import_local_paths(raw_paths)
        return jsonify({"imported": imported, "errors": errors})

    @app.post("/api/media/upload")
    def api_upload_media() -> Response | tuple[Response, int]:
        files = request.files.getlist("files")
        if not files:
            return _json_error("No se recibieron archivos de imagen en 'files'.")

        imported: list[dict[str, object]] = []
        errors: list[dict[str, str]] = []
        with tempfile.TemporaryDirectory(prefix="layoutexpo_up_") as tmp_dir:
            tmp_root = Path(tmp_dir)
            for storage in files:
                raw_name = storage.filename or ""
                safe_name = secure_filename(raw_name) or "imagen"
                suffix = Path(safe_name).suffix.lower()
                if suffix not in ALLOWED_IMAGE_EXTENSIONS:
                    errors.append(
                        {
                            "path": raw_name,
                            "error": (
                                f"Formato no soportado '{suffix}'. Permitidos: JPEG, PNG, TIFF."
                            ),
                        }
                    )
                    continue
                staged = tmp_root / safe_name
                storage.save(staged)
                try:
                    item = import_image(staged, store.proxy_dir)
                    imported.append(
                        {
                            "source_path": raw_name,
                            "sha256": item.sha256,
                            "pixel_width": item.pixel_width,
                            "pixel_height": item.pixel_height,
                            "dpi_x": item.dpi_x,
                            "dpi_y": item.dpi_y,
                            "proxy_path": item.proxy_path,
                            "icc_converted": item.icc_converted,
                        }
                    )
                except MediaImportError as exc:
                    errors.append({"path": raw_name, "error": str(exc)})
        return jsonify({"imported": imported, "errors": errors})

    @app.get("/api/media/proxy/<artwork_id>")
    def api_get_proxy(artwork_id: str) -> Response | tuple[Response, int]:
        proxy_path = store.get_proxy_path(artwork_id)
        if proxy_path is None:
            return _json_error("Proxy de imagen no disponible.", 404)
        resolved_dir = store.proxy_dir.resolve()
        if not proxy_path.is_relative_to(resolved_dir):
            return _json_error("Ruta de proxy fuera de directorio permitido.", 403)
        return send_file(proxy_path, mimetype="image/jpeg")

    @app.get("/api/media/wall-proxy/<wall_id>")
    def api_get_wall_proxy(wall_id: str) -> Response | tuple[Response, int]:
        proxy_path = store.get_wall_proxy_path(wall_id)
        if proxy_path is None:
            return _json_error("Imagen de muro no disponible.", 404)
        resolved_dir = store.proxy_dir.resolve()
        if not proxy_path.is_relative_to(resolved_dir):
            return _json_error("Ruta de proxy fuera de directorio permitido.", 403)
        return send_file(proxy_path, mimetype="image/jpeg")

    @app.post("/api/layout/align")
    def api_align_placements() -> Response | tuple[Response, int]:
        body = request.get_json(silent=True) or {}
        if not isinstance(body, dict):
            return _json_error("Se esperaba JSON válido.")
        wall_id = body.get("wall_id")
        placement_ids = body.get("placement_ids")
        mode = body.get("mode")
        if (
            not isinstance(wall_id, str)
            or not isinstance(placement_ids, list)
            or mode not in ("top", "bottom", "center_y", "left", "right", "center_x", "eye_level")
        ):
            return _json_error("Parámetros inválidos para alineación.")

        proj = store.project
        wall = next((w for w in proj.walls if w.id == wall_id), None)
        if wall is None:
            return _json_error("Muro no encontrado.", 404)
        selected = [p for p in wall.placements if p.id in set(placement_ids)]
        updated = align_placements(
            selected,
            proj.artworks_by_id(),
            cast(AlignMode, mode),
            eye_level_dmm=wall.eye_level_dmm,
        )
        for pl in wall.placements:
            if pl.id in updated:
                pl.x_dmm, pl.y_dmm = updated[pl.id]
        store.replace_project(proj, active_wall_id=wall.id)
        return jsonify(store.snapshot_payload())

    @app.post("/api/layout/distribute")
    def api_distribute_placements() -> Response | tuple[Response, int]:
        body = request.get_json(silent=True) or {}
        if not isinstance(body, dict):
            return _json_error("Se esperaba JSON válido.")
        wall_id = body.get("wall_id")
        placement_ids = body.get("placement_ids")
        gap_dmm = body.get("gap_dmm")
        if not isinstance(wall_id, str) or not isinstance(placement_ids, list):
            return _json_error("Parámetros inválidos para distribución.")
        if gap_dmm is not None and (isinstance(gap_dmm, bool) or not isinstance(gap_dmm, int)):
            return _json_error("gap_dmm debe ser entero o null.")

        proj = store.project
        wall = next((w for w in proj.walls if w.id == wall_id), None)
        if wall is None:
            return _json_error("Muro no encontrado.", 404)
        selected = [p for p in wall.placements if p.id in set(placement_ids)]
        try:
            updated = distribute_horizontally(selected, proj.artworks_by_id(), gap_dmm=gap_dmm)
        except ValueError as exc:
            return _json_error(str(exc), 422)
        for pl in wall.placements:
            if pl.id in updated:
                pl.x_dmm, pl.y_dmm = updated[pl.id]
        store.replace_project(proj, active_wall_id=wall.id)
        return jsonify(store.snapshot_payload())

    @app.post("/api/layout/snap")
    def api_snap_preview() -> Response | tuple[Response, int]:
        body = request.get_json(silent=True) or {}
        if not isinstance(body, dict):
            return _json_error("Se esperaba JSON válido.")
        wall_id = body.get("wall_id")
        artwork_id = body.get("artwork_id")
        x_dmm = body.get("x_dmm")
        y_dmm = body.get("y_dmm")
        placement_id = body.get("placement_id")
        if (
            not isinstance(wall_id, str)
            or not isinstance(artwork_id, str)
            or isinstance(x_dmm, bool)
            or not isinstance(x_dmm, int)
            or isinstance(y_dmm, bool)
            or not isinstance(y_dmm, int)
        ):
            return _json_error("Parámetros inválidos para snap.")

        proj = store.project
        wall = next((w for w in proj.walls if w.id == wall_id), None)
        arts = proj.artworks_by_id()
        art = arts.get(artwork_id)
        if wall is None or art is None:
            return _json_error("Muro u obra no encontrados.", 404)
        res = snap_placement(
            x_dmm,
            y_dmm,
            art,
            wall,
            arts,
            moving_placement_id=placement_id if isinstance(placement_id, str) else None,
        )
        return jsonify(
            {
                "x_dmm": res.x_dmm,
                "y_dmm": res.y_dmm,
                "guides": [
                    {"axis": g.axis, "coord_dmm": g.coord_dmm, "kind": g.kind} for g in res.guides
                ],
            }
        )

    @app.post("/api/layout/reorganize")
    def api_reorganize_layout() -> Response | tuple[Response, int]:
        body = request.get_json(silent=True) or {}
        if not isinstance(body, dict):
            return _json_error("Se esperaba JSON válido.")
        wall_id = body.get("wall_id") or store.active_wall_id
        scope = body.get("scope", "active_wall")
        allow_constellations = body.get("allow_constellations", True)
        if (
            not isinstance(wall_id, str)
            or scope not in ("active_wall", "all_walls")
            or not isinstance(allow_constellations, bool)
        ):
            return _json_error("Parámetros inválidos para reorganización armónica.")

        result = reorganize_exhibition(
            store.project,
            active_wall_id=wall_id,
            scope=cast(CurationScope, scope),
            allow_constellations=allow_constellations,
        )
        store.replace_project(result.project, active_wall_id=wall_id)
        payload = store.snapshot_payload()
        payload["curation"] = {
            "rationale": list(result.rationale),
            "warnings": list(result.warnings),
            "metrics": result.metrics,
        }
        return jsonify(payload)

    @app.get("/api/layout/presets")
    def api_list_presets() -> Response:
        return jsonify({"presets": list_layout_presets()})

    @app.post("/api/layout/apply-preset")
    def api_apply_preset() -> Response | tuple[Response, int]:
        body = request.get_json(silent=True) or {}
        if not isinstance(body, dict):
            return _json_error("Se esperaba JSON válido.")
        wall_id = body.get("wall_id") or store.active_wall_id
        preset_id = body.get("preset_id")
        scale_factor = body.get("scale_factor", 1.0)
        preserve_aspect = body.get("preserve_aspect", True)
        create_placeholders = body.get("create_placeholders", True)
        if (
            not isinstance(wall_id, str)
            or not isinstance(preset_id, str)
            or isinstance(scale_factor, bool)
            or not isinstance(scale_factor, int | float)
            or not isinstance(preserve_aspect, bool)
            or not isinstance(create_placeholders, bool)
        ):
            return _json_error("Parámetros inválidos para aplicar plantilla.")

        try:
            result = apply_layout_preset(
                store.project,
                wall_id=wall_id,
                preset_id=preset_id,
                scale_factor=float(scale_factor),
                preserve_aspect=preserve_aspect,
                create_placeholders=create_placeholders,
            )
        except ProjectValidationError as exc:
            return _json_error(str(exc), 422)

        store.replace_project(result.project, active_wall_id=wall_id)
        payload = store.snapshot_payload()
        payload["curation"] = {
            "rationale": list(result.rationale),
            "warnings": list(result.warnings),
            "metrics": {
                "preset_id": result.preset_id,
                "used_existing": result.used_existing,
                "created_samples": result.created_samples,
            },
        }
        return jsonify(payload)

    @app.post("/api/export/pdf")
    def api_export_pdf() -> Response | tuple[Response, int]:
        body = request.get_json(silent=True) or {}
        if not isinstance(body, dict):
            return _json_error("Se esperaba JSON válido.")
        raw_path = body.get("output_path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            return _json_error("Debe indicar 'output_path' para el PDF.")

        try:
            out = export_exhibition_pdf(
                store.project,
                Path(raw_path),
                proxy_paths=store.all_proxy_paths(),
                include_elevations=bool(body.get("include_elevations", True)),
                include_inventory=bool(body.get("include_inventory", True)),
                include_labels=bool(body.get("include_labels", True)),
            )
        except ValueError as exc:
            return _json_error(str(exc), 422)
        return jsonify({"exported": True, "output_path": str(out)})

    @app.get("/api/project/download")
    def api_download_project() -> Response:
        slug = secure_filename(store.project.title) or "exposicion"
        filename = f"{slug}.layoutexpo"
        raw = json.dumps(project_to_dict(store.project), indent=2, ensure_ascii=False).encode(
            "utf-8"
        )
        return send_file(
            io.BytesIO(raw),
            mimetype="application/json; charset=utf-8",
            as_attachment=True,
            download_name=filename,
        )

    @app.get("/api/export/pdf/download")
    def api_download_pdf() -> Response | tuple[Response, int]:
        slug = secure_filename(store.project.title) or "montaje_expo"
        filename = f"{slug}.pdf"
        with tempfile.TemporaryDirectory(prefix="layoutexpo_pdf_") as tmp_dir:
            tmp_pdf = Path(tmp_dir) / filename
            try:
                out = export_exhibition_pdf(
                    store.project,
                    tmp_pdf,
                    proxy_paths=store.all_proxy_paths(),
                    include_elevations=True,
                    include_inventory=True,
                    include_labels=True,
                )
                data = out.read_bytes()
            except ValueError as exc:
                return _json_error(str(exc), 422)
        return send_file(
            io.BytesIO(data),
            mimetype="application/pdf",
            as_attachment=True,
            download_name=filename,
        )

    @app.post("/api/native/choose-images")
    def api_native_choose_images() -> Response | tuple[Response, int]:
        if dialog_controller is None:
            return _json_error("Diálogos nativos no disponibles en modo headless.", 501)
        paths = dialog_controller.choose_images()
        if not paths:
            return jsonify({"cancelled": True, "imported": [], "errors": []})
        imported, errors = _import_local_paths(paths)
        return jsonify({"cancelled": False, "imported": imported, "errors": errors})

    @app.post("/api/native/save-project")
    def api_native_save_project() -> Response | tuple[Response, int]:
        if dialog_controller is None:
            return _json_error("Diálogos nativos no disponibles en modo headless.", 501)
        slug = secure_filename(store.project.title) or "exposicion"
        default_name = (
            store.project_path.name if store.project_path is not None else f"{slug}.layoutexpo"
        )
        chosen = dialog_controller.choose_save_project(default_name=default_name)
        if not chosen:
            return jsonify({"saved": False, "cancelled": True})
        target = Path(chosen)
        save_project_atomic(store.project, target)
        store.replace_project(store.project, project_path=target.resolve())
        return jsonify({"saved": True, "cancelled": False, "path": str(target.resolve())})

    @app.post("/api/native/open-project")
    def api_native_open_project() -> Response | tuple[Response, int]:
        if dialog_controller is None:
            return _json_error("Diálogos nativos no disponibles en modo headless.", 501)
        chosen = dialog_controller.choose_open_project()
        if not chosen:
            return jsonify({"cancelled": True})
        try:
            loaded = load_project(Path(chosen))
        except ProjectValidationError as exc:
            return _json_error(str(exc), 422)
        store.replace_project(loaded, project_path=Path(chosen).resolve())
        payload = store.snapshot_payload()
        payload["cancelled"] = False
        return jsonify(payload)

    @app.post("/api/native/export-pdf")
    def api_native_export_pdf() -> Response | tuple[Response, int]:
        if dialog_controller is None:
            return _json_error("Diálogos nativos no disponibles en modo headless.", 501)
        slug = secure_filename(store.project.title) or "montaje_expo"
        chosen = dialog_controller.choose_save_pdf(default_name=f"{slug}_plano.pdf")
        if not chosen:
            return jsonify({"exported": False, "cancelled": True})
        try:
            out = export_exhibition_pdf(
                store.project,
                Path(chosen),
                proxy_paths=store.all_proxy_paths(),
                include_elevations=True,
                include_inventory=True,
                include_labels=True,
            )
        except ValueError as exc:
            return _json_error(str(exc), 422)
        return jsonify({"exported": True, "cancelled": False, "output_path": str(out)})

    @app.get("/api/projector/stream")
    def api_projector_stream() -> Response:
        subscriber = store.broadcaster.subscribe()

        def _event_stream() -> Iterator[str]:
            try:
                initial = json.dumps({"revision": store.revision})
                yield f"event: revision\ndata: {initial}\n\n"
                while True:
                    try:
                        rev = subscriber.get(timeout=15.0)
                        payload = json.dumps({"revision": rev})
                        yield f"event: revision\ndata: {payload}\n\n"
                    except queue.Empty:
                        yield ": heartbeat\n\n"
            finally:
                store.broadcaster.unsubscribe(subscriber)

        return Response(_event_stream(), mimetype="text/event-stream")

    @app.get("/api/displays")
    def api_displays() -> Response:
        if window_controller is None:
            return jsonify({"displays": [], "projector_open": False})
        return jsonify(
            {
                "displays": window_controller.list_displays(),
                "projector": window_controller.status(),
            }
        )

    @app.post("/api/projector/window")
    def api_projector_window() -> Response | tuple[Response, int]:
        if window_controller is None:
            return _json_error(
                "Controlador nativo de ventanas no disponible en modo headless.", 501
            )
        body = request.get_json(silent=True) or {}
        action = body.get("action") if isinstance(body, dict) else None
        if action == "open":
            display_idx = body.get("display_index") if isinstance(body, dict) else None
            fullscreen_val = body.get("fullscreen") if isinstance(body, dict) else None
            idx = (
                display_idx
                if isinstance(display_idx, int) and not isinstance(display_idx, bool)
                else None
            )
            fs = fullscreen_val if isinstance(fullscreen_val, bool) else None
            return jsonify(window_controller.open_projector(idx, fullscreen=fs))
        if action == "close":
            return jsonify(window_controller.close_projector())
        return _json_error("Acción inválida; use 'open' o 'close'.")

    return app
