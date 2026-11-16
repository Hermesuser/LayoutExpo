# Design System — LayoutExpo

Basado en **Apple Human Interface Guidelines** (Claridad, Deferencia, Profundidad), **Material Design 3** (roles de color semánticos) y **WCAG 2.2 AA**.

## 1. Tokens de Color (Estudio Neutro 18 %)

| Token CSS | Valor | Rol | Contraste verificado |
| :--- | :--- | :--- | :--- |
| `--surface-workspace` | `#1A1A1C` | Lienzo alrededor del muro | Base |
| `--surface-panel` | `#242426` | Paneles laterales y barra superior | Base |
| `--surface-elevated` | `#2E2E32` | Tarjetas, controles y popovers | Base |
| `--border-subtle` | `#3E3E44` | Separadores estructurales | — |
| `--border-strong` | `#6E6E77` | Bordes de inputs y botones secundarios | ≥ 3.3:1 sobre panel |
| `--text-primary` | `#F5F5F7` | Títulos, valores de cotas, etiquetas | ≥ 14:1 sobre panel |
| `--text-secondary` | `#B8B8BE` | Metadatos, ayudas, unidades | ≥ 6.8:1 sobre elevado |
| `--accent-primary` | `#4DA3FF` | Acción principal, selección activa | ≥ 5.8:1 sobre panel |
| `--on-accent-primary` | `#0A0A0C` | Texto/icono sobre botón acento | ≥ 7.5:1 sobre acento |
| `--state-snap` | `#30D158` | Guías de imán/alineación | Con línea discontinua |
| `--state-warning` | `#FFD60A` | Colisión, fuera de muro, foco | > 12:1 sobre oscuro |
| `--state-danger` | `#FF6961` | Error destructivo o archivo faltante | ≥ 5.5:1 sobre panel |
| `--focus-ring` | `#FFD60A` | Anillo de foco 2 px sólido + 2 px offset | > 12:1 |

## 2. Tokens del Modo Proyector (Sala)

| Token CSS | Valor | Uso |
| :--- | :--- | :--- |
| `--projector-bg` | `#000000` | Fondo negro puro (sin luz proyectada) |
| `--projector-white` | `#FFFFFF` | Muros oscuros o neutros |
| `--projector-cyan` | `#00E5FF` | Muros cálidos / madera |
| `--projector-green` | `#39FF14` | Muros grises / hormigón |
| `--projector-amber` | `#FFB300` | Muros blancos con luz ambiental |

Cada capa proyectada se distingue por **patrón geométrico además del color**:
- Contorno exterior (marco o borde directo): trazo continuo (`2 px`).
- Ventana de imagen (cuando hay passepartout): trazo discontinuo (`6 4`).
- Eje visual / nivel de horizonte: trazo punto-raya (`12 4 2 4`).
- Puntos de anclaje / perforación: cruz ortogonal (`+`) con círculo concéntrico.

## 3. Tipografía, Espaciado y Radios

- **Tipografía UI:** `-apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", system-ui, sans-serif`
- **Tipografía Cotas:** `"SF Mono", ui-monospace, "Cascadia Mono", Consolas, monospace` con `font-variant-numeric: tabular-nums`.
- **Escala:** `xs: 0.75rem`, `sm: 0.8125rem`, `base: 0.875rem`, `lg: 1.0625rem`, `xl: 1.25rem`.
- **Espaciado (base `4 px`):** `4, 8, 12, 16, 20, 24, 32 px`.
- **Radios:** `sm: 6px`, `md: 10px`, `lg: 14px` (en obra física dentro del lienzo: `0px`).
- **Objetivos interactivos:** mínimo `36×36 px` en inspector denso; `44×44 px` en acciones primarias y calibrador de proyector.
- **Movimiento:** `150ms cubic-bezier(0.2, 0, 0, 1)`; `0ms` bajo `prefers-reduced-motion: reduce`.
