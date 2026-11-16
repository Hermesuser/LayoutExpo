# ADR-005: Design System Dual-Ambiente (Estudio Neutro 18 % y Proyector `#000000`)

- **Estado:** Aprobado (Fase 1)
- **Fecha:** 2026-11-14

## Contexto
La interfaz del Estudio acompaña la curaduría visual de fotografías, por lo que colores saturados en los paneles distorsionan la percepción cromática (Principio de **Deferencia** de Apple HIG). Por otro lado, la ventana de Proyector opera en sala frente a muros físicos reales.

## Decisión
1. **Estudio en Gris Neutro Acromático:** Superficies neutras (`#1A1A1C`, `#242426`, `#2E2E32`) con tokens semánticos verificados a ≥ 4.5:1 para texto y ≥ 3:1 para bordes y estados de foco.
2. **Proyector en Negro Puro (`#000000`):** Minimiza emisión de luz residual sobre el muro; líneas de guía de alto contraste seleccionables (Blanco, Cian, Verde Láser, Ámbar) diferenciadas también por **patrón de trazo** (continuo, discontinuo, punto-raya, cruz) para cumplir WCAG 2.2 AA (no depender solo del color).
3. **Accesibilidad obligatoria:** Foco visible (`#FFD60A`, 2 px), tipografía del sistema, `tabular-nums` en toda cota métrica, soporte completo de teclado (`1 mm` / `1 cm`) y respeto a `prefers-reduced-motion`.

## Consecuencias
- Todas las pantallas deben consumir variables CSS definidas en `ui/tokens.css` sin colores hex hardcodeados en componentes.
