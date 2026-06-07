# Admin Dashboard Redesign — Scope & Proposal

**Date:** 2026-06-06
**Status:** Scoping / design proposal — awaiting approval before any code

---

## TL;DR

The current admin UI is functional but feels custom and dense. The FreeDash-lite template offers a clean Bootstrap 5 foundation worth adopting more deeply. **Adoption level: broader.** Pull in the full Bootstrap utilities, the multi-level sidebar, and the wider card family. Keep our domain model, backend, design tokens, and htmx + Alpine stack. The visual change is bigger; the bundle is bigger; ship time is longer — but the result is a much more recognizable, professional admin UI.

**Velocity over features.** No theme switcher, no language picker, no new settings panels. One operator, one screen, one job: keep the monitors healthy.

---

## 1. The Operator — Who Is This "Human"?

**Single admin / operator** (matches reality: single `ADMIN_PASSWORD`, single-tenant, no user management). Runs the visa appointment monitoring service. They are not a developer — they don't read logs unless something is wrong. They don't customize anything.

### Daily workflow (in order of frequency)

1. **Glance at health** — "Anything broken? Anything new to approve? Anything found?" — 10×/day, 3 seconds each.
2. **Triage a request** — A new client submitted their credentials. Approve or reject. 1–5×/day.
3. **Investigate a failure** — A monitor crashed. Read the log, restart it, or fix the cause. 0–2×/week.
4. **Confirm a hit** — System found an earlier date. Verify the screenshot, send the user to book. 0–3×/month.
5. **Check notification health** — Did alerts go out? Are contacts verified? 0–1×/week.

### What this means for the dashboard

- **The dashboard is the home page.** Every redesign decision optimizes for the 3-second glance.
- **The "needs attention" list is the most important widget.** Surfaces pending requests + erroring monitors + unverified contacts in one place.
- **Status is binary-ish at the top.** A red badge on "needs attention" tells them everything. They don't read numbers unless they want to.
- **Detail is one click away**, never inline. Drawer pattern (existing) is right; keep it.

---

## 2. What to Adopt From FreeDash (Broader Cherry-Pick)

**CSS bundle:** ship FreeDash's precompiled `dist/css/style.min.css` as a single asset, then add Bootstrap 5 utilities (the `bootstrap-utilities.min.css` subset — buttons, cards, badges, toasts, tabs, modal, progress, alerts, list-group, dropdown). Skip the full `bootstrap.min.css` reboot (it would normalize a lot of defaults we control with tokens). Use the rest of FreeDash's `style.min.css` for the sidebar/topbar skeleton.

| Pattern | Source file | What we adopt | Why |
|---|---|---|---|
| **Multi-level left sidebar** | `index.html` lines 251–471 | Replace our custom rail with FreeDash's `aside.left-sidebar` + `#sidebarnav`. Keep our 4 nav items; use the `nav-small-cap` pattern for "Workspace" / "Configuration" groups. | Standard, recognizable, scales if we add pages. |
| **Topbar with profile dropdown** | `index.html` lines 46–244 | Replace our `l-topbar` with FreeDash's `header.topbar`. Keep the search, theme toggle, notification bell. Profile dropdown gets just "Logout" (no fake "My Profile"). | Visual consistency with the rest of the adoption. |
| **Stat-card row** | `index.html` lines 516–590 | The "big number + label + icon" card pattern, 4-up at the top of the dashboard. Replace our `_metric_tile.html`. | Clean, scannable, standard. Works at any width. |
| **Coloured stat-card variants** | `ui-cards.html` (the colored cards section) | Use FreeDash's tinted card variants (`bg-primary`, `bg-success`, `bg-danger`, `bg-warning`) for the "needs attention" panel and the notification health strip. | Visual hierarchy without bespoke colors. |
| **Notification dropdown** | `index.html` lines 81–154 | Replace our placeholder topbar bell with a real dropdown showing recent events (new request, monitor error, slot found). | One glance, no navigation. Reduces context switching. |
| **Activity feed / list** | `ui-list-media.html` | "Recent activity" panel on the dashboard — last 10 events, time-stamped, click-through to source. | Surfaces "what just happened" without reading logs. |
| **Tabbed views** | `ui-tab.html` | Re-style our `requests.html` tabs (Pending / Approved / Rejected) with Bootstrap `nav-tabs` + content panels. | Already have tabs; make them feel intentional. |
| **Toast pattern** | `ui-toasts.html` | Replace our custom toast component with Bootstrap's `.toast` stack, but keep the same JS API (`window.toast()`). | Standard, accessible, free ARIA. |
| **Modal pattern** | `ui-modals.html` | Re-style the "Generate client link" modal using Bootstrap's `.modal` classes. | Consistent look, standard dismiss behaviors. |
| **Table card wrapper** | `table-basic.html` | Wrap our clients table in a `.card` container with a `.card-body` like FreeDash does. | Standard look; minimal markup change. |
| **Breadcrumbs** | `ui-breadcrumb.html` | Add breadcrumbs to nested pages (e.g., "Dashboard / Clients / Jane Smith"). | Helps when the URL gets deep. Optional, low cost. |
| **ApexCharts sparkline** | `chart-chart-js.html` | Small inline sparkline on each stat card showing the last 7 days of activity. | Adds visual interest with no new endpoint needed — we can compute it from `clients.updated_at`. Optional. |

**That's the full list.** About 12 patterns. The CSS is one file (~250 KB minified) + Bootstrap utilities (~50 KB). Acceptable for a private admin tool.

## 3. What NOT to Adopt (and Why)

| FreeDash feature | Skip because |
|---|---|
| jQuery | We use vanilla + htmx + Alpine. Adding jQuery is 30 KB of weight for zero benefit. |
| ApexCharts full library (if we don't use sparklines) | We don't have historical data worth charting. **Only adopt if we add the sparkline on stat cards.** |
| The `preloader` animation | The full-page spinner on every load is jarring. We use skeleton loaders. |
| The `freedashDark.svg` logo | Replace with a small inline `VC` mark. |
| `app-calendar.html` | We have no calendar data. |
| `app-chat.html` | We are not a chat app. |
| `ticket-list.html` | Our clients table is the equivalent; the styles map to `table-basic.html`. |
| `form-checkbox-radio.html`, `form-input-grid.html` | Client form is a wizard, not a generic form. |
| `icon-fontawesome.html`, `icon-simple-lineicon.html` | We use inline SVG / Lucide. Don't add a second icon set. |
| `authentication-login1.html` (jumbotron login) | Our login (`auth/login.html`) is cleaner and already themed. |
| `authentication-register1.html` | No self-signup. |
| Language switcher (`<select>` with EN/AB/AK) | Single-language product. YAGNI. |
| Profile dropdown with "My Profile / My Balance / Inbox / Account Setting" | We need only "Logout". |
| Gulp build pipeline (`gulpfile.js`, `package.json`) | We don't have a JS build step. Use the precompiled `style.min.css` directly. |

## 4. New Dashboard Layout (Proposed)

```
┌────────────────────────────────────────────────────────────────────────────┐
│  [Rail]  VisaCtrl · Dashboard                          [⌘K] [🔔3] [🌗] [A] │  ← existing topbar
├────────┬───────────────────────────────────────────────────────────────────┤
│  Nav   │  Eyebrow: Workspace ·  Heading: "Good afternoon"                │
│        │  Sub: "3 monitors running · 2 new requests waiting"              │
│  Dash  │                                                                   │
│  Cli.. │  ┌─Stat─────┐ ┌─Stat─────┐ ┌─Stat─────┐ ┌─Stat─────┐              │
│  Req.. │  │   12     │ │    2     │ │    1     │ │    3     │              │
│  Set.. │  │  Active  │ │  Pending │ │  Errors  │ │  Found   │              │
│  Log.. │  │ monitor. │ │ requests │ │  (24h)   │ │  (7d)    │              │
│        │  └──────────┘ └──────────┘ └──────────┘ └──────────┘              │
│        │                                                                   │
│        │  ┌─ Needs attention (3) ───────────────────────────────────────┐  │
│        │  │  ⚠ 2 pending requests — [Review →]                          │  │
│        │  │  ⚠ 1 monitor in error (Bob Smith) — [View log →]            │  │
│        │  └─────────────────────────────────────────────────────────────┘  │
│        │                                                                   │
│        │  ┌─ Recent activity ─────────────┐ ┌─ Live monitors (6 of 12) ─┐ │
│        │  │  • 14:02  Slot found — Jane S.│ │ ┌─card─┐ ┌─card─┐ ┌─card─┐│ │
│        │  │  • 13:48  Request — Bob S.    │ │ │  ●  │ │  ●  │ │  ⚠  ││ │
│        │  │  • 13:21  Monitor crashed — A.│ │ └──────┘ └──────┘ └──────┘│ │
│        │  │  • 12:55  Approved — J. Lee   │ │ ┌─card─┐ ┌─card─┐ ┌─card─┐│ │
│        │  │  ...                         │ │ │  ●  │ │  ◌  │ │  ●  ││ │
│        │  │  [View all activity →]       │ │ └──────┘ └──────┘ └──────┘│ │
│        │  └──────────────────────────────┘ └────────────────────────────┘ │
│        │                                                                   │
│        │  ┌─ Notification health ───────────────────────────────────────┐ │
│        │  │  9/12 monitors have verified contacts  ·  3 unverified     │ │
│        │  └─────────────────────────────────────────────────────────────┘ │
└────────┴───────────────────────────────────────────────────────────────────┘
```

**Principles:**
- **Eyebrow + heading + sub** (3 lines, not 1) is the modern dashboard greeting pattern. Replaces our flat title.
- **"Needs attention"** is a single panel with N items. Empty state: green checkmark + "All clear."
- **Recent activity** is a vertical feed with timestamps, click-through to source (request card, client detail, log).
- **Live monitors** is a 3-up grid of cards. Limited to 6 with a "View all 12 →" link to `/admin/clients`. Replaces our current "24 cards on the dashboard" (too many to scan).
- **Notification health** is a footer strip. One line. Surfaces the "is the alerting actually working" question.

## 5. Phased Plan — Velocity First (Broader Adoption)

### Phase 1 — Wire up FreeDash CSS + new shell (2–3 hours)
1. Copy `dist/css/style.min.css` from FreeDash into `src/app/static/css/freedash.min.css`.
2. Add `bootstrap-utilities.min.css` (utilities subset only — no reboot) into `src/app/static/css/`.
3. Add `<link>` tags to `base.html` AFTER our own tokens/base CSS so our values win on conflict.
4. Add FreeDash's `feather.min.js` (icon library — small, tree-shakable, replaces some inline SVG).
5. Rewrite the `<body>` of `base.html` to use FreeDash's `aside.left-sidebar` + `header.topbar` + `div.page-wrapper` structure. Keep our 4 nav items, grouped under "Workspace" / "Configuration" caps.
6. Wrap page content in `div.container-fluid` to match FreeDash's grid.

### Phase 2 — Dashboard rewrite (2–3 hours)
7. Replace `_metric_tile.html` with FreeDash stat-card markup. Keep our data binding.
8. Add the "Needs attention" panel with coloured card variants (`bg-warning`, `bg-danger`).
9. Add the "Recent activity" panel (vertical feed, last 10 client updates).
10. Add the "Notification health" strip (one line, color-tinted by health).
11. Replace the "24 monitors on the dashboard" with 6-card grid + "View all →".

### Phase 3 — Clients + Requests restyle (1–2 hours)
12. Wrap the clients table in a FreeDash `.card` container.
13. Restyle the requests tabs as Bootstrap `nav-tabs`.
14. Adopt the table card wrapper pattern across all admin pages.

### Phase 4 — Notifications + toasts + modal (1 hour)
15. Replace the bell placeholder with a real dropdown feed.
16. Wrap our `window.toast()` in Bootstrap's `.toast` markup. Same API.
17. Re-style the "Generate client link" modal as a Bootstrap `.modal`.

### Phase 5 — Optional polish (only if velocity holds)
18. Add breadcrumbs to nested pages.
19. Add ApexCharts sparklines to the stat cards (only if we can compute 7-day deltas cheaply).
20. Empty-state copy across the app.

**Total: 6–9 hours of focused work to ship a substantially redesigned admin experience. Larger visual change, larger bundle, more value.**

## 6. What About the Client Form?

**Out of scope for this redesign.** The client form (`/client/<token>`) is the end-user's view — visa applicants filling in their credentials. It's a one-shot wizard, not a dashboard. Leave it. The free-dash `form-inputs.html` patterns are generic form layouts; the wizard has its own visual language (steps, validation, focused single-purpose UX).

The only client-side polish worth considering later: align its `glass.css` look with the new admin's Bootstrap-influenced feel. Not now.

## 7. What About the Profile Feature?

**Out of scope.** The profile-with-multiple-applications spec is parked. If/when it gets built, the profile UI follows the same card/feed patterns we're adopting here. The FreeDash cherry-pick list does not change.

## 8. What Gets Deleted / Replaced

| File | Action |
|---|---|
| `src/app/static/css/glass.css` | **Keep for client form**, don't load on admin pages. |
| `src/app/templates/partials/_metric_tile.html` | Replace with stat-card markup. |
| `src/app/templates/admin/dashboard.html` | Rewrite with new layout. |
| `src/app/templates/admin/clients.html` | Lightly re-style table card wrapper only. |
| `src/app/templates/admin/requests.html` | Lightly re-style tabs. |
| `src/app/static/js/toast.js` | Wrap our `window.toast()` in Bootstrap markup. |
| `src/app/static/js/popover.js` | Add a real activity-feed render path for the bell. |

Nothing in `src/`, `src/services/`, `src/orchestrator/`, or any route file changes. This is a pure UI revamp.

## 9. Risk & Rollback

- **Risk:** New CSS layer collides with our tokens. Mitigated by loading order (ours first, FreeDash + utilities after) and CSS specificity (our tokens use `--var` references; FreeDash uses concrete values — minimal collision on tokens, more on component classes). **Plan: if conflict, prefix our class names with `vc-` to win specificity, or scope our overrides under a higher-specificity selector.**
- **Risk:** Bootstrap's reboot (if we accidentally include `bootstrap.min.css` instead of the utilities subset) normalizes HTML defaults we control. Mitigated by importing ONLY the utilities we want, never the full reboot.
- **Risk:** Adopting FreeDash's sidebar/topbar markup means rewriting `base.html` and a lot of partials. If we get the markup wrong, every admin page breaks. **Mitigation: rewrite `base.html` last, after all new partials are in place, and test with the existing pages before any new ones.**
- **Rollback:** All changes are template + CSS + JS. Revert by `git checkout` of those files. No DB, no schema, no backend.

## 10. Decisions (Locked)

1. **Two base templates.** `base_admin.html` for `/admin/*` gets the full FreeDash shell (sidebar + topbar + container). `base_client.html` for `/client/*` keeps the existing minimal shell. They never share markup. — *Approved.*
2. **Feather for admin, Lucide for the form.** Two icon libraries, but they never coexist on the same page. Acceptable. — *Approved.*
3. **No ApexCharts sparklines in v1.** Skip charts until we have a stats endpoint. — *Default.*
4. **"Needs attention" = pending requests + erroring monitors (last 24h).** Skip unverified contacts. — *Approved.*
5. **Keep the existing ⌘K command palette + theme toggle on the new admin shell.** They're our features, not FreeDash. — *Default.*

---

## 11. Files That Change (Total Surface)

**Added:** 2 (`freedash.min.css`, `bootstrap-utilities.min.css`) + 1 JS (`feather.min.js`).

**Modified:** 7 templates (dashboard, clients, requests, settings, logs, base, login shell) + 2 JS modules + the topbar.

**Untouched:** All backend, all routes, all repos, all orchestrator code, all services, all scrapers, `src/app/static/css/glass.css` (still used by client form), the entire `src/app/static/img/` tree, `AGENTS.md` (no API changes).

The revamp is contained in templates, 2 new CSS files, 1 new JS file, and 2 existing JS modules. One to two focused days of work for a substantial UX win.
