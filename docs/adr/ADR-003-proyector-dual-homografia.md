# ADR-003: Modo Proyector Dual-Screen con Homografía 2D (4 Puntos) y Tiling por Tramos

- **Estado:** Aprobado (Fase 1)
- **Fecha:** 2026-11-14

## Contexto
Durante el montaje físico en sala, el fotógrafo o montajista conecta un proyector multimedia al equipo para proyectar las guías de colgado (marcos, eje visual y cruces de anclaje) directamente sobre la pared real. Sin calibración, la escala proyectada depende de la distancia de tiro del proyector y sufre deformación trapezoidal (*keystone*) si no está perpendicular al muro. Además, un muro largo puede exceder el ancho cubierto por el proyector.

## Decisión
1. **Ventana Dual Independiente:** La app abre una ventana de **Estudio** (en pantalla del operador) y una ventana de **Proyector** (*borderless fullscreen* en pantalla secundaria, fondo `#000000`).
2. **Calibración mediante Homografía DLT (4 puntos):** El operador proyecta un rectángulo patrón o define 4 puntos de referencia conocidos en el muro (`cm`); `core/homography.py` resuelve la matriz proyectiva `3×3` exacta en Python puro (`dmm -> espacio normalizado proyector` y `CSS matrix3d`) para compensar escala y *keystone*.
3. **Proyección por tramos (*Wall Tiling*):** Se soporta proyectar una ventana parcial del muro (`viewport_x_dmm`, `viewport_width_dmm`) con marca de origen para muros más anchos que el tiro del proyector.
4. **Capas independientes:** En proyección se pueden activar/desactivar contornos, ventana de imagen, eje visual, cruces de clavos/tornillos y vista fantasma de la foto.

## Consecuencias
- No depende de cámaras externas ni sensores LiDAR en el MVP.
- La precisión física depende de la correcta medición de los 4 puntos de referencia por parte del operador en sala.
