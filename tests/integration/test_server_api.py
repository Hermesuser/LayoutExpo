"""Pruebas de integración del servidor local loopback, API, proxies, PDF y displays."""

import secrets
from pathlib import Path

from PIL import Image

from core.project import project_to_dict
from core.units import cm_to_dmm
from desktop.displays import DisplayInfo, pick_projector_display
from server.app import create_app
from server.events import ProjectStateStore


def test_api_security_project_media_layout_and_pdf(tmp_path: Path) -> None:
    proxy_dir = tmp_path / "proxies"
    store = ProjectStateStore(proxy_dir=proxy_dir)
    token = secrets.token_urlsafe(16)
    app = create_app(store, session_token=token)
    client = app.test_client()
    headers = {"X-LayoutExpo-Token": token}

    # 1. Sin token => 401 + headers CSP estrictos
    unauth = client.get("/api/health")
    assert unauth.status_code == 401
    assert "default-src 'self'" in unauth.headers["Content-Security-Policy"]

    ok = client.get("/api/health", headers=headers)
    assert ok.status_code == 200
    assert ok.get_json()["status"] == "ok"

    # 2. Importar imagen sintética
    img_path = tmp_path / "foto.png"
    Image.new("RGB", (600, 400), (100, 140, 180)).save(img_path, format="PNG")
    imp_res = client.post("/api/media/import", headers=headers, json={"paths": [str(img_path)]})
    assert imp_res.status_code == 200
    imp_data = imp_res.get_json()["imported"][0]

    # 3. Actualizar proyecto vía PUT /api/project y verificar proyección + reporte + proxy
    proj_dict = project_to_dict(store.project)
    proj_dict["artworks"] = [
        {
            "id": "art-1",
            "title": "Obra Uno",
            "author": "Autor",
            "year": "2026",
            "medium": "Inkjet",
            "source_path": imp_data["source_path"],
            "sha256": imp_data["sha256"],
            "image_width_dmm": cm_to_dmm(60),
            "image_height_dmm": cm_to_dmm(40),
            "mounting_type": "framed",
            "frame": {"top_dmm": 200, "bottom_dmm": 200, "left_dmm": 200, "right_dmm": 200},
            "passepartout": {"top_dmm": 400, "bottom_dmm": 400, "left_dmm": 400, "right_dmm": 400},
            "hardware": {"hanging_type": "single_center", "offset_from_top_dmm": 300},
        }
    ]
    walls_list = proj_dict["walls"]
    assert isinstance(walls_list, list)
    first_wall = walls_list[0]
    assert isinstance(first_wall, dict)
    first_wall["placements"] = [
        {"id": "pl-1", "artwork_id": "art-1", "x_dmm": cm_to_dmm(50), "y_dmm": cm_to_dmm(100)}
    ]
    put_res = client.put("/api/project", headers=headers, json={"project": proj_dict})
    assert put_res.status_code == 200
    snap = put_res.get_json()
    assert snap["revision"] == 2
    assert snap["projections"]["wall-1"]["valid"] is True
    assert snap["projections"]["wall-1"]["css_matrix3d"].startswith("matrix3d(")

    proxy_res = client.get(f"/api/media/proxy/art-1?token={token}")
    assert proxy_res.status_code == 200
    assert proxy_res.mimetype == "image/jpeg"

    # 4. Alinear al eje visual vía API
    align_res = client.post(
        "/api/layout/align",
        headers=headers,
        json={"wall_id": "wall-1", "placement_ids": ["pl-1"], "mode": "eye_level"},
    )
    assert align_res.status_code == 200
    # outer height = 40 + 8 + 4 = 52 cm; eye_level = 150 cm => y = 124 cm
    placed = align_res.get_json()["project"]["walls"][0]["placements"][0]
    assert placed["y_dmm"] == cm_to_dmm(124)

    # 5. Guardar, reabrir y exportar PDF
    save_file = tmp_path / "expo.layoutexpo"
    assert (
        client.post("/api/project/save", headers=headers, json={"path": str(save_file)}).status_code
        == 200
    )
    assert save_file.is_file()
    assert (
        client.post("/api/project/open", headers=headers, json={"path": str(save_file)}).status_code
        == 200
    )

    pdf_file = tmp_path / "plano.pdf"
    pdf_res = client.post("/api/export/pdf", headers=headers, json={"output_path": str(pdf_file)})
    assert pdf_res.status_code == 200
    assert pdf_file.read_bytes().startswith(b"%PDF-")


def test_pick_projector_display_prefers_external_monitor() -> None:
    primary = DisplayInfo(0, "Built-in", 0, 0, 1512, 982, is_primary=True)
    projector = DisplayInfo(1, "Epson Projector", 1512, 0, 1920, 1080, is_primary=False)
    assert pick_projector_display([primary, projector]) == projector
    assert pick_projector_display([primary]) == primary
    assert pick_projector_display([]) is None


def test_api_reorganize_harmonic_and_backward_compatibility(tmp_path: Path) -> None:
    store = ProjectStateStore(proxy_dir=tmp_path / "proxies")
    token = secrets.token_urlsafe(16)
    app = create_app(store, session_token=token)
    client = app.test_client()
    headers = {"X-LayoutExpo-Token": token}

    # Cargar payload v1 sin campos V2.1 (is_anchor / narrative_role)
    proj_dict = project_to_dict(store.project)
    proj_dict["artworks"] = [
        {
            "id": "v1",
            "title": "Vertical 1",
            "image_width_dmm": cm_to_dmm(40),
            "image_height_dmm": cm_to_dmm(60),
            "mounting_type": "direct",
        },
        {
            "id": "h1",
            "title": "Horizontal Ancla",
            "image_width_dmm": cm_to_dmm(80),
            "image_height_dmm": cm_to_dmm(50),
            "mounting_type": "direct",
            "is_anchor": True,
        },
        {
            "id": "v2",
            "title": "Vertical 2",
            "image_width_dmm": cm_to_dmm(40),
            "image_height_dmm": cm_to_dmm(60),
            "mounting_type": "direct",
        },
    ]
    walls = proj_dict["walls"]
    assert isinstance(walls, list)
    first_wall = walls[0]
    assert isinstance(first_wall, dict)
    first_wall.pop("narrative_role", None)
    first_wall["placements"] = [
        {"id": "p1", "artwork_id": "v1", "x_dmm": cm_to_dmm(50), "y_dmm": cm_to_dmm(100)},
        {"id": "p2", "artwork_id": "h1", "x_dmm": cm_to_dmm(110), "y_dmm": cm_to_dmm(100)},
        {"id": "p3", "artwork_id": "v2", "x_dmm": cm_to_dmm(210), "y_dmm": cm_to_dmm(100)},
    ]
    put_res = client.put("/api/project", headers=headers, json={"project": proj_dict})
    assert put_res.status_code == 200

    reorg_res = client.post(
        "/api/layout/reorganize",
        headers=headers,
        json={"wall_id": "wall-1", "scope": "active_wall", "allow_constellations": True},
    )
    assert reorg_res.status_code == 200
    payload = reorg_res.get_json()
    assert "curation" in payload
    assert isinstance(payload["curation"]["rationale"], list)
    assert len(payload["curation"]["rationale"]) >= 1
    placed_sorted = sorted(payload["project"]["walls"][0]["placements"], key=lambda p: p["x_dmm"])
    assert placed_sorted[1]["artwork_id"] == "h1"


class _FakeDialogController:
    def __init__(self, tmp_dir: Path, img_file: Path, *, cancel: bool = False) -> None:
        self.tmp_dir = tmp_dir
        self.img_file = img_file
        self.cancel = cancel

    def choose_images(self) -> list[str]:
        return [] if self.cancel else [str(self.img_file)]

    def choose_open_project(self) -> str | None:
        save_path = self.tmp_dir / "opened.layoutexpo"
        return None if self.cancel else str(save_path)

    def choose_save_project(self, default_name: str = "exposicion.layoutexpo") -> str | None:
        return None if self.cancel else str(self.tmp_dir / "opened.layoutexpo")

    def choose_save_pdf(self, default_name: str = "montaje_expo.pdf") -> str | None:
        return None if self.cancel else str(self.tmp_dir / "plano_nativo.pdf")


def test_api_downloads_and_native_dialog_endpoints(tmp_path: Path) -> None:
    store = ProjectStateStore(proxy_dir=tmp_path / "proxies")
    img_path = tmp_path / "muestra.png"
    Image.new("RGB", (800, 600), (60, 90, 120)).save(img_path, format="PNG")
    token = secrets.token_urlsafe(16)
    ctrl = _FakeDialogController(tmp_path, img_path)
    app = create_app(store, session_token=token, dialog_controller=ctrl)
    client = app.test_client()
    headers = {"X-LayoutExpo-Token": token}

    caps = client.get("/api/capabilities", headers=headers).get_json()
    assert caps == {"native_dialogs": True, "native_projector": False}

    # Descargas directas para modo navegador
    proj_dl = client.get(f"/api/project/download?token={token}")
    assert proj_dl.status_code == 200
    assert "attachment" in proj_dl.headers["Content-Disposition"]
    assert b'"schema_version"' in proj_dl.data

    pdf_dl = client.get(f"/api/export/pdf/download?token={token}")
    assert pdf_dl.status_code == 200
    assert pdf_dl.data.startswith(b"%PDF-")

    # Endpoints de diálogo nativo
    chosen = client.post("/api/native/choose-images", headers=headers).get_json()
    assert chosen["cancelled"] is False
    assert len(chosen["imported"]) == 1

    saved = client.post("/api/native/save-project", headers=headers).get_json()
    assert saved["saved"] is True
    assert (tmp_path / "opened.layoutexpo").is_file()

    opened = client.post("/api/native/open-project", headers=headers).get_json()
    assert opened["cancelled"] is False
    assert "project" in opened

    exported = client.post("/api/native/export-pdf", headers=headers).get_json()
    assert exported["exported"] is True
    assert (tmp_path / "plano_nativo.pdf").read_bytes().startswith(b"%PDF-")

    # Cancelación explícita
    ctrl.cancel = True
    assert client.post("/api/native/save-project", headers=headers, json={}).get_json() == {
        "saved": False,
        "cancelled": True,
    }


def test_api_presets_and_wall_image_proxy(tmp_path: Path) -> None:
    store = ProjectStateStore(proxy_dir=tmp_path / "proxies")
    img_path = tmp_path / "pared.png"
    Image.new("RGB", (900, 600), (210, 205, 195)).save(img_path, format="PNG")
    token = secrets.token_urlsafe(16)
    app = create_app(store, session_token=token)
    client = app.test_client()
    headers = {"X-LayoutExpo-Token": token}

    presets_res = client.get("/api/layout/presets", headers=headers)
    assert presets_res.status_code == 200
    assert len(presets_res.get_json()["presets"]) == 6

    applied = client.post(
        "/api/layout/apply-preset",
        headers=headers,
        json={"wall_id": "wall-1", "preset_id": "reticula_compacta", "scale_factor": 1.0},
    )
    assert applied.status_code == 200
    snap = applied.get_json()
    assert len(snap["project"]["walls"][0]["placements"]) == 10

    imp = client.post(
        "/api/media/import", headers=headers, json={"paths": [str(img_path)]}
    ).get_json()
    sha = imp["imported"][0]["sha256"]
    snap["project"]["walls"][0]["wall_image_sha256"] = sha
    snap["project"]["walls"][0]["wall_texture_preset"] = "concrete"
    assert (
        client.put("/api/project", headers=headers, json={"project": snap["project"]}).status_code
        == 200
    )

    wall_proxy = client.get(f"/api/media/wall-proxy/wall-1?token={token}")
    assert wall_proxy.status_code == 200
    assert wall_proxy.mimetype == "image/jpeg"
