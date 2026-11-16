# Arquitectura — LayoutExpo

## Principios de Diseño
1. **Dominio puro desacoplado (`core/`):** Todo cálculo dimensional, de anclajes, homografía, proyecto, media y exportación PDF vive en `core/` sin depender de HTTP, DOM ni `pywebview`.
2. **Precisión entera (`dmm`):** Todas las coordenadas físicas se expresan en décimas de milímetro (`1 mm = 10 dmm`), con origen `(0, 0)` en la esquina inferior izquierda del muro (`+X` derecha, `+Y` arriba).
3. **No destructivo:** Los archivos `JPEG`, `PNG` y `TIFF` originales jamás se escriben; solo se leen para metadatos y generación de proxies sRGB.
4. **Seguridad local:** El servidor local escucha únicamente en `127.0.0.1` con token efímero por sesión y CSP estricta.

## Capas del Sistema

```text
+---------------------------------------------------------------+
|  desktop/ (Cocoa WKWebView macOS arm64/x86_64 | Edge Win11)  |
|    ├── Ventana Estudio (operador)                             |
|    └── Ventana Proyector (fullscreen en pantalla secundaria)   |
+------------------------------+--------------------------------+
                               | HTTP loopback + SSE (token)
+------------------------------v--------------------------------+
|  server/ (API local + sincronización de estado Estudio->Proy) |
+------------------------------+--------------------------------+
                               |
+------------------------------v--------------------------------+
|  core/ (Python puro, tipado estricto mypy, testeado pytest)   |
|    ├── units.py        Conversión exacta dmm <-> mm/cm/px/pt  |
|    ├── project.py      Esquema .layoutexpo + guardado atómico |
|    ├── geometry.py     Rects, anclajes, snap, colisiones      |
|    ├── homography.py   DLT 4-puntos + CSS matrix3d + tiling   |
|    ├── media.py        Ingesta JPEG/PNG/TIFF + ICC + proxies  |
|    └── pdf_export.py   Planos vectoriales + lista + cartelas  |
+---------------------------------------------------------------+
```
