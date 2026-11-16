# ADR-001: Stack Multiplataforma Nativo (Shell OS + Motor Python)

- **Estado:** Aprobado (Fase 0 / Fase 1)
- **Fecha:** 2026-11-14

## Contexto
LayoutExpo debe ejecutarse de forma 100 % local y offline de manera nativa en:
- macOS Apple Silicon (`arm64`)
- macOS Intel (`x86_64`)
- Windows (`x64`)

Además, requiere salida dual de pantalla (Estudio + Proyector multimedia fullscreen), precisión métrica vectorial en PDF, lectura fiable de `JPEG`/`PNG`/`TIFF` con perfiles ICC y cumplimiento verificable de WCAG 2.2 AA.

## Decisión
Adoptar una arquitectura desacoplada con:
1. **Motor de dominio y exportación en Python (`>=3.11`)**: `core/` puro para geometría y homografía; `Pillow` para ingesta de imágenes/proxies; `ReportLab` para PDF vectorial exacto.
2. **Servidor local loopback (`127.0.0.1`)** con puerto efímero, token de sesión único y Content Security Policy (CSP) estricta sin recursos externos.
3. **Launcher nativo multi-ventana (`desktop/`)**: `pywebview` sobre `Cocoa / WKWebView` en macOS (`arm64` y `x86_64`) y `Edge WebView2` High-DPI en Windows 11.
4. **Interfaz web local (`ui/`)**: HTML/CSS/JS modular sin frameworks pesados, tokens semánticos y auditoría automatizada WCAG 2.2 AA (`axe-core`).

## Alternativas descartadas
- **Swift / SwiftUI / AppKit exclusivo:** imposible compilar o ejecutar en Windows.
- **PySide6 / Qt 6:** mayor peso de distribución, complejidad adicional en accesibilidad de canvas y licencia LGPLv3 a gestionar.
- **Tauri / Rust:** requiere toolchain Rust no instalado actualmente y duplica librerías maduras de PDF/TIFF ya disponibles en Python.

## Consecuencias
- Requiere aislar toda lógica de negocio en `core/` sin acoplarla al transporte HTTP ni al DOM.
- Permite compartir estrategia de empaquetado/notarización entre `macOS arm64`, `macOS x86_64` y `Windows x64`.
