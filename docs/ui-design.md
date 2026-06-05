# VisaCtrl UI Design Specification

**Version:** 0.1 (Phase 0+1+2+3 — Dashboard milestone)
**Stack:** Flask + htmx + Alpine.js + Server-Sent Events
**A11y target:** WCAG 2.1 AA
**Browser floor:** Last 2 versions of Chrome, Edge, Safari, Firefox

## 1. Goals

| Goal | Anti-goal |
|---|---|
| Reactive — every state change is visible in < 2 s | No SPA build pipeline |
| State-persistent — UI survives reload, restore from server | No client-owned truth |
| Material × Apple — calm, considered, never busy | No gratuitous motion |
| Server-rendered HTML, hydrated by SSE | No React/Vue/Svelte runtime |
| Progressive enhancement — works without JS for read paths | No hard JS dependency for non-interactive pages |
| All client state in SQLite stays authoritative | No localStorage as truth (only as cache) |

## 2. Design language

### Type
- **Sans:** `Inter` with system fallback (`-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`)
- **Mono:** `JetBrains Mono` for log lines, IDs, code
- **Base:** 14px / 1.5 line-height
- **Scale:** 12, 13, 14, 16, 18, 20, 24, 30, 36

### Color (light)
- Neutrals: slate 50–950
- Primary: blue 500 `#3b82f6` (interactions), blue 600 (hover), blue 700 (active)
- Semantic: green 600 success, amber 500 warning, red 600 error, blue 500 info
- Surfaces: `--bg-primary` (page), `--bg-secondary` (card), `--bg-tertiary` (raised)

### Color (dark)
- Page bg: slate 950 `#020617`
- Card bg: slate 900 `#0f172a`
- Raised: slate 800 `#1e293b`
- Border: slate 800
- Text primary: slate 50, secondary: slate 400, muted: slate 500
- Same primary/semantic hues, slightly desaturated

### Spacing
4px base unit: `4, 8, 12, 16, 20, 24, 32, 40, 48, 64`. **Never use any other value.**

### Radius
`4px` (sm: chips), `6px` (md: inputs), `8px` (lg: cards/buttons), `12px` (xl: modals), `9999px` (full: pills/avatars).

### Shadow
Three tiers only. **No drop shadow on flat rows.**
- `sm`: 0 1px 2px rgba(0,0,0,.05) — popovers
- `md`: 0 4px 6px -1px rgba(0,0,0,.1) — cards on hover
- `lg`: 0 10px 25px -5px rgba(0,0,0,.15) — modals

### Motion
| Interaction | Duration | Easing |
|---|---|---|
| Hover | 150ms | ease |
| Focus ring | 100ms | ease-out |
| Modal in | 200ms | cubic-bezier(0.2, 0, 0, 1) |
| Drawer | 250ms | cubic-bezier(0.2, 0, 0, 1) |
| Page view-transition | 200ms | ease-in-out |

**All motion disabled when `prefers-reduced-motion: reduce`.**

### Iconography
- **Lucide** (line icons), 1.5 stroke width
- 20px in nav, 16px inline with text, 14px in chips

## 3. Information architecture

```
Login ──► /admin/
           ├── Dashboard       (landing)
           ├── Clients         (table, filter, bulk)
           ├── Requests        (inbox)
           ├── Settings        (tabs: General / Notifications / Telegram / Security)
           └── Logs            (live tail)
```

## 4. Shell layout

```
┌─────────────────────────────────────────────────────────────┐
│  [≡]  VisaCtrl        ⌘K Search…        [◐] [🔔] [👤 Admin] │  ← topbar (56px, glass)
├──────┬──────────────────────────────────────────────────────┤
│  ⌂   │   Breadcrumb · Page title                  [+ Action]│
│  📊  │   ─────────────────────────────────────────────      │
│  👥  │                                                       │
│  ⏳  │   [main content]                                      │
│  ⚙️  │                                                       │
│  📋  │                                                       │
│      │                                                       │
│  ──  │                                                       │
│  ⎯⎯  │                                                       │
│  👤  │                                                       │
└──────┴──────────────────────────────────────────────────────┘
```

- **Left rail:** 72px collapsed (icons + tooltip), 256px expanded on hover. Persistent on `xl` viewports.
- **Topbar:** `backdrop-filter: blur(20px)`, 56px tall, fixed top, z-20.
- **Main:** max-width 1280px, padding 32px (`--space-8`).
- **Status dot** in topbar (green/amber/red) reflects `/health` + scraper health.

## 5. Dashboard (first view)

### Layout

```
┌──────────┬──────────┬──────────┬──────────┐
│ Total    │ Running  │ Pending  │ Errors   │  ← metric tiles (sparkline)
│ 24       │ 7        │ 3        │ 1        │
└──────────┴──────────┴──────────┴──────────┘

┌──────────────────────────────────┬──────────────┐
│  Active monitors                 │  Recent      │
│  ┌─────────┐ ┌─────────┐         │  activity    │
│  │ Jiggar  │ │ Ashley  │         │              │
│  │ ✓ IDLE  │ │ ⟳ CHECK │         │  • Approved  │
│  │ Toronto │ │ Calgary │         │    client X  │
│  │ 2h ago  │ │ 3m ago  │         │  • Found ear │
│  └─────────┘ └─────────┘         │    date @ YY │
│                                  │              │
└──────────────────────────────────┴──────────────┘
```

### Metric tiles
- Big number (24px, semibold) + label (12px uppercase, muted)
- Sparkline below (24h history, 7-day or 30-day toggle)
- Click → drill into the filtered list
- Reactive: every 1–2 s via SSE (`metric.tick`)

### Active monitors
- Card per running client
- Status pulse (green dot) animated
- "Idle" / "Checking" / "Login" pill
- Last checked: relative time (`2m ago`)
- Latest screenshot thumbnail (click → detail)
- Click card → full client detail

### Activity feed
- Reverse-chronological, virtualized
- 5 event types, color-coded icon:
  - `approved` (green check) — admin approved a request
  - `rejected` (red x) — admin rejected
  - `restart` (blue refresh) — orchestrator restarted
  - `error` (red alert) — scraper logged an error
  - `found` (amber calendar) — earlier date discovered
- Auto-scrolls if at top; pauses on user scroll

## 6. Reactive model

### Server → browser
- **SSE endpoint:** `GET /events/stream` — `text/event-stream`, one connection per browser
- **Snapshot endpoint:** `GET /snapshot` — initial state for hydrate
- The SSE handler polls SQLite (clients, automation_state) + log file mtimes + screenshot dir every 1–2 s
- Emits structured events with `id` (monotonic), `event` (type), `data` (JSON)

### Event types

| Event | Payload | Trigger |
|---|---|---|
| `state.changed` | `{client_id, fields: {…diff}}` | DB row updated |
| `log.line` | `{client_id, ts, level, msg}` | New line in `<id>.log` |
| `screenshot.ready` | `{client_id, path, ts}` | New screenshot persisted |
| `metric.tick` | `{running, pending, errors_24h, total}` | Periodic (every 5 s) |
| `request.new` | `{client_id, name, email, ts}` | New pending request |
| `alert` | `{severity, title, msg, ts}` | Orchestrator error or admin action |

### Browser → server
- All writes go through normal POST endpoints (already exist)
- Optimistic UI for low-risk actions (stop, approve)
- No `put`/`delete` to SSE — SSE is read-only

### Persistence
- `localStorage` stores: `theme`, `sidebar.expanded`, `density`, `last_seen_snapshot`
- IndexedDB (optional, later): per-client log tail cache for offline view
- Server is always the source of truth — local caches are filled, not authoritative

## 7. Component vocabulary (15 components)

| Component | Variants | Notes |
|---|---|---|
| `Button` | primary, secondary, ghost, destructive · sm/md/lg | 36px md height, 8px radius |
| `IconButton` | ghost · sm/md | 32px square, tooltip via `aria-label` |
| `Card` | default, raised, interactive | 16px padding, 8px radius, 1px border |
| `Stat` | default, with-sparkline, with-trend | Used in dashboard tiles |
| `Pill` | success, warning, error, info, neutral | 9999px radius, 4px px, 20px height |
| `Avatar` | sm/md/lg · with-status | Circle, 1.5px status border |
| `Drawer` | right (default), left | 480px, slides in 250ms |
| `Modal` | sm (400), md (560), lg (720) | Centered, overlay 30% opacity |
| `Toast` | success, error, info, warning | Top-right stack, 4s auto-dismiss |
| `Tabs` | underline (default), pill | 6 max |
| `Empty` | default, with-illustration, with-cta | Centered, max-width 400px |
| `Skeleton` | text, block, circle, card | Shimmer 1.2s loop |
| `Command` | single-modal | ⌘K / Ctrl+K |
| `Banner` | info, warning, error, success | Full-width, dismissable |
| `Switch` | sm/md | 36×20 / 44×24 |

Each component is a Jinja macro in `src/app/components/macros.html` + CSS classes in `components.css`. No JS framework dependency.

## 8. Accessibility (WCAG 2.1 AA)

- All text ≥ 4.5:1 contrast (3:1 for large)
- All interactive elements have visible `:focus-visible` ring (2px, primary-500)
- All icon-only buttons have `aria-label`
- All form fields have visible `<label>` (no placeholder-only)
- Toasts: `aria-live="polite"`; errors: `aria-live="assertive"`
- Modals trap focus, restore on close, `Esc` to dismiss
- Drawers: same as modals
- All images have `alt`; decorative have `alt=""`
- Color is never the only signal — always paired with icon or text
- `prefers-reduced-motion: reduce` disables all transitions
- `prefers-color-scheme: dark` honored if user hasn't set manual override
- Skip-to-content link at top of every page
- Semantic HTML: `<nav>`, `<main>`, `<section>`, `<article>`, `<button>`, `<a>`

## 9. Performance

- All CSS in one compiled `app.css` (not per-page)
- All JS in one `app.js` (~25 KB after gzip, no bundler)
- htmx + Alpine loaded from CDN with `defer`
- Images use `width`/`height` to prevent CLS
- No web fonts on critical path beyond Inter (loaded with `font-display: swap`)
- SSE is single connection, throttled to 1–2 s tick

## 10. File layout (post-Phase 3)

```
src/app/
├── static/
│   ├── css/
│   │   ├── tokens.css       # design tokens
│   │   ├── base.css         # reset + base
│   │   ├── components.css   # 15 components
│   │   └── views.css        # per-view overrides
│   ├── js/
│   │   ├── store.js         # client state, localStorage
│   │   ├── sse.js           # EventSource wrapper
│   │   ├── theme.js         # dark mode toggle
│   │   ├── command.js       # ⌘K palette
│   │   ├── toast.js         # toast manager
│   │   └── views/
│   │       └── dashboard.js # dashboard-specific
│   └── img/                 # logos, illustrations
├── templates/
│   ├── base.html            # shell
│   ├── login.html
│   ├── admin/
│   │   ├── dashboard.html
│   │   ├── clients.html     # phase 4
│   │   ├── requests.html    # phase 4
│   │   ├── settings.html    # phase 4
│   │   └── logs.html        # phase 4
│   └── partials/
│       ├── _metric_tile.html
│       ├── _monitor_card.html
│       ├── _activity_item.html
│       ├── _pill.html
│       ├── _toast.html
│       └── _empty.html
└── components/
    └── macros.html          # the 15 components as Jinja macros
```

## 11. What's NOT in scope for this milestone

- Clients / Requests / Settings / Logs views (Phase 4+)
- ⌘K command palette (Phase 5)
- Bulk actions (Phase 4)
- Audit log (Phase 4)
- Tests beyond `test_event_bus.py` (continuous)
- i18n (later)
- Mobile-first polish (desktop-first per constraint)
- White-labelling / multi-tenancy

## 12. Open questions

- Are there client photos / avatars we should render in the monitor cards? (Currently: initials only)
- Do we want a sound on `request.new`? (Default: off)
- Should the dashboard refresh rate be configurable, or fixed at 1 s?
