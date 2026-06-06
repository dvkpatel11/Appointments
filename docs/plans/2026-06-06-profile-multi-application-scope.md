# Profile & Multi-Application Scope — Backend Completeness + Prod Readiness

**Date:** 2026-06-06
**Status:** Scoping / spec — awaiting approval before implementation

---

## TL;DR — Verdict

| Capability | Status | Evidence |
|---|---|---|
| Parallel web-scraping of N requests | **Complete** | `src/orchestrator/manager.py:92` spawns one `multiprocessing.Process` per approved client; `_alive_processes` registry; `check_and_recover` 60s tick; `clients_bulk_start/stop` endpoints |
| Isolated state per request | **Complete** | Per-client `automation_state` row, per-client `logs/<id>.log`, per-client `screenshots/<id>/` dir, per-client `agent_pid` |
| **Profile grouping multiple applications** | **Missing** | No profile entity; one `Client` row == one application. Form, admin, and notification routing are all single-app |
| **Form-level mode distinction** | **Missing** | `client/form.html` is a single 3-step wizard that always produces exactly one application |
| **Shared credentials across apps in a profile** | **Missing** | Each app has its own `password_ciphertext`; no way to "use the same login for all my apps" |
| **Notification inheritance / override** | **Missing** | Notification fields live only on the client row; no profile-level fallback |
| **Profile-scoped status page** | **Missing** | `/client/<token>` renders one application; no way to see "my 4 apps" at a glance |
| **Admin grouping by profile** | **Missing** | Clients table is flat; 1 user with 5 apps = 5 indistinguishable rows |

**Bottom line:** the parallel-scraping substrate is production-grade. The new "profile with multiple applications" concept is a clean additive layer — it does not require touching the orchestrator, the scrapers, or the per-process state model.

---

## 1. Backend Audit — Why Parallel Scraping Is Complete

### What works today

```
┌─────────────────────────────── Flask parent process ───────────────────────────────┐
│                                                                                     │
│  /admin/clients/bulk-start ──► AutomationService.start(token)  for each id          │
│  /admin/clients/bulk-stop  ──► orchestrator.stop(client_id)    for each id          │
│                                                                                     │
│  _recovery_loop (60s tick):                                                         │
│    orchestrator.check_and_recover()                                                │
│      ├─ for each APPROVED client:                                                  │
│      │   if process not in _alive_processes:                                       │
│      │     apply exponential backoff (30s → 600s)                                  │
│      │     if not in backoff: start(client)                                        │
│      │                                                                             │
│    orchestrator.cleanup_stale_pending_links()  (30-min TTL)                        │
│                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                │
                                │ spawns one Process per approved client
                                ▼
┌────────────────── Process A (pid=100) ──────────────────┐
│  CanadaVisaScraper.run()                                │
│   ├─ own sync_playwright() instance                     │
│   ├─ own browser context                                │
│   ├─ logs/<id_A>.log   (RotatingFileHandler 5MB×3)     │
│   ├─ screenshots/<id_A>/NNN_*.png                      │
│   └─ state_repo.save(id_A, ...) on every log line       │
└─────────────────────────────────────────────────────────┘
┌────────────────── Process B (pid=101) ──────────────────┐
│  CanadaVisaScraper.run()  (independent Playwright, log, │
│  screenshot dir, state row)                             │
└─────────────────────────────────────────────────────────┘
...N processes...
```

### What's specifically there

- `multiprocessing.Process` per approved client — `src/orchestrator/manager.py:92`
- Process registry keyed by `client_id` — `manager.py:13` (`_alive_processes`)
- Crash detection via `_pid_alive` — `manager.py:18`
- Exponential backoff: `crash_backoff_base=30s`, `crash_backoff_max=600s` — `config.py:32-33`, `manager.py:165`
- Per-client PID persisted to `clients.agent_pid` — `client_repo.update_field(..., agent_pid=...)` on every start
- Resume on app boot: `manager.py:200 resume_approved_agents()` runs from `create.py:341`
- SIGTERM-aware shutdown with grace budget split across agents — `manager.py:121 stop()`, `manager.py:144 stop_all()`
- Bulk admin endpoints with per-id outcome reporting — `admin.py:198 bulk_start`, `admin.py:220 bulk_stop`
- Live SSE event stream to refresh admin UI on state changes — `src/app/routes/events.py`
- Status panel capped at 24 monitors in dashboard for UI sanity — `admin.py:289`

### What can break at scale (worth knowing but not "incomplete")

- **No fan-out limit.** A user could approve 1000 clients and the parent would spawn 1000 chromium processes. Cloud Run 2Gi/2CPU caps this implicitly. **Recommendation (YAGNI for now):** add a `max_concurrent_agents` setting; log a warning when exceeded. Do not enforce until a real customer hits it.
- **Each Playwright instance ≈ 200-300 MB RSS.** 10 agents ≈ 2.5-3 GB. We are at the Cloud Run 2Gi ceiling already with ~7-8 agents. **Recommendation:** document the ceiling; consider switching to a single shared chromium with multiple contexts (smaller per-agent footprint). Defer until needed.
- **State writes serialize on the parent DB** (WAL helps, but every log line is a `cursor()` call). For 20+ agents polling every 30s, that's ~40 writes/min. Fine. Will not scale to 1000s.

---

## 2. The Profile Concept — Design

### 2.1 The mental model

```
Profile (real-world person / visa portal account)
  ├─ name: "Jane Smith"
  ├─ portal username + password (shared by all apps)
  ├─ notification contacts (email / telegram / phone)
  └─ Applications[]
        ├─ App #1: appointment_id=9988, locations=[Toronto], reschedule=true
        ├─ App #2: appointment_id=9989, locations=[Ottawa, Vancouver], reschedule=false
        └─ App #3: appointment_id=9990, locations=[Calgary], reschedule=true
```

A **profile** is a grouping entity. It owns credentials and notifications. It has no scraper process of its own.

An **application** is the existing `Client` row. It owns one scraper process, one appointment, one set of monitoring preferences. Under a profile, applications inherit the profile's credentials and notifications.

### 2.2 Why "one process per application" (not "one per profile")

The orchestrator already keys on `client_id`. Keeping the process-per-application model:

- Preserves isolation — one app crashing doesn't take down siblings.
- Allows staggered polling — different apps can start at different offsets.
- Avoids one giant scraper with shared browser state (race conditions).
- Reuses 100% of existing code: `VisaScraper`, `state_repo`, `automation_state`, `agent_pid`, crash recovery.

The profile is purely a **data layer** concept. The orchestrator and scraper never need to know it exists.

### 2.3 Where credentials and notifications live

**Two valid options.** Both are workable. The choice affects how the `Client` dataclass, `NotificationService`, and the form interact.

| Option | Credentials | Notifications | Pros | Cons |
|---|---|---|---|---|
| **A. Copy at submit time** | Snapshot onto each app at submit | Snapshot onto each app at submit | Zero runtime lookups; scraper is unchanged | Updating creds requires re-approving all apps; no profile-level update UX |
| **B. Inherit at runtime** | Live-read from profile at scraper startup | Live-read from profile on every `_notify()` call | Updating profile creds/contacts affects all apps immediately | Every notification has a DB lookup; scraper needs profile_id awareness; need fallback chain |

**Recommendation: A for credentials, B for notifications.**

- **Credentials are stable** — users rarely change their visa portal password. Snapshot at submit time = zero scraper change.
- **Notifications are mutable** — users add Telegram after approval, change email, etc. Live-read = single source of truth, no per-app update path.

This gives us:
- Scraper code is **untouched** for credentials.
- `NotificationService.send()` gains a small fallback chain (client override → profile).
- No re-approval needed to add Telegram; user goes to profile status page, links Telegram, all apps start receiving.

### 2.4 Schema (minimal additive)

```sql
-- New table
CREATE TABLE profiles (
    id TEXT PRIMARY KEY,                    -- internal UUID (same shape as client.id)
    token TEXT UNIQUE NOT NULL,             -- public link token (same shape as client.token)
    name TEXT,                              -- "Jane Smith"
    username TEXT,                          -- visa portal login
    password_ciphertext TEXT,               -- encrypted (reuse crypto helpers)
    notification_email TEXT,
    notification_email_verified INTEGER NOT NULL DEFAULT 0,  -- mirrors email_confirmations logic
    telegram_chat_id TEXT,
    phone_number TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Additive to clients (nullable, so existing rows are unaffected)
ALTER TABLE clients ADD COLUMN profile_id TEXT REFERENCES profiles(id) ON DELETE SET NULL;

-- Helpful index for "list all apps under a profile" queries
CREATE INDEX idx_clients_profile_id ON clients(profile_id);
```

**No other schema changes.** The existing `clients` table and all its columns stay as-is. `profile_id IS NULL` = legacy standalone client; `profile_id IS NOT NULL` = app under a profile.

### 2.5 What `Client.can_start` becomes

Today: `state == APPROVED and username and password`.

Under profile mode: the app's `username`/`password` are populated at submit time from the profile (snapshot approach). So `can_start` is unchanged. **No logic change needed.**

---

## 3. Form UX — The Distinction

### 3.1 The two modes

The first thing the user sees on the form (replacing or preceding Step 1) is a mode toggle:

```
┌─────────────────────────────────────────────────────┐
│  What are you setting up?                           │
│                                                     │
│  ( ) Single application                             │
│      Monitor one appointment with one login.        │
│                                                     │
│  (●) Profile with multiple applications             │
│      One login, multiple appointments.              │
│                                                     │
└─────────────────────────────────────────────────────┘
```

### 3.2 Single mode (preserves current flow)

3-step wizard, identical to today:
- Step 1: Your name
- Step 2: Appointment + Credentials + Locations + Dates + Reschedule
- Step 3: Notifications

Submit → existing `/client_submit` endpoint, existing flow.

### 3.3 Profile mode (new flow)

4-step wizard:
- **Step 1: Your details** — Name only (matches existing Step 1)
- **Step 2: Portal credentials** — Username + portal password (moved up from current Step 2)
- **Step 3: Applications** — Dynamic list. First application shown by default. `[+ Add another application]` button appends another card with: appointment_id, locations, date window, reschedule. `[Remove]` button on apps 2+. Each card has client-side validation; submit is blocked if any card is incomplete.
- **Step 4: Notifications** — Email, SMS, Telegram (same fields as today)

Submit → new endpoint `/client_submit_profile` (or extends `/client_submit` with a `mode=profile` flag and an `applications` array payload).

### 3.4 The data flow

```
Step 3 (apps) submits payload like:
  applications: [
    {appointment_id: "9988", preferred_locations: ["Toronto"], reschedule: "true", preferred_date_from: "2026-09-01", preferred_date_to: "2026-12-01"},
    {appointment_id: "9989", preferred_locations: ["Ottawa"], reschedule: "false", ...},
  ]
```

Server side:
1. Create one `profiles` row with name + credentials + contacts
2. Create N `clients` rows, each with:
   - `profile_id` = new profile's id
   - `username` / `password` snapshotted from the profile
   - `appointment_id`, `preferred_locations`, dates, reschedule from the app card
   - `state = PENDING`
   - `notification_email` left NULL (set only after magic-link click, same as today)
3. Return the profile token; render the **profile status page** instead of the single-app status page

### 3.5 The "use existing client link" question

The current `create_token()` creates a token for a single client. We need a parallel `create_profile_token()` (or generalize it). Decision: **keep both** — admin gets a "Generate client link" button (today) and a new "Generate profile link" button. The form URL is `/client/<token>` for both; the form's first question determines which wizard renders. A small lookup helper checks `profiles` first, falls back to `clients`.

---

## 4. Notification Inheritance — The Runtime Fallback

### 4.1 The chain (in `NotificationService.send`)

```
For each channel (email / telegram / sms):
  1. If client.<channel> is set AND (channel != email OR email_verified): use it.
  2. Else: look up client.profile_id → profile.<channel>; if set AND verified: use it.
  3. Else: skip this channel.
```

### 4.2 Where the lookup lives

Two options:
- (a) `NotificationService.send()` gains a `client` (or `client_id`) parameter and does the fallback internally.
- (b) The scraper's `_notify()` method resolves the final recipient list (a `dict[channel → address]`) before calling `send()`.

**Recommendation: (b).** Resolving the recipient is a per-client concern, not a per-channel concern. The scraper already has `client_id`; it can resolve once per notify call and pass a flat dict to `send()`. Keeps `NotificationService` simple.

```python
# In VisaScraper._notify or a new helper
def _resolve_recipients(self) -> dict[str, str]:
    recipients = {}
    if self.notification_email:
        recipients["email"] = self.notification_email
    elif self.profile_id:
        profile = profile_repo.get(self.profile_id)
        if profile and profile.notification_email and profile.notification_email_verified:
            recipients["email"] = profile.notification_email
    # same for telegram, sms
    return recipients
```

This means the scraper constructor needs a `profile_id`. Small change: pass it through `_scraper_entry` in `manager.py`, store on the scraper instance, use the resolver before each `_notify` call.

### 4.3 Email verification under profiles

`email_confirmations` table has `user_id` referring to `clients.id`. Two options:
- (a) Keep referring to the profile's id (we'd need a separate `profile_id` column or change the FK).
- (b) Store the email confirmation against the profile, mark `profiles.notification_email_verified = 1` on click.

**Recommendation:** add a `profile_id` column to `email_confirmations` (nullable, alongside the existing `user_id`). The magic link click handler checks which row to mark confirmed. This is minimal and mirrors existing logic.

---

## 5. Status Page — `/client/<token>` Under Profile Mode

Today, `/client/<token>` renders one client's monitor panel.

Under profile mode, the same URL renders a **profile status page** that shows:
- Profile header (name, contact info, "Add Telegram" / "Add Email" tiles — same UX as today)
- A list of cards, one per application under the profile, each showing:
  - Appointment ID + visa type
  - State (Pending / Approved / Running / Stopped)
  - Last action, current date, found date
  - Per-app stop button

The existing per-client endpoints (`/client_status/<token>`, `/client_screenshot/<token>`, etc.) are **single-app** and stay as-is. New endpoints serve the profile:

```
GET  /profile_status/<profile_token>      → JSON for the profile status page polling
POST /profile_stop_app/<profile_token>    → body: {client_id}; stops one app
POST /profile_link_telegram               → body: {profile_token, chat_id}; sets on profile
```

The client-side JS that polls status changes from "one panel" to "list of panels"; the polling endpoint switches based on whether the token resolves to a profile or a legacy client.

---

## 6. Admin UX — New Views

### 6.1 New page: `/admin/profiles`

Lists profiles with:
- Name
- Application count
- Notification status (email verified? telegram linked?)
- Expand to see all apps under the profile

### 6.2 Clients table changes

- Add a "Profile" column showing the profile name (or "—" for legacy standalone clients)
- New filter: `data-filter="profile"` with options: `All / With profile / Standalone`
- "Generate profile link" button next to "Generate client link"
- Bulk operations stay per-application (operate on `client_id`s, not profiles)

### 6.3 Existing admin flows unchanged

- Approve / Reject a pending request still happens at the application level. Each app under a profile goes through its own ISSUED → PENDING → APPROVED transition. The admin can see "this app belongs to Jane Smith's profile (3 other apps)" while approving.
- Bulk start/stop operates on selected rows as today.
- Dashboard monitors grid stays the same (one card per app).

---

## 7. Migration & Backwards Compat

### 7.1 What existing users see

- All existing clients have `profile_id = NULL` after the migration. The form's "Profile with multiple applications" mode is a new option; the existing single-app flow is the default and works exactly as before.
- Admin sees a "Profile" column showing "—" for all existing rows.
- The new "Generate profile link" button is added; the old button stays.

### 7.2 Migration code

`init_db()` already has the idempotent `ALTER TABLE ... ADD COLUMN` pattern (`database.py:92-95`). Add:

```python
try:
    cur.execute("ALTER TABLE clients ADD COLUMN profile_id TEXT REFERENCES profiles(id) ON DELETE SET NULL")
except sqlite3.OperationalError:
    pass

cur.execute("CREATE TABLE IF NOT EXISTS profiles (...)")
cur.execute("CREATE INDEX IF NOT EXISTS idx_clients_profile_id ON clients(profile_id)")
```

No data backfill is needed. Old clients are simply standalone forever.

---

## 8. Phased Implementation Plan

Each phase is independently shippable. The order minimizes risk by keeping each phase a thin additive layer.

### Phase 1 — Data layer (no UI, no behavior change)

1. `src/domain/profile.py` — `Profile` dataclass mirroring `Client`'s shape (without monitoring fields)
2. `src/infrastructure/repositories/profile_repo.py` — `create_token`, `get_by_id`, `get_by_token`, `save`, `update_field`, with the same `ALLOWED_UPDATE_COLUMNS` pattern
3. `src/infrastructure/database.py` — add `CREATE TABLE profiles`, `ALTER TABLE clients ADD COLUMN profile_id`, index
4. `src/app/routes/__init__.py` re-exports

**No other code touched. No behavior change. Ship to verify the migration is clean.**

### Phase 2 — Profile-scoped status page + admin list (read-only)

5. `src/app/routes/admin.py` — new `GET /admin/profiles` + partials for the profile list and a "view apps under this profile" expandable
6. `src/app/templates/admin/profiles.html` — list view
7. `src/app/templates/partials/_profile_row.html` — row partial
8. New `GET /profile_status/<profile_token>` endpoint returning a flat JSON for client-side polling
9. Client-side JS module `static/js/views/profile_status.js` (only fetched when the resolved entity is a profile)

At this point: zero new submissions, just a way to see "what profiles exist" and "what apps are in each". Validates the data model.

### Phase 3 — Profile submit flow

10. `src/services/client_service.py` — new `submit_profile_request(token, form_data)` and `ClientService.approve(token)` reuses; new internal `snapshot_credentials_to_apps(profile, apps)`
11. `src/app/routes/client.py` — new `POST /client_submit_profile` (rate-limited same as `/client_submit`)
12. `src/app/templates/client/form.html` — add mode toggle at top of Step 1; show the appropriate wizard based on selection (server-side render the active mode, JS-only switch is fine too)
13. New client-side `static/js/views/client_form_profile.js` handling the dynamic apps list
14. Admin "Generate profile link" button + endpoint

Submitting a profile creates the profile + N apps in PENDING. Admin can approve each app independently with the existing flow.

### Phase 4 — Notification inheritance

15. `src/services/notification_service.py` — accept a `recipients: dict[str, str]` instead of individual kwargs (clean refactor)
16. `src/scraper/base.py` — `_resolve_recipients()` helper, called from `_notify()` before passing to `NotificationService.send()`
17. `src/orchestrator/manager.py` — pass `profile_id` through `_scraper_entry` to the scraper constructor
18. `src/scraper/canada/scraper.py`, `src/scraper/uk/scraper.py` — accept and store `profile_id`
19. `src/app/routes/client.py` — `profile_link_telegram` and the email magic-link flow updated to support profile tokens

The scraper now does one extra DB read per `_notify()` call (only when no per-client override exists). Notification routing becomes profile-aware.

### Phase 5 — Polish (optional, do only if any phase reveals UX gaps)

- Profile rename from status page
- Re-apply for a profile (one submit, multiple pending apps)
- Delete a profile (cascade-set NULL on apps, or hard-delete per the cascade rule)
- Per-app notification override UI in the profile status page

---

## 9. Production Readiness Checklist

For the **existing** parallel-scraping path, the gaps are minor:

| Concern | Status | Notes |
|---|---|---|
| Multi-process isolation | ✅ | One Process per app, no shared state |
| Crash recovery | ✅ | 60s tick, exponential backoff, resume on boot |
| Graceful shutdown | ✅ | SIGTERM → split grace budget across agents |
| Secrets at rest | ✅ | Fernet encryption on password, mandatory `ENCRYPTION_KEY` |
| Secrets in flight | ⚠️ | No HTTPS enforced by app (relies on platform). TLS headers set but not required at the app layer |
| Rate limiting on public endpoints | ✅ | `/login`, `/client_submit`, magic-link, telegram webhook — all limited via Flask-Limiter |
| Observability | ⚠️ | Per-client logs (rotating 5MB×3), server.log, Sentry hooked in. No metrics endpoint (Prometheus). No structured logging |
| Health checks | ✅ | `/healthz/ready` (DB SELECT 1) + `/healthz/live` (cheap) + `/health` |
| Backups | ❌ | DB is ephemeral in prod (gitignored); no automated backup. Acceptable if "state loss on restart" is OK |
| Database migrations | ⚠️ | Idempotent `ALTER TABLE` pattern. No proper migration tool. Acceptable at this scale |
| Concurrency limits | ❌ | No cap on number of concurrent agents. Will exhaust memory at ~7-8 on Cloud Run 2Gi |
| Audit log | ❌ | No record of who approved/rejected/started what and when beyond the `clients` `updated_at` |
| CSRF on admin forms | ❌ | Out of scope per current directive. Rate limiting is the only protection |
| Multi-tenant isolation | ❌ | Single admin password. Not multi-tenant by design |

For the **new profile path**, additional concerns:

| Concern | Status | Notes |
|---|---|---|
| Profile-level credential rotation | ❌ | Credentials snapshotted at submit. Rotation = re-submit (acceptable for v1) |
| Profile token leakage | ⚠️ | Same as existing client token — it's the only auth. No expiry. Admin can rotate by deleting + re-issuing |
| Orphan profiles | ⚠️ | If all apps are rejected/deleted, profile row stays. Add a cleanup pass on the 60s recovery tick |
| Email verification under profile | Needs design | Magic link confirms against profile_id, but the email_confirmations table currently keys on user_id (= client_id). Phase 4 design above |

---

## 10. Open Questions for Approval

Before I write code, please confirm:

1. **Mode toggle or separate forms?** The proposed UX is one form with a Step 0 mode toggle. Alternative is `/client` (single) vs `/profile` (multi) — two separate URLs and templates. I recommend the toggle (less URL surface, single "Client" mental model). Confirm?

2. **Credentials: snapshot or live-inherit?** I recommend snapshot for credentials, live-inherit for notifications. Confirm?

3. **Admin approval granularity?** Per-application (each app approved individually, same as today) or per-profile (one click approves all apps under the profile)? Per-application is the safer default — admin might want to reject one app but accept the rest. Confirm?

4. **Is the orchestrator-per-application model final?** If yes, profiles are pure data grouping and the orchestrator code is untouched. If no (you want one process per profile that manages multiple apps concurrently), the scraper and orchestrator both need work — let me know before I start.

5. **Phase ordering OK?** Phase 1 (data) → Phase 2 (read-only) → Phase 3 (submit flow) → Phase 4 (notification inheritance). Each phase is independently shippable. Cut or reorder if needed.

---

## 11. Files That Will Change (Total Surface)

**New files (~7):**
- `src/domain/profile.py`
- `src/infrastructure/repositories/profile_repo.py`
- `src/app/templates/admin/profiles.html`
- `src/app/templates/partials/_profile_row.html`
- `src/app/templates/partials/_profile_apps.html`
- `src/app/static/js/views/client_form_profile.js`
- `src/app/static/js/views/profile_status.js`

**Modified files (~10):**
- `src/infrastructure/database.py` — schema
- `src/infrastructure/repositories/__init__.py` — export profile_repo
- `src/services/client_service.py` — `submit_profile_request`
- `src/services/notification_service.py` — `recipients` dict
- `src/app/routes/admin.py` — `/admin/profiles` + "Generate profile link" button
- `src/app/routes/client.py` — `/client_submit_profile`, `/profile_status/<token>`, profile telegram/email endpoints
- `src/app/templates/client/form.html` — mode toggle + profile wizard
- `src/app/templates/admin/clients.html` — Profile column + filter + new button
- `src/app/templates/partials/_clients_tbody.html` or `_client_row.html` — Profile column
- `src/orchestrator/manager.py` — pass `profile_id` through
- `src/scraper/base.py` — `_resolve_recipients()`
- `src/scraper/canada/scraper.py`, `src/scraper/uk/scraper.py` — accept `profile_id`

**Untouched (the bulk of the app):**
- All Flask blueprints except `client.py` and `admin.py`
- All infrastructure except `database.py` and the new `profile_repo.py`
- The `VisaScraper` run loop, login flow, polling, screenshots, error handling
- The orchestrator's process lifecycle, crash recovery, shutdown logic
- The notification transports (email, telegram, sms)
- The Telegram webhook, magic-link confirmation, settings, Sentry init
- All auth/session/header/rate-limit/security middleware

The parallel-scraping substrate stays exactly as it is. The new feature is an additive layer above it.
