# Layout Optimization Concept (v3 -- zen mode)

## Current Layout (from screenshot)

```
┌──────────────────────────────────────────────────────────────────────┐
│  ● TELEMETRY CONSOLE     [Connect][Record][Pause][LIVE]   V: R: S: │  ~56px tall
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │  Live Camera                                            H264  │  │ panel header ~48px
│  │  WebRTC low-latency feed                                      │  │
│  │  ┌──────────────────────────────────────────────────────────┐  │  │
│  │  │                                                          │  │  │
│  │  │               VIDEO STREAM  (260px min)                  │  │  │ ~260px
│  │  │               Disconnected                               │  │  │
│  │  │                                                          │  │  │
│  │  └──────────────────────────────────────────────────────────┘  │  │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐          │  │
│  │  │ CAPTURE TIME │ │ FRAME RATE   │ │ LATENCY      │          │  │ metrics ~64px
│  │  │ --:--:--     │ │ -- fps       │ │ -- ms        │          │  │
│  │  └──────────────┘ └──────────────┘ └──────────────┘          │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                      │  gap 24px
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │  Trajectory + 3D Model                                 RERUN  │  │ panel header ~48px
│  │  Rerun split view                                             │  │
│  │  ┌──────────────────────────────────────────────────────────┐  │  │
│  │  │                                                          │  │  │
│  │  │  ┌─── Trajectory ───┐ ┌── 3D Visual ── 3D Collision ─┐  │  │  │
│  │  │  │  sin / cos waves  │ │   robot URDF model           │  │  │  │ fills remaining
│  │  │  │                   │ │                               │  │  │  │
│  │  │  └───────────────────┘ └───────────────────────────────┘  │  │  │
│  │  │                                                          │  │  │
│  │  └──────────────────────────────────────────────────────────┘  │  │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐          │  │
│  │  │ TIMELINE     │ │ DATA RATE    │ │ ENTITIES     │          │  │ metrics ~64px
│  │  │ Wall time    │ │ -- msg/s     │ │ --           │          │  │
│  │  └──────────────┘ └──────────────┘ └──────────────┘          │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                      │
├──────────────────────────────────────────────────────────────────────┤
│  TIMELINE   ════════════════●══════════   00:00:00 · LIVE MODE      │  ~52px tall
└──────────────────────────────────────────────────────────────────────┘
```

**Vertical space overhead on 1080p (~468px, 43% of screen):**

| Element              | Current height | Notes                           |
|----------------------|----------------|---------------------------------|
| TopBar               | ~56px          | Large padding, 3-column grid    |
| Main-grid padding    | ~56px          | 1.5rem top + 2rem bottom        |
| Panel padding x2     | ~56px          | 1.4rem x2 panels x top+bottom   |
| Panel headers x2     | ~96px          | h2 + subtitle per panel         |
| Video metrics row    | ~64px          | 3 large metric cards            |
| Rerun metrics row    | ~64px          | 3 large metric cards            |
| Gap between panels   | ~24px          | grid gap                        |
| TimelineBar          | ~52px          | Full-width footer               |
| **Total overhead**   | **~468px**     | On 1080p that's ~43% of screen! |

---

## Three display modes

The UI has three progressive density levels. **Zen** is the default.

| Mode        | What's visible                                      | Chrome overhead | Toggle                  |
|-------------|-----------------------------------------------------|-----------------|-------------------------|
| **Zen**     | Camera + Rerun content only, floating status dot    | ~12px (2 gaps)  | Default on load         |
| **Compact** | + slim topbar, inline metrics, slim timeline        | ~108px          | `Z` key or hover-reveal |
| **Focus**   | Single panel fills viewport + slim topbar/timeline  | ~72px           | `⤢` button or `F` key  |

State machine: `Zen ↔ Compact ↔ Focus` (Zen cannot go directly to Focus)

```
         Z / hover                 ⤢ / F
  ┌─────┐ ────────▶ ┌─────────┐ ────────▶ ┌───────┐
  │ ZEN │            │ COMPACT │            │ FOCUS │
  └─────┘ ◀──────── └─────────┘ ◀──────── └───────┘
         Z / idle 3s               Esc / ⤡
```

---

## Mode 1: Zen (default)

Pure content. No topbar, no metrics, no timeline. Just camera and rerun with a
tiny floating status indicator and an invisible hover zone to reveal controls.

```
┌──────────────────────────────────────────────────────────────────────┐
│ ┌──────────────────────────────────────────────────────────────────┐ │
│ │                                                                  │ │
│ │                       VIDEO  STREAM                              │ │  max 35vh
│ │                       Disconnected                               │ │  min 180px
│ │                                                                  │ │
│ └──────────────────────────────────────────────────────────────────┘ │
│ ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄  resize handle  ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄ │  4px
│ ┌──────────────────────────────────────────────────────────────────┐ │
│ │                                                                  │ │
│ │  ┌─── Trajectory ───┐ ┌──── 3D Visual ──── 3D Collision ────┐   │ │
│ │  │                   │ │                                      │   │ │
│ │  │   sin / cos       │ │         robot URDF                   │   │ │  flex: 1 (ALL remaining)
│ │  │                   │ │                                      │   │ │
│ │  └───────────────────┘ └──────────────────────────────────────┘   │ │
│ │                                                                  │ │
│ └──────────────────────────────────────────────────────────────────┘ │
│                                                              ● LIVE │  floating dot, bottom-right
└──────────────────────────────────────────────────────────────────────┘
```

### Zen details

- **No topbar, no timeline, no panel headers, no metrics**
- Panels render edge-to-edge with `0.5rem` outer margin, `0.5rem` gap
- **Floating status dot** -- bottom-right corner, 8px accent circle
  - Green pulse = connected, amber = connecting, red = error, gray = idle
  - Hover the dot: tooltip shows `V: Connected  R: Streaming  00:01:23`
- **Hover zone** -- invisible 60px strip at top edge of viewport
  - Mouse enters → topbar slides down (150ms ease-out)
  - Mouse leaves topbar → topbar slides up after 400ms delay
  - This lets you access Connect/Record/Pause without leaving zen
- **Panel borders**: removed -- just content on the dark background
  - No `panel` class styling (no border, no bg, no shadow, no gradient overlay)
  - Just the media areas (video element + rerun iframe) directly
- **Resize handle**: still present but nearly invisible (1px border-color line)
  - Shows `cursor: row-resize` on hover, dims slightly brighter
- Keyboard: `Z` toggles to Compact mode

### Zen space budget (1080px viewport)

```
margin top:      8px   (0.5rem)
camera:         ~378px (35vh)
resize gap:      8px   (0.5rem)
rerun:          ~678px (all remaining)
margin bottom:   8px   (0.5rem)
─────────────────────
total:          1080px
content:        1056px → 97.8% of viewport is camera + rerun
```

---

## Mode 2: Compact (toggle from zen)

Slim controls revealed. This is the operational mode when you need status info,
recording controls, or to see metrics while still keeping content maximized.

```
┌──────────────────────────────────────────────────────────────────────┐
│ ● TELEMETRY  [Connect][Rec][Pause][LIVE]        V:--  R:Idle  S:-- │  40px (slim topbar)
├──────────────────────────────────────────────────────────────────────┤
│ ┌──────────────────────────────────────────────────────────────────┐ │
│ │ CAM  H264         --:--:-- │ -- fps │ -- ms               [ ⤢ ]│ │  28px compact header
│ │ ┌────────────────────────────────────────────────────────────┐   │ │
│ │ │                                                            │   │ │
│ │ │                    VIDEO  STREAM                           │   │ │  max 35vh
│ │ │                    Disconnected                            │   │ │  min 180px
│ │ │                                                            │   │ │
│ │ └────────────────────────────────────────────────────────────┘   │ │
│ └──────────────────────────────────────────────────────────────────┘ │
│ ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄  resize handle  ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄ │  4px drag divider
│ ┌──────────────────────────────────────────────────────────────────┐ │
│ │ RERUN             Wall time │ -- msg/s │ --               [ ⤢ ]│ │  28px compact header
│ │ ┌────────────────────────────────────────────────────────────┐   │ │
│ │ │                                                            │   │ │
│ │ │  ┌─── Trajectory ───┐ ┌── 3D Visual ── 3D Collision ──┐   │   │ │
│ │ │  │                   │ │                                │   │   │ │  flex: 1 (ALL remaining)
│ │ │  │   sin / cos       │ │      robot URDF               │   │   │ │
│ │ │  │                   │ │                                │   │   │ │
│ │ │  └───────────────────┘ └────────────────────────────────┘   │   │ │
│ │ │                                                            │   │ │
│ │ └────────────────────────────────────────────────────────────┘   │ │
│ └──────────────────────────────────────────────────────────────────┘ │
├──────────────────────────────────────────────────────────────────────┤
│ ════════════════════════════●════════════════   00:00:00 · LIVE     │  28px (slim timeline)
└──────────────────────────────────────────────────────────────────────┘
```

### Compact details

- **TopBar** -- 40px, slim controls, borderless status text
- **Panel headers** -- 28px inline bars: title chip + metrics text + maximize icon
- **TimelineBar** -- 28px, no label, just the scrubber track + time meta
- **Panel styling restored** -- border, translucent bg, shadow, gradient overlay
- **Resize handle active** -- visible 1px line, draggable, `localStorage` persisted
- Keyboard: `Z` returns to Zen, `F` or `⤢` enters Focus mode

### Compact space budget (1080px viewport)

```
topbar:          40px
panel padding:   12px  (0.75rem top)
cam header:      28px
camera:         ~320px (capped 35vh minus overhead)
panel padding:   12px  (0.75rem bottom)
gap:              8px
panel padding:   12px  (0.75rem top)
rerun header:    28px
rerun:          ~540px (flex: 1, all remaining)
panel padding:   12px  (0.75rem bottom)
timeline:        28px
─────────────────────
content:        ~860px (camera ~320 + rerun ~540) → 80% of viewport
chrome:         ~220px → 20%
```

---

## Mode 3: Focus (maximize single panel)

One panel fills the entire content area. Topbar and timeline stay visible
so you keep controls and playback position.

```
┌──────────────────────────────────────────────────────────────────────┐
│ ● TELEMETRY  [Connect][Rec][Pause][LIVE]        V:--  R:Idle  S:-- │  40px
├──────────────────────────────────────────────────────────────────────┤
│ ┌──────────────────────────────────────────────────────────────────┐ │
│ │ RERUN             Wall time │ -- msg/s │ --               [ ⤡ ]│ │  28px
│ │ ┌────────────────────────────────────────────────────────────┐   │ │
│ │ │                                                            │   │ │
│ │ │                                                            │   │ │
│ │ │  ┌─── Trajectory ───┐ ┌── 3D Visual ── 3D Collision ──┐   │   │ │
│ │ │  │                   │ │                                │   │   │ │
│ │ │  │   sin / cos       │ │      robot URDF               │   │   │ │  fills ENTIRE content area
│ │ │  │                   │ │                                │   │   │ │
│ │ │  └───────────────────┘ └────────────────────────────────┘   │   │ │
│ │ │                                                            │   │ │
│ │ │                                                            │   │ │
│ │ └────────────────────────────────────────────────────────────┘   │ │
│ └──────────────────────────────────────────────────────────────────┘ │
├──────────────────────────────────────────────────────────────────────┤
│ ════════════════════════════●════════════════   00:00:00 · LIVE     │  28px
└──────────────────────────────────────────────────────────────────────┘
```

### Focus details

- Clicked panel fills `position: fixed; inset: 40px 0 28px 0; z-index: 20;`
- Other panel: `display: none`
- `⤢` icon changes to `⤡` (restore)
- Keyboard: `Escape` or `⤡` returns to Compact; `F` toggles
- Transition: 150ms ease-out on opacity + scale(0.98 → 1)

### Focus space budget (1080px)

```
topbar:          40px
panel padding:   12px
panel header:    28px
content:        ~944px (single panel)
panel padding:   12px
timeline:        28px
─────────────────────
content:        ~944px → 87% of viewport
```

---

## Space comparison across all modes (1080px)

| Mode        | Camera px | Rerun px  | Content total | Chrome % |
|-------------|-----------|-----------|---------------|----------|
| **Current** | ~260px    | ~410px    | ~670px        | 38%      |
| **Zen**     | ~378px    | ~678px    | ~1056px       | 2%       |
| **Compact** | ~320px    | ~540px    | ~860px        | 20%      |
| **Focus**   | --        | ~944px    | ~944px        | 13%      |

---

## Component-by-component spec

### 1. Mode State (new -- React context)

```tsx
type DisplayMode = "zen" | "compact" | "focus";
type FocusTarget = "camera" | "rerun" | null;

interface LayoutState {
  mode: DisplayMode;
  focusTarget: FocusTarget;
  splitRatio: number;        // 0–1, persisted in localStorage
}
```

- Stored in a `LayoutContext` provider at the `App` level
- `splitRatio` default: `0.35` (35vh for camera)
- `mode` default: `"zen"`
- Persisted: `splitRatio` in `localStorage`, `mode` resets to `zen` on load

### 2. TopBar (compact mode only, auto-hides in zen)

```
┌──────────────────────────────────────────────────────────────────────┐
│ ● TELEMETRY   [Connect][Rec][⏸][LIVE]              V:--  R:Idle [Z]│
└──────────────────────────────────────────────────────────────────────┘
```

- Height: **40px**
- Padding: `0.5rem 1rem`
- Brand: `● TELEMETRY` -- Unbounded 0.8rem
- Buttons: padding `0.35rem 0.9rem`, font-size `0.62rem`
- Status pills: **borderless**, colored mono text
- **Zen toggle `[Z]`** -- far right, small icon button to return to zen
- Grid: `auto 1fr auto auto` (brand | controls | status | zen-toggle)
- **Zen behavior**: hidden by default; slides in from top on hover (60px trigger zone)
  - `transform: translateY(-100%)` → `translateY(0)` over 150ms

### 3. Video Panel

**Zen mode** -- no panel chrome, just the video area:

```
┌────────────────────────────────────────────────────────────────┐
│                                                                │
│                     VIDEO  STREAM                              │  bare content
│                     Disconnected                               │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

- No border, no background, no shadow, no gradient overlay
- Just the `.media-placeholder` / video element
- Rounded corners: `8px` (subtle, content-only)

**Compact mode** -- panel with inline header:

```
┌──────────────────────────────────────────────────────────────────┐
│ CAM  H264         --:--:-- │ -- fps │ -- ms               [ ⤢ ] │  28px
│ ┌────────────────────────────────────────────────────────────┐   │
│ │              video / placeholder                           │   │  min 180px, max 35vh
│ └────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

- **Header row** -- 28px flex line
  - Left: `CAM` chip (Unbounded 0.7rem, accent border) + `H264` (muted)
  - Right: inline metrics `--:--:-- │ -- fps │ -- ms`
  - Far right: maximize `⤢`
- Panel: border, translucent bg, shadow, gradient overlay restored
- Padding: `0.75rem`, border-radius: `14px`

### 4. Rerun Panel

**Zen mode** -- bare iframe:

```
┌────────────────────────────────────────────────────────────────┐
│                                                                │
│  ┌─── Trajectory ───┐ ┌── 3D Visual ── 3D Collision ──┐       │  bare content
│  │                   │ │                                │       │
│  └───────────────────┘ └────────────────────────────────┘       │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

- No panel chrome, just the iframe
- Rounded corners: `8px`

**Compact mode** -- panel with inline header:

```
┌──────────────────────────────────────────────────────────────────┐
│ RERUN             Wall time │ -- msg/s │ --               [ ⤢ ] │  28px
│ ┌────────────────────────────────────────────────────────────┐   │
│ │              rerun iframe                                  │   │  flex: 1
│ └────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

### 5. TimelineBar (compact/focus only)

```
┌──────────────────────────────────────────────────────────────────────┐
│ ══════════════════════════════●═══════════════   00:00:00 · LIVE    │
└──────────────────────────────────────────────────────────────────────┘
```

- Height: **28px**, padding `0.3rem 1rem`
- Hidden in zen mode
- Track spans full width, thumb 14px

### 6. Floating Status Dot (zen only)

```
                                                               ● LIVE
```

- Position: `fixed`, bottom-right, `1rem` inset
- 8px circle with accent glow (matches brand-mark style)
- Color reflects aggregate status: green/amber/red/gray
- Hover → tooltip: `V: Connected  R: Streaming  00:01:23`
- Click → enters compact mode
- Pulse animation: `scale(1) → scale(1.3) → scale(1)` every 2s when streaming
- `pointer-events: auto` on a `pointer-events: none` container (non-intrusive)

### 7. Resize Handle

- 4px hit-area, visual: 1px `border-color` line
- `cursor: row-resize` on hover
- Drag adjusts camera/rerun split
- `localStorage` persistence of `splitRatio`
- Double-click: reset to 0.35 default
- Works in both zen and compact modes

### 8. Hover Trigger Zone (zen only)

- Invisible `div`, `position: fixed; top: 0; left: 0; right: 0; height: 60px;`
- `pointer-events: auto`, `z-index: 30`
- Mouse enter: topbar slides in (150ms), starts 400ms leave timer
- Mouse inside topbar: cancel leave timer
- Mouse leaves topbar + zone: topbar slides out after 400ms

---

## Keyboard shortcuts

| Key       | Action                                              |
|-----------|-----------------------------------------------------|
| `Z`       | Toggle between Zen ↔ Compact                        |
| `F`       | Toggle Focus mode (from Compact only)               |
| `Escape`  | Exit Focus → Compact, or exit Compact → Zen         |
| `1`       | Focus camera panel (from Compact)                   |
| `2`       | Focus rerun panel (from Compact)                    |

Shortcuts are disabled when any `<input>`, `<textarea>`, or `contenteditable` is focused.

---

## CSS token changes

```css
:root {
  /* Compact spacing */
  --spacing-panel:    0.75rem;   /* was 1.4rem */
  --spacing-grid-gap: 0.5rem;   /* was 1.5rem */
  --radius-panel:     14px;     /* was 20px */
  --radius-zen:       8px;      /* bare content corners in zen */

  /* Element heights */
  --topbar-h:         40px;
  --timeline-h:       28px;
  --panel-header-h:   28px;

  /* Zen-specific */
  --zen-margin:       0.5rem;   /* outer edge margin */
  --zen-gap:          0.5rem;   /* gap between panels */

  /* Transitions */
  --transition-mode:  150ms ease-out;  /* mode switches */
  --transition-hover: 400ms;           /* hover reveal delay */

  /* Existing tokens preserved */
  --panel, --panel-translucent, --border, --accent, etc.
}
```

## Responsive behavior

| Breakpoint  | Zen                          | Compact                                    | Focus           |
|-------------|------------------------------|--------------------------------------------|-----------------|
| >= 1200px   | Full layout as designed      | Full layout as designed                     | Full             |
| 800–1199px  | Same (no chrome to reflow)   | Controls wrap → topbar ~52px               | Same             |
| < 800px     | Same (no chrome to reflow)   | TopBar stacks; panels 50/50; resize off    | Same             |

Note: Zen mode benefits most on small screens -- no chrome means 98% content everywhere.

## Preserved aesthetic elements

These cost zero layout space and must survive across all modes:

- `body::before` grid texture overlay (all modes)
- `body` radial gradient background (all modes)
- `panel::after` directional gradient overlay (compact + focus only)
- `panel` translucent background + box-shadow (compact + focus only)
- Unbounded display font for title chips (compact + focus)
- IBM Plex Mono for all data/metrics (compact + focus)
- Accent glow on brand mark, timeline thumb, floating dot

---

## Proportional mockup (1080px viewport)

### Current layout

```
████████████████████████████  TopBar        ████  5%
░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  padding
████████████████████████████  Panel header  ████  4%
████████████████████████████                ████
████████████████████████████   CAMERA       ████  24%
████████████████████████████                ████
████████████████████████████  Metrics       ████  6%
░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  gap
████████████████████████████  Panel header  ████  4%
████████████████████████████                ████
████████████████████████████                ████
████████████████████████████   RERUN        ████  38%
████████████████████████████                ████
████████████████████████████                ████
████████████████████████████  Metrics       ████  6%
░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  padding
████████████████████████████  Timeline      ████  5%
```

### Zen mode (default on load)

```
████████████████████████████                ████
████████████████████████████                ████
████████████████████████████   CAMERA       ████  35%
████████████████████████████                ████
████████████████████████████                ████
┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄  resize       ┄┄┄┄
████████████████████████████                ████
████████████████████████████                ████
████████████████████████████                ████
████████████████████████████                ████
████████████████████████████   RERUN        ████  63%
████████████████████████████                ████
████████████████████████████                ████
████████████████████████████                ████
████████████████████████████                ████
████████████████████████████                ████  ●
```

### Compact mode (press Z)

```
████████████████████████████  TopBar        ████  4%
████████████████████████████  CAM header    ████  3%
████████████████████████████                ████
████████████████████████████                ████
████████████████████████████   CAMERA       ████  28%
████████████████████████████                ████
████████████████████████████                ████
┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄  resize       ┄┄┄┄
████████████████████████████  RERUN header  ████  3%
████████████████████████████                ████
████████████████████████████                ████
████████████████████████████                ████
████████████████████████████   RERUN        ████  53%
████████████████████████████                ████
████████████████████████████                ████
████████████████████████████                ████
████████████████████████████  Timeline      ████  3%
```

### Focus mode (press F on rerun)

```
████████████████████████████  TopBar        ████  4%
████████████████████████████  RERUN header  ████  3%
████████████████████████████                ████
████████████████████████████                ████
████████████████████████████                ████
████████████████████████████                ████
████████████████████████████                ████
████████████████████████████   RERUN        ████  87%
████████████████████████████                ████
████████████████████████████                ████
████████████████████████████                ████
████████████████████████████                ████
████████████████████████████                ████
████████████████████████████                ████
████████████████████████████                ████
████████████████████████████                ████
████████████████████████████  Timeline      ████  3%
```

## Summary

| Mode        | Content %  | Chrome % | Best for                           |
|-------------|------------|----------|------------------------------------|
| **Current** | 62%        | 38%      | (existing layout)                  |
| **Zen**     | **98%**    | 2%       | Monitoring, demo, observation      |
| **Compact** | **81%**    | 19%      | Active operation, recording, debug |
| **Focus**   | **87%**    | 13%      | Deep inspection of one data source |
