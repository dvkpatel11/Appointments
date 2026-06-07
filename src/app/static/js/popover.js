// popover.js — wire the topbar popovers (notifications + user menu).
//
// Anchors are <div data-popover="<name>"> wrapping the trigger button.
// Clicking data-action="open-<name>" opens a .popover next to the anchor.
// Clicking outside or pressing Esc closes any open popover. Only one
// popover can be open at a time.

(function () {
  let openPopover = null;
  const ALERT_LIMIT = 20;

  // ── Open / close ─────────────────────────────────────────────────────
  function close() {
    if (!openPopover) return;
    openPopover.remove();
    openPopover = null;
    document.removeEventListener("click", onDocClick, true);
    document.removeEventListener("keydown", onKey, true);
  }

  function open(anchor, popoverEl) {
    close();
    if (!anchor) return;
    popoverEl.dataset.popoverEl = "";
    anchor.appendChild(popoverEl);
    requestAnimationFrame(() => popoverEl.classList.add("popover--in"));
    openPopover = popoverEl;
    // Defer handler attach so the click that opened us doesn't immediately close.
    setTimeout(() => {
      document.addEventListener("click", onDocClick, true);
      document.addEventListener("keydown", onKey, true);
    }, 0);
  }

  function onDocClick(e) {
    if (!openPopover) return;
    if (openPopover.contains(e.target)) return;
    const anchor = openPopover.parentElement;
    if (anchor && anchor.contains(e.target)) return;
    close();
  }

  function onKey(e) {
    if (e.key === "Escape") close();
  }

  // ── Notifications popover ────────────────────────────────────────────
  function renderNotifications() {
    const alerts = (window.store && window.store.getAlerts && window.store.getAlerts()) || [];
    const wrap = document.createElement("div");
    wrap.className = "popover";
    wrap.setAttribute("role", "dialog");
    wrap.setAttribute("aria-label", "Notifications");

    const head = `
      <div class="popover__head">
        <div style="display: flex; align-items: center; justify-content: space-between; gap: var(--s-2);">
          <strong>Notifications</strong>
          ${alerts.length ? `<button class="btn btn--ghost btn--xs" type="button" data-popover-clear>Clear all</button>` : ""}
        </div>
      </div>
    `;

    let body = "";
    if (alerts.length === 0) {
      body = `
        <div style="padding: var(--s-5) var(--s-3); text-align: center; color: var(--c-text-muted);">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" style="margin-bottom: var(--s-2);"><polyline points="20 6 9 17 4 12"/></svg>
          <div style="font-size: var(--text-sm);">All caught up</div>
          <div style="font-size: var(--text-xs); margin-top: 2px;">No alerts in this session.</div>
        </div>
      `;
    } else {
      body = alerts
        .slice(0, ALERT_LIMIT)
        .map((a) => {
          const tone = a.severity || "info";
          const ts = a._ts ? new Date(a._ts).toLocaleTimeString() : "";
          return `
            <div class="popover__item" data-alert-id="${a._id || ""}">
              <span class="popover__item-icon" aria-hidden="true">
                ${toneIcon(tone)}
              </span>
              <div class="popover__item-body">
                <div class="popover__item-title">${escapeHtml(a.title || "Alert")}</div>
                ${a.msg ? `<div class="popover__item-sub">${escapeHtml(a.msg)}</div>` : ""}
                ${ts ? `<div class="popover__item-sub" style="opacity:.6">${ts}</div>` : ""}
              </div>
            </div>
          `;
        })
        .join("");
    }

    wrap.innerHTML = head + body;

    // Wire Clear all
    const clear = wrap.querySelector("[data-popover-clear]");
    if (clear) {
      clear.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (window.store && window.store.clearAlerts) window.store.clearAlerts();
        open(anchorFor("notifications"), renderNotifications());
      });
    }
    return wrap;
  }

  function toneIcon(tone) {
    const common = 'width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"';
    if (tone === "error") return `<svg ${common}><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>`;
    if (tone === "warning") return `<svg ${common}><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/></svg>`;
    if (tone === "success") return `<svg ${common}><polyline points="20 6 9 17 4 12"/></svg>`;
    return `<svg ${common}><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>`;
  }

  // ── User menu popover ───────────────────────────────────────────────
  function renderUserMenu() {
    const wrap = document.createElement("div");
    wrap.className = "popover";
    wrap.setAttribute("role", "menu");
    wrap.setAttribute("aria-label", "User menu");
    wrap.innerHTML = `
      <div class="popover__head">
        <div class="popover__item-title">Admin</div>
        <div class="popover__item-sub" data-user-menu-version>Loading version…</div>
      </div>
      <a class="popover__item" href="/health" target="_blank" rel="noopener" role="menuitem">
        <span class="popover__item-icon" aria-hidden="true">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>
        </span>
        <div class="popover__item-body">
          <div class="popover__item-title">System health</div>
          <div class="popover__item-sub">/health · opens in new tab</div>
        </div>
      </a>
      <a class="popover__item" href="/admin/logs" role="menuitem">
        <span class="popover__item-icon" aria-hidden="true">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
        </span>
        <div class="popover__item-body">
          <div class="popover__item-title">View logs</div>
        </div>
      </a>
      <div class="popover__divider"></div>
      <a class="popover__item popover__item--danger" href="/logout" role="menuitem">
        <span class="popover__item-icon" aria-hidden="true">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
        </span>
        <div class="popover__item-body">
          <div class="popover__item-title">Sign out</div>
        </div>
      </a>
    `;
    // Pop version in async.
    fetch("/admin/version", { credentials: "same-origin" })
      .then((r) => (r.ok ? r.json() : null))
      .then((v) => {
        const el = wrap.querySelector("[data-user-menu-version]");
        if (el && v) el.textContent = `v${v.version} · ${v.commit}`;
      })
      .catch(() => {});
    return wrap;
  }

  function anchorFor(name) {
    return document.querySelector(`[data-popover="${name}"]`);
  }

  // ── Trigger clicks ───────────────────────────────────────────────────
  document.addEventListener("click", (e) => {
    const trigger = e.target.closest("[data-action^='open-']");
    if (!trigger) return;
    const action = trigger.getAttribute("data-action") || "";
    const name = action.replace(/^open-/, "");
    if (name !== "notifications" && name !== "user-menu") return;
    e.preventDefault();
    e.stopPropagation();
    const anchor = anchorFor(name);
    if (!anchor) return;
    if (openPopover && openPopover.parentElement === anchor) {
      close();
      return;
    }
    const popover = name === "notifications" ? renderNotifications() : renderUserMenu();
    open(anchor, popover);
  });

  // ── Helpers ─────────────────────────────────────────────────────────
  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  window.popover = { close, open };
})();
