"""Pruebas de integración para rutas UI estáticas y carga multipart de medios."""

import io
import secrets
from pathlib import Path

from PIL import Image

from server.app import create_app
from server.events import ProjectStateStore


def test_ui_routes_and_multipart_upload(tmp_path: Path) -> None:
    store = ProjectStateStore(proxy_dir=tmp_path / "proxies")
    token = secrets.token_urlsafe(16)
    app = create_app(store, session_token=token)
    client = app.test_client()

    studio_res = client.get(f"/?token={token}")
    assert studio_res.status_code == 200
    assert b"LayoutExpo" in studio_res.data

    proj_res = client.get(f"/projector?token={token}")
    assert proj_res.status_code == 200
    assert b"projector-svg" in proj_res.data

    tokens_res = client.get("/ui/tokens.css")
    assert tokens_res.status_code == 200
    assert b"--surface-workspace" in tokens_res.data

    buf = io.BytesIO()
    Image.new("RGB", (300, 200), (120, 80, 60)).save(buf, format="JPEG")
    buf.seek(0)

    up_res = client.post(
        "/api/media/upload",
        headers={"X-LayoutExpo-Token": token},
        data={"files": (buf, "paisaje.jpg")},
        content_type="multipart/form-data",
    )
    assert up_res.status_code == 200
    payload = up_res.get_json()
    assert len(payload["imported"]) == 1
    assert payload["imported"][0]["pixel_width"] == 300
    assert payload["errors"] == []
