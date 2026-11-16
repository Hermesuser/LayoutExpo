# ADR-004: Formato de Proyecto `.layoutexpo` No Destructivo y Versionado

- **Estado:** Aprobado (Fase 1)
- **Fecha:** 2026-11-14

## Contexto
Los fotógrafos trabajan con archivos maestros pesados (`TIFF`, `PNG`, `JPEG`) que nunca deben ser alterados, sobreescritos ni duplicados innecesariamente. Al mismo tiempo, un corte de energía o cierre inesperado no debe corromper el diseño de la exposición.

## Decisión
1. **Flujo 100 % no destructivo:** Las imágenes originales se leen exclusivamente en modo lectura. La app genera proxies sRGB ligeros en caché local preservando orientación EXIF y conversión ICC.
2. **Persistencia atómica:** El archivo de proyecto `.layoutexpo` (JSON UTF-8 con `schema_version: 1`) se guarda escribiendo primero a un archivo temporal en el mismo directorio, aplicando `fsync` y reemplazando atópicamente con `os.replace`.
3. **Integridad de referencias:** Cada obra guarda `source_path` y `sha256` opcional para detectar archivos movidos y permitir relocalización segura.

## Consecuencias
- Protección total ante corrupción parcial de disco al guardar.
- Migraciones futuras explícitas y auditables mediante `schema_version`.
