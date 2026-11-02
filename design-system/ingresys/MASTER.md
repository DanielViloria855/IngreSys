# ingreSys · Design System (versión corporativa)

> Reemplaza la primera propuesta (azul + naranja, Fira Code en títulos), que resultó demasiado «de plantilla».
> Referencia de la skill ui-ux-pro-max: estilo tokenizado tipo Spectrum (jerarquía precisa, controles densos pero legibles, foco visible, movimiento mínimo) y tipografía «Financial Trust» (IBM Plex Sans).

## Principios
1. **Sobrio y plano**: bordes de 1 px, radios de 3–4 px, sin sombras decorativas, sin degradados, sin animaciones de entrada ni hover con elevación.
2. **Una sola gama de color**: azul corporativo + grises neutros. Rojo/ámbar/verde solo para estado (error, atención, correcto), siempre acompañados de texto.
3. **Texto antes que adorno**: sin íconos decorativos en botones, etiquetas ni encabezados; sin chips con fondo de color en íconos; sin marketing en pantallas de trabajo.
4. **Datos legibles**: números tabulares; placas y códigos de contenedor en IBM Plex Mono (único uso de monoespaciada).
5. **Tablet primero**: objetivos táctiles ≥ 44 px, una columna en el formulario, tabla con scroll interno.

## Tokens
| Rol | Valor | Variable |
|---|---|---|
| Fondo | `#F3F4F6` | `--c-bg` |
| Superficie | `#FFFFFF` / `#F7F8FA` | `--c-surface` / `--c-surface-2` |
| Texto | `#1F2933` / `#566070` | `--c-ink` / `--c-ink-2` |
| Borde | `#D9DDE3` / `#B4BBC6` | `--c-line` / `--c-line-strong` |
| Primario | `#1F4E79` (hover `#173B5C`) | `--c-primary` |
| Cabecera | `#14283D` | `--c-header` |
| Correcto | `#1E6B3F` sobre `#E6F2EA` | `--c-success` |
| Atención | `#8A5A00` sobre `#FCF3DC` | `--c-warning` |
| Error | `#A4261C` sobre `#FBE9E7` | `--c-danger` |

Contraste de texto ≥ 4.5:1 en todas las combinaciones.

## Tipografía
- **IBM Plex Sans** 400/500/600: interfaz completa. Títulos 600, h1 1.5 rem, cuerpo 15 px.
- **IBM Plex Mono**: solo placa, contenedor, usuario y documento.

## Componentes
- **Cabecera**: barra oscura fija con la marca en texto, navegación por texto (subrayado en la sección activa), botón «Nuevo ingreso» con borde blanco y menú de usuario en texto.
- **Indicadores**: una franja única dividida en celdas (título, cifra, nota); el estado de atención cambia el color de la cifra y añade una nota de texto.
- **Formulario dinámico**: una ficha con filas separadas por una línea; etiquetas arriba; Sí/No y opciones como botones rectangulares con selección en azul suave.
- **Tablas**: encabezado gris, filas de 1 línea, enlace en la placa (fila completa clicable), estado como etiqueta rectangular de texto.
- **Análisis automático**: lista de filas con nivel en texto (Alerta · Atención · Información), sin tarjetas de color.
- **Gráficos**: un azul principal y azul claro; ámbar solo para novedades; sin leyendas redundantes.

## Accesibilidad
Foco visible (2 px azul), etiquetas visibles, errores junto al campo, `prefers-reduced-motion` respetado, estado nunca solo por color.
