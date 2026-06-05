// views/requests.js — wire the requests inbox: tabs, live counts, modal trigger.

(async function () {
  await new Promise((resolve) => {
    if (window.store) return resolve();
    const t = setInterval(() => {
      if (window.store) { clearInterval(t); resolve(); }
    }, 30);
  });

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  // 1. Tabs — click → toggle aria-selected + show/hide panel.
  function activateTab(tab) {
    const tabsContainer = $("[data-tabs]");
    if (!tabsContainer) return;
    const target = tab.dataset.target;
    $$("[role='tab']", tabsContainer).forEach((t) => {
      t.setAttribute("aria-selected", String(t === tab));
      t.tabIndex = t === tab ? 0 : -1;
    });
    $$("[data-tab-panel]").forEach((p) => { p.hidden = ("#" + p.id) !== target; });
    try { localStorage.setItem("visactrl:requests:tab", tab.dataset.tab); } catch (e) {}
  }

  $$("[role='tab']").forEach((tab) => {
    tab.addEventListener("click", () => activateTab(tab));
    tab.addEventListener("keydown", (e) => {
      if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
      e.preventDefault();
      const tabs = $$("[role='tab']");
      const i = tabs.indexOf(tab);
      const next = tabs[(i + (e.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length];
      next && next.focus();
      next && activateTab(next);
    });
  });

  // 2. Restore last tab.
  try {
    const saved = localStorage.getItem("visactrl:requests:tab");
    if (saved) {
      const tab = $(`[data-tab='${saved}']`);
      if (tab) activateTab(tab);
    }
  } catch (e) {}

  // 3. Modal: reject modal — populate dynamic name from data-reject-name.
  document.addEventListener("click", (e) => {
    const trigger = e.target.closest("[data-modal-trigger='reject-modal']");
    if (!trigger) return;
    e.preventDefault();
    const token = trigger.dataset.rejectToken;
    const name = trigger.dataset.rejectName || "this client";
    const mount = $("[data-modal-mount]");
    if (!mount) return;
    mount.innerHTML = `
      <div class="modal-overlay" data-modal="reject-modal">
        <div class="modal" role="dialog" aria-modal="true" aria-labelledby="reject-title">
          <div class="modal__header">
            <div>
              <h3 class="modal__title" id="reject-title">Reject request</h3>
              <p class="modal__sub">${name}</p>
            </div>
            <button class="btn btn--ghost btn--icon btn--sm" type="button" data-modal-close aria-label="Close">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            </button>
          </div>
          <form hx-post="/admin/reject/${token}" hx-swap="none">
            <div class="modal__body">
              <div class="field">
                <label class="field__label" for="reject-reason">Reason</label>
                <textarea class="input" id="reject-reason" name="reason" rows="3" required></textarea>
              </div>
            </div>
            <div class="modal__footer">
              <button class="btn btn--secondary" type="button" data-modal-close>Cancel</button>
              <button class="btn btn--primary" type="submit">Reject</button>
            </div>
          </form>
        </div>
      </div>`;
    const modal = mount.querySelector("[data-modal='reject-modal']");
    modal && (modal.hidden = false);
    document.body.style.overflow = "hidden";
  });
  document.addEventListener("click", (e) => {
    const closer = e.target.closest("[data-modal-close]");
    if (closer) {
      const modal = closer.closest("[data-modal]");
      if (modal) {
        modal.hidden = true;
        document.body.style.overflow = "";
      }
    }
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      $$("[data-modal]").forEach((m) => {
        if (!m.hidden) { m.hidden = true; document.body.style.overflow = ""; }
      });
    }
  });

  // 4. Live counts from store.
  function updateCounts() {
    const s = window.store.get();
    const buckets = { pending: 0, approved: 0, rejected: 0 };
    Object.values(s.clients || {}).forEach((c) => {
      if (buckets[c.state] !== undefined) buckets[c.state]++;
    });
    Object.entries(buckets).forEach(([k, n]) => {
      const pill = $(`[data-count='${k}']`);
      if (pill) pill.textContent = String(n);
    });
  }
  window.store.subscribeSlice("snapshot", updateCounts);
  window.store.subscribeSlice("metrics", updateCounts);

  // 5. Hydrate snapshot.
  try {
    const res = await fetch(window.APP.snapshotUrl, { credentials: "same-origin" });
    if (res.ok) {
      const snap = await res.json();
      window.store.hydrate(snap);
      updateCounts();
    }
  } catch (e) {
    window.toast && window.toast("Requests snapshot failed", "error", String(e));
  }
})();
