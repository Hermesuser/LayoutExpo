# ADR-006: Motor Heurístico Determinista de Reorganización Armónica y Compositiva

- **Estado:** Aprobado (V2.1)
- **Fecha:** 2026-11-14

## Contexto
El curador o fotógrafo necesita reorganizar automáticamente las obras en uno o varios muros aplicando criterios museográficos profesionales: punto focal (Pieza Ancla), alternancia de ritmo visual, compensación de pesos ópticos (constelaciones 2×1 y *gutters* proporcionales) y respeto a márgenes perimetrales de `50 cm`, preservando bloqueos manuales (`Placement.locked`) y generando justificaciones transparentes.

## Decisión
1. **Motor heurístico determinista en Python puro (`core/curation.py`):** 100 % local y offline, operando exclusivamente en enteros `dmm` ([ADR-002](ADR-002-unidades-exactas-dmm.md)) sin mutar el objeto de entrada.
2. **Clasificación física exterior:** La orientación (`V`, `H`, `C` con relación `0.90 ≤ ancho/alto ≤ 1.10`) y el peso visual (área física `ancho × alto`) se evalúan sobre el tamaño exterior real en el muro (incluyendo marco y passepartout).
3. **Constelaciones 2×1 y momento óptico:** Cuando existen obras secundarias pequeñas compatibles en altura y una obra pesada genera desequilibrio, el algoritmo puede agrupar un par vertical `2×1` como bloque compositivo y pondera *gutters* alrededor de piezas pesadas para minimizar el desequilibrio de momento respecto al centro del muro.
4. **Degradación segura con trazabilidad:** Las piezas con `locked=True` se preservan como anclas fijas. Si un muro es demasiado estrecho para mantener `50 cm` por extremo o el inventario carece de alternancia estricta, se prioriza evitar solapamientos y se informa la excepción en `rationale[]` / `warnings[]`.

## Consecuencias
- Retrocompatibilidad completa con proyectos `.layoutexpo` de `schema_version = 1` mediante valores por defecto (`Artwork.is_anchor = False`, `Wall.narrative_role = "standard"`).
- Reproducible al 100 % en pruebas unitarias y reversible en un paso con la pila de Deshacer (`Cmd/Ctrl+Z`).
