"""Estado en memoria thread-safe y canal Pub/Sub (SSE) entre Estudio y Proyector."""

from __future__ import annotations

import queue
import threading
from dataclasses import dataclass, field
from pathlib import Path

from core.geometry import WallDimensionReport, wall_dimension_report
from core.homography import (
    CalibrationError,
    WallTileBounds,
    compute_homography,
    compute_wall_tile_bounds,
    css_matrix3d_from_homography,
)
from core.project import ExhibitionProject, ProjectorCalibration, Wall, project_to_dict
from core.units import m_to_dmm


def default_empty_project() -> ExhibitionProject:
    """Crea un proyecto inicial listo para trabajar al abrir la aplicación."""
    w_dmm = m_to_dmm(4)
    h_dmm = m_to_dmm(3)
    return ExhibitionProject(
        title="Nueva Exposición",
        walls=[
            Wall(
                id="wall-1",
                name="Muro Principal",
                width_dmm=w_dmm,
                height_dmm=h_dmm,
                calibration=ProjectorCalibration(
                    wall_points_dmm=((0, h_dmm), (w_dmm, h_dmm), (w_dmm, 0), (0, 0)),
                ),
            )
        ],
    )


class ProjectBroadcaster:
    """Distribuidor ligero de eventos de revisión para clientes SSE del proyector."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: set[queue.Queue[int]] = set()

    def subscribe(self) -> queue.Queue[int]:
        q: queue.Queue[int] = queue.Queue(maxsize=32)
        with self._lock:
            self._subscribers.add(q)
        return q

    def unsubscribe(self, q: queue.Queue[int]) -> None:
        with self._lock:
            self._subscribers.discard(q)

    def publish(self, revision: int) -> None:
        with self._lock:
            targets = list(self._subscribers)
        for q in targets:
            try:
                q.put_nowait(revision)
            except queue.Full:
                try:
                    q.get_nowait()
                    q.put_nowait(revision)
                except queue.Empty:
                    pass


def _serialize_report(report: WallDimensionReport) -> dict[str, object]:
    return {
        "wall_id": report.wall_id,
        "wall_name": report.wall_name,
        "wall_width_dmm": report.wall_width_dmm,
        "wall_height_dmm": report.wall_height_dmm,
        "eye_level_dmm": report.eye_level_dmm,
        "items": [
            {
                "placement_id": item.placement_id,
                "artwork_id": item.artwork_id,
                "title": item.title,
                "outer_rect": {
                    "x": item.outer_rect.x,
                    "y": item.outer_rect.y,
                    "width": item.outer_rect.width,
                    "height": item.outer_rect.height,
                },
                "image_rect": {
                    "x": item.image_rect.x,
                    "y": item.image_rect.y,
                    "width": item.image_rect.width,
                    "height": item.image_rect.height,
                },
                "distance_from_floor_dmm": item.distance_from_floor_dmm,
                "distance_from_left_wall_dmm": item.distance_from_left_wall_dmm,
                "distance_from_right_wall_dmm": item.distance_from_right_wall_dmm,
                "distance_from_ceiling_dmm": item.distance_from_ceiling_dmm,
                "center_height_dmm": item.center_height_dmm,
                "anchors": [
                    {
                        "label": a.label,
                        "x_dmm": a.x_dmm,
                        "y_dmm": a.y_dmm,
                        "distance_from_top_edge_dmm": a.distance_from_top_edge_dmm,
                    }
                    for a in item.anchors
                ],
            }
            for item in report.items
        ],
        "horizontal_gaps": [
            {
                "left_placement_id": g.left_placement_id,
                "right_placement_id": g.right_placement_id,
                "gap_dmm": g.gap_dmm,
            }
            for g in report.horizontal_gaps
        ],
        "issues": [
            {
                "code": iss.code,
                "severity": iss.severity,
                "message": iss.message,
                "placement_ids": list(iss.placement_ids),
            }
            for iss in report.issues
        ],
    }


def _compute_wall_projection(wall: Wall) -> dict[str, object]:
    """Calcula tramo activo y matriz CSS 3D normalizada para la ventana del proyector."""
    try:
        tile: WallTileBounds = compute_wall_tile_bounds(
            wall.width_dmm,
            wall.calibration.viewport_x_dmm,
            wall.calibration.viewport_width_dmm,
        )
    except ValueError:
        tile = WallTileBounds(x_start_dmm=0, x_end_dmm=wall.width_dmm, width_dmm=wall.width_dmm)

    src_norm = [(float(x), float(y)) for x, y in wall.calibration.wall_points_dmm]
    dst_norm = [(float(u), float(v)) for u, v in wall.calibration.projector_points_norm]
    try:
        matrix = compute_homography(src_norm, dst_norm)
        css_m3d = css_matrix3d_from_homography(matrix)
        valid = True
        error_msg = ""
    except CalibrationError as exc:
        css_m3d = ""
        valid = False
        error_msg = str(exc)

    return {
        "valid": valid,
        "error": error_msg,
        "tile": {
            "x_start_dmm": tile.x_start_dmm,
            "x_end_dmm": tile.x_end_dmm,
            "width_dmm": tile.width_dmm,
        },
        "css_matrix3d": css_m3d,
    }


@dataclass
class ProjectStateStore:
    """Contenedor sincronizado del proyecto activo y caché de proxies."""

    proxy_dir: Path
    project: ExhibitionProject = field(default_factory=default_empty_project)
    active_wall_id: str = "wall-1"
    project_path: Path | None = None
    revision: int = 1
    broadcaster: ProjectBroadcaster = field(default_factory=ProjectBroadcaster)
    _lock: threading.RLock = field(default_factory=threading.RLock)
    _proxy_map: dict[str, Path] = field(default_factory=dict)

    def snapshot_payload(self) -> dict[str, object]:
        """Devuelve el estado completo más reportes dimensionales y homografía."""
        with self._lock:
            arts = self.project.artworks_by_id()
            reports = {
                w.id: _serialize_report(wall_dimension_report(w, arts)) for w in self.project.walls
            }
            projections = {w.id: _compute_wall_projection(w) for w in self.project.walls}
            wall_ids = {w.id for w in self.project.walls}
            active_id = (
                self.active_wall_id
                if self.active_wall_id in wall_ids
                else (self.project.walls[0].id if self.project.walls else "")
            )
            return {
                "revision": self.revision,
                "active_wall_id": active_id,
                "project_path": str(self.project_path) if self.project_path else None,
                "project": project_to_dict(self.project),
                "reports": reports,
                "projections": projections,
            }

    def replace_project(
        self,
        project: ExhibitionProject,
        *,
        active_wall_id: str | None = None,
        project_path: Path | None = None,
    ) -> int:
        with self._lock:
            self.project = project
            if active_wall_id is not None:
                self.active_wall_id = active_wall_id
            elif project.walls and self.active_wall_id not in {w.id for w in project.walls}:
                self.active_wall_id = project.walls[0].id
            if project_path is not None:
                self.project_path = project_path
            self.revision += 1
            rev = self.revision
        self.broadcaster.publish(rev)
        return rev

    def register_proxy(self, artwork_id: str, proxy_path: Path) -> None:
        with self._lock:
            self._proxy_map[artwork_id] = proxy_path.resolve()

    def get_proxy_path(self, artwork_id: str) -> Path | None:
        with self._lock:
            candidate = self._proxy_map.get(artwork_id)
            if candidate is not None and candidate.is_file():
                return candidate
            art = self.project.artworks_by_id().get(artwork_id)
            if art and art.sha256:
                fallback = (self.proxy_dir / f"{art.sha256[:16]}.jpg").resolve()
                if fallback.is_file():
                    self._proxy_map[artwork_id] = fallback
                    return fallback
            return None

    def get_wall_proxy_path(self, wall_id: str) -> Path | None:
        with self._lock:
            wall = next((w for w in self.project.walls if w.id == wall_id), None)
            if wall and wall.wall_image_sha256:
                candidate = (self.proxy_dir / f"{wall.wall_image_sha256[:16]}.jpg").resolve()
                if candidate.is_file():
                    return candidate
            return None

    def all_proxy_paths(self) -> dict[str, Path]:
        with self._lock:
            out: dict[str, Path] = {}
            for art in self.project.artworks:
                p = self.get_proxy_path(art.id)
                if p is not None:
                    out[art.id] = p
            return out
