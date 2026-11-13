# Diseño del dashboard

Vista general de FríoTrack, mobile-first, con datos simulados que respetan la
forma de [docs/contrato-api.md](../docs/contrato-api.md). Todavía no hay API,
login, SSE ni router: esta entrega es solo de interfaz.

## Referencias y qué se tomó de cada una

| Referencia | Lo que se aplicó                                                                  |
| ---------- | --------------------------------------------------------------------------------- |
| Apple      | Whitespace generoso, jerarquía tipográfica clara y movimiento casi imperceptible. |
| Duolingo   | Banner de bienvenida breve y amable, dismissible, sin tono infantil.              |
| Linear     | Bordes finos, tipografía compacta, elevación sutil y estados de foco nítidos.     |
| Pentagram  | Wordmark y títulos de sección en serif local, con carácter editorial.             |
| Muji       | Fondo cálido, cero decoración, mucho aire y una sola paleta neutra.               |
| Airbnb     | Chips de filtro y búsqueda por cámara, sin convertirlo en un catálogo.            |
| Aesop      | Colores apagados, contraste suave y jerarquía por tamaño, no por saturación.      |
| Notion     | Bloques ordenados: resumen, cámaras y seguridad en secciones separadas.           |
| Stripe     | Acabado pulido y sombras discretas; sin gradientes llamativos.                    |
| Framer     | Hover de 1 px, press de botones y respeto a `prefers-reduced-motion`.             |

## Paleta

Variables en `src/index.css`.

| Token                       | Valor                 | Uso                                                 |
| --------------------------- | --------------------- | --------------------------------------------------- |
| `--bg`                      | `#F6F4EF`             | Fondo de página, papel cálido.                      |
| `--surface`                 | `#FFFDF9`             | Tarjetas y header translúcido.                      |
| `--surface-2`               | `#F0EDE6`             | Hover y bloques secundarios.                        |
| `--ink`                     | `#1B1A18`             | Texto principal.                                    |
| `--muted`                   | `#6E6A63`             | Metadatos y texto secundario (AA sobre surface).    |
| `--line`                    | `#E4DED2`             | Bordes de 1 px.                                     |
| `--accent`                  | `#145C57`             | Verde profundo para marca, chips activos y foco.    |
| `--accent-soft`             | `#E3EFEC`             | Fondos de apoyo y banda de la sparkline.            |
| `--ok` / `--ok-ink`         | `#2F7A57` / `#246246` | Cámara en rango.                                    |
| `--warn` / `--warn-ink`     | `#B26B1A` / `#8A4E0F` | Alerta, puerta abierta y valor en riesgo.           |
| `--danger` / `--danger-ink` | `#B3261E` / `#8F1D18` | Estado crítico (Pescados ya tiene lotes en riesgo). |

Los estados nunca dependen solo del color: cada tarjeta lleva la palabra
"En rango", "Alerta" o "Crítica" junto al punto.

## Tipografía

- **UI:** sans del sistema (`-apple-system`, Segoe UI, Roboto, Arial). Sin
  fuentes externas ni descargas.
- **Wordmark y títulos de sección:** serif local (Iowan Old Style, Palatino,
  Georgia) definida en `--font-display`. El punto del wordmark usa el verde de
  acento.
- **Números:** `font-variant-numeric: tabular-nums` en temperaturas, KPIs y
  tiempos para evitar saltos de ancho.
- **Labels:** mayúsculas de 10–11 px, tracking amplio y color `--muted`.

## Layout

- Ancho máximo de 1180 px, con padding de 16 px en móvil, 24 px en tablet y
  32 px en desktop.
- Header sticky con `backdrop-filter`; en móvil el subtítulo se oculta y la
  metadata pasa a una segunda línea sin desbordar.
- KPIs: 2 columnas en móvil, 3 en tablet (≥720 px) y 6 en desktop (≥1024 px).
- Cámaras: 1 columna, 2 desde 640 px y 3 desde 1024 px.
- Filtros en columna en móvil y en fila desde 760 px.
- Grids con `minmax(0, 1fr)` para que un texto largo nunca abra scroll
  horizontal. Revisado a 360 px, 768 px y 1280 px.

## Movimiento

- Transiciones de 160–220 ms con `--ease` (curva suave de salida).
- Hover lift de 1 px y sombra un poco más alta en tarjetas.
- Press de 0.94–0.98 en botones; nunca animación decorativa en bucle.
- Foco visible con outline de 2 px y `offset: 2px`.
- `@media (prefers-reduced-motion: reduce)` reduce transiciones y anula
  desplazamientos.

## Decisiones

- **Datos mock con forma de contrato.** `src/data/mock.ts` usa los campos de
  `GET /camaras` y `GET /kpis`. Las series de la sparkline van aparte porque
  `GET /camaras` no las incluye; en la versión conectada saldrán de
  `GET /camaras/{id}/lecturas`.
- **Reloj fijo de demo** (`AHORA_DEMO`) para que los "hace X" sean estables en
  pruebas y capturas. No hay temporizador ni polling.
- **Header con props de demo y sesión.** `escalaTiempo` (que vendrá de
  `GET /health`) oculta la pill cuando vale 1 o no está definido, e `iniciales`
  tiene default "JC" hasta que exista login.
- **Sparkline SVG propia:** 24 puntos, polyline, banda del rango permitido y
  punto final. Sin librerías de gráficas.
- **Filtros locales.** Chips con `aria-pressed`, conteos derivados del mock y
  búsqueda normalizada (ignora acentos y mayúsculas). El estado vive en `App`
  para que el conteo visible y el anuncio `role="status"` coincidan.
- **Onboarding dismissible** con `localStorage` tolerante a fallos. Solo es un
  aviso; no bloquea la vista.
- **Seguridad** usa la forma de la tabla `alertas_seguridad` (`regla`,
  `severidad`, `detalle` y `accion`). El panel deriva el título de `regla`, el
  tono de `severidad`, la etiqueta de `accion` y el resumen de `detalle`.
- **Sin dependencias nuevas.** React y Vite bastan; el resto es CSS y SVG.
