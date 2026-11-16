# ADR-002: Unidades Exactas en Décimas de Milímetro (`dmm`) y Origen Arquitectónico

- **Estado:** Aprobado (Fase 1)
- **Fecha:** 2026-11-14

## Contexto
En montaje museográfico y de galerías, las cotas físicas se miden en centímetros y milímetros (`cm` / `mm`). Usar números de punto flotante (`float`) en el modelo de dominio introduce errores acumulativos de redondeo (`0.1 + 0.2 != 0.3`), rompe comparaciones de alineación y genera cotas imprecisas en planos PDF y proyección.

## Decisión
1. **Unidad interna única:** Toda dimensión, coordenada, margen, marco, passepartout y anclaje se almacena y opera como **entero en décimas de milímetro (`dmm`)**, donde `1 mm = 10 dmm` y `1 cm = 100 dmm`.
2. **Sistema de coordenadas del muro:** Origen `(0, 0)` en la **esquina inferior izquierda del muro**; `+X` hacia la derecha y `+Y` hacia arriba (desde el nivel del suelo).
3. **Conversiones externas:** La conversión a `cm`/`mm` para la UI, a píxeles de lienzo o a puntos Tipográficos PDF (`1 mm = 72 / 25.4 pt`) ocurre exclusivamente en las capas de frontera (`core/units.py`, `ui/`, `core/pdf_export.py`).

## Consecuencias
- Cero deriva numérica al alinear, distribuir o recalcular anclajes.
- Coincidencia directa con la medición física con cinta métrica en sala (desde suelo y esquina izquierda) y con el sistema cartesiano de `ReportLab`.
