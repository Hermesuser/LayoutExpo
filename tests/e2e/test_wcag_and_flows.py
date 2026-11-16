"""Pruebas E2E en navegador real y auditoría automatizada WCAG 2.2 AA (axe-core)."""

from __future__ import annotations

import secrets
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest
from axe_playwright_python.sync_playwright import Axe
from playwright.sync_api import Browser, Playwright, sync_playwright
from werkzeug.serving import make_server

from server.app import create_app
from server.events import ProjectStateStore


@pytest.fixture
def live_server(tmp_path: Path) -> Iterator[tuple[str, str]]:
    store = ProjectStateStore(proxy_dir=tmp_path / "proxies")
    token = secrets.token_urlsafe(16)
    app = create_app(store, session_token=token)
    server = make_server("127.0.0.1", 0, app, threaded=True)
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield (f"http://127.0.0.1:{port}", token)
    finally:
        server.shutdown()


def _launch_browser(p: Playwright) -> Browser:
    try:
        return p.chromium.launch(headless=True)
    except Exception:
        return p.chromium.launch(channel="chrome", headless=True)


def _assert_zero_wcag_violations(results: object, context_label: str) -> None:
    response = getattr(results, "response", {})
    violations = response.get("violations", [])
    assert violations == [], f"Violaciones WCAG en {context_label}: {violations}"


def test_studio_and_projector_e2e_wcag_and_keyboard_flows(live_server: tuple[str, str]) -> None:
    base_url, token = live_server
    axe = Axe()
    axe_options = {
        "runOnly": {"type": "tag", "values": ["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]}
    }

    with sync_playwright() as p:
        browser = _launch_browser(p)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page_errors: list[str] = []
            page.on("pageerror", lambda err: page_errors.append(str(err)))

            # 1. Abrir Estudio y auditar WCAG 2.2 AA inicial
            page.goto(f"{base_url}/?token={token}", wait_until="networkidle")
            _assert_zero_wcag_violations(axe.run(page, options=axe_options), "Studio inicial")

            # 2. Agregar obra por medidas y verificar colocación + inspector + toast visible
            page.get_by_role("button", name="+ Por medidas").click()
            artwork_node = page.locator("#wall-svg .artwork-node").first
            artwork_node.wait_for(state="visible")
            page.locator("#toast-banner").wait_for(state="visible")
            assert page.locator("#import-size-preset").input_value() == "max50"
            initial_x = float(page.locator("#pl-x-cm").input_value())

            # 3. Mover con teclado: ArrowRight (+1 mm) y Shift+ArrowRight (+1 cm)
            artwork_node.focus()
            page.keyboard.press("ArrowRight")
            page.wait_for_timeout(150)
            page.keyboard.press("Shift+ArrowRight")
            page.wait_for_timeout(200)
            moved_x = float(page.locator("#pl-x-cm").input_value())
            assert moved_x == pytest.approx(initial_x + 1.1, abs=0.15)

            # 3b. Verificar 4 nodos de esquina y redimensionar por teclado (Alt+ArrowRight)
            assert page.locator("#wall-svg .resize-handle").count() == 4
            initial_w = float(page.locator("#art-w-cm").input_value())
            artwork_node.focus()
            page.keyboard.press("Alt+ArrowRight")
            page.wait_for_timeout(150)
            assert float(page.locator("#art-w-cm").input_value()) == pytest.approx(
                initial_w + 1.0, abs=0.15
            )

            # 3c. Personalizar textura del muro y probar selector visual de Plantillas
            page.get_by_role("tab", name="Muro").click()
            page.locator("#wall-texture-preset").select_option("concrete")
            page.locator("#wall-svg pattern#wall-tex-wall-1").wait_for(state="attached")
            page.locator("#btn-presets-toggle").click()
            page.locator("#presets-panel").wait_for(state="visible")
            _assert_zero_wcag_violations(
                axe.run(page, options=axe_options), "Selector de plantillas abierto"
            )
            page.locator('[data-preset-id="triptico_clasico"]').click()
            page.locator("#presets-panel").wait_for(state="hidden")
            assert page.locator("#wall-svg .artwork-node").count() == 3
            page.keyboard.press("Escape")
            page.locator("#btn-undo").click()
            page.wait_for_timeout(150)
            assert page.locator("#btn-redo").is_enabled()
            page.locator("#btn-redo").click()
            page.wait_for_timeout(150)
            assert page.locator("#wall-svg .artwork-node").count() == 3
            page.locator("#btn-undo").click()
            page.wait_for_timeout(150)

            # 3d. Verificar panel de atajos de teclado y menú Archivo con Escape + WCAG
            page.locator("#btn-shortcuts-toggle").click()
            page.locator("#shortcuts-panel").wait_for(state="visible")
            _assert_zero_wcag_violations(
                axe.run(page, options=axe_options), "Panel de atajos abierto"
            )
            page.keyboard.press("Escape")
            page.locator("#shortcuts-panel").wait_for(state="hidden")
            assert page.evaluate("document.activeElement?.id") == "btn-shortcuts-toggle"

            page.locator("#file-menu summary").click()
            assert page.locator("#file-menu").evaluate("el => el.open") is True
            _assert_zero_wcag_violations(axe.run(page, options=axe_options), "Menú Archivo abierto")
            page.keyboard.press("Escape")
            assert page.locator("#file-menu").evaluate("el => el.open") is False

            # 4. Cambiar a tab Proyector, verificar calibrador visual y auditar WCAG 2.2 AA
            page.get_by_role("tab", name="Proyector").click()
            assert page.locator("#keystone-pad .keystone-handle").count() == 4
            p1_handle = page.locator('#keystone-pad .keystone-handle[data-corner="0"]')
            p1_before = p1_handle.get_attribute("aria-valuetext")
            p1_handle.focus()
            page.keyboard.press("ArrowRight")
            page.wait_for_timeout(150)
            assert p1_handle.get_attribute("aria-valuetext") != p1_before
            _assert_zero_wcag_violations(
                axe.run(page, options=axe_options), "Studio con obra y tab Proyector"
            )

            # 5. Abrir vista Proyector en segunda pestaña y verificar homografía + HUD + SSE + WCAG
            proj_page = browser.new_page(viewport={"width": 1280, "height": 720})
            proj_page.on("pageerror", lambda err: page_errors.append(str(err)))
            proj_page.goto(f"{base_url}/projector?token={token}", wait_until="networkidle")
            proj_page.locator("#projector-svg rect").first.wait_for(state="attached")
            proj_page.locator("#btn-prev-tile").wait_for(state="visible")
            proj_page.locator("#btn-next-tile").wait_for(state="visible")
            proj_page.locator("#btn-close-projector").wait_for(state="visible")
            inline_transform = proj_page.locator("#projector-stage").evaluate(
                "el => el.style.transform"
            )
            assert inline_transform.startswith("matrix3d(")
            computed_transform = proj_page.locator("#projector-stage").evaluate(
                "el => getComputedStyle(el).transform"
            )
            assert computed_transform.startswith(("matrix(", "matrix3d("))

            # Activar patrón de calibración por teclado (G) y probar ocultar/mostrar HUD (H / Esc)
            proj_page.keyboard.press("g")
            assert proj_page.locator("#projector-svg polygon").count() == 1
            _assert_zero_wcag_violations(axe.run(proj_page, options=axe_options), "Vista Proyector")
            proj_page.keyboard.press("h")
            proj_page.locator("#projector-hud").wait_for(state="hidden")
            proj_page.locator("#projector-hint").wait_for(state="visible")
            proj_page.keyboard.press("Escape")
            proj_page.locator("#projector-hud").wait_for(state="visible")

            # Verificar sincronización SSE en vivo desde Estudio -> Proyector
            page.get_by_role("button", name="+ Por medidas").click()
            proj_page.wait_for_function(
                "() => document.getElementById('hud-status')?.textContent?.includes('2 obra(s)')",
                timeout=3000,
            )

            # Reorganización armónica, reporte flotante, auditoría WCAG y deshacer/Escape
            page.locator("#btn-reorganize").click()
            report = page.locator("#curation-report")
            report.wait_for(state="visible")
            assert page.locator("#curation-rationale-list li").count() >= 1
            _assert_zero_wcag_violations(
                axe.run(page, options=axe_options), "Studio con reporte de curaduría abierto"
            )
            page.keyboard.press("Escape")
            report.wait_for(state="hidden")
            page.locator("#btn-reorganize").click()
            report.wait_for(state="visible")
            page.locator("#btn-undo-curation").click()
            report.wait_for(state="hidden")
            assert page_errors == []
        finally:
            browser.close()
