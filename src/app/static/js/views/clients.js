// views/clients.js — wire the clients view: bulk select, search, filters, density, modals, drawer, live refetch.

(async function () {
  await new Promise((resolve) => {
    if (window.store) return resolve();
    const t = setInterval(() => {
      if (window.store) { clearInterval(t); resolve(); }
    }, 30);
  });

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  const tbody = $("#clients-tbody");
  const bulkBar = $("[data-bulk-bar]");
  const bulkCount = $("[data-bulk-count]");

  // 1. Bulk select — show bar when ≥1 row checked, update count.
  function refreshBulk() {
    const checked = $$("[data-row-select]:checked", tbody);
    if (bulkCount) bulkCount.textContent = String(checked.length);
    if (bulkBar) bulkBar.hidden = checked.length === 0;
    const all = $$("[data-row-select]", tbody);
    const selectAll = $("[data-select-all]");
    if (selectAll) {
      selectAll.checked = all.length > 0 && checked.length === all.length;
      selectAll.indeterminate = checked.length > 0 && checked.length < all.length;
    }
  }

  document.addEventListener("change", (e) => {
    if (e.target.matches("[data-row-select]")) refreshBulk();
    if (e.target.matches("[data-select-all]")) {
      const checked = e.target.checked;
      $$("[data-row-select]", tbody).forEach((cb) => { cb.checked = checked; });
      refreshBulk();
    }
  });

  // 2. Bulk action handlers.
  document.addEventListener("click", async (e) => {
    const btn = e.target.closest("[data-bulk-action]");
    if (!btn) return;
    const action = btn.dataset.bulkAction;
    if (action === "clear") {
      $$("[data-row-select]", tbody).forEach((cb) => { cb.checked = false; });
      $("[data-select-all]") && ($("[data-select-all]").checked = false);
      refreshBulk();
      return;
    }
    const ids = $$("[data-row-select]:checked", tbody).map((cb) => cb.value);
    if (ids.length === 0) return;
    if (action === "start" || action === "stop") {
      const endpoint = action === "start" ? "/admin/clients/bulk-start" : "/admin/clients/bulk-stop";
      btn.disabled = true;
      try {
        const res = await fetch(endpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "same-origin",
          body: JSON.stringify({ ids }),
        });
        const data = await res.json().catch(() => ({}));
        if (res.ok) {
          const results = data.results || {};
          const ok = Object.values(results).filter((v) => v === (action === "start" ? "started" : "stopped")).length;
          const bad = ids.length - ok;
          const tone = bad === 0 ? "success" : "info";
          const verb = action === "start" ? "started" : "stopped";
          const msg = bad === 0
            ? `Bulk ${verb}: ${ok} client(s)`
            : `Bulk ${verb}: ${ok} ok, ${bad} failed`;
          window.toast && window.toast(`Bulk ${verb}`, tone, msg);
          if (tbody && tbody.getAttribute("hx-get")) {
            htmx.ajax("GET", tbody.getAttribute("hx-get"), tbody);
          }
        } else {
          window.toast && window.toast(`Bulk ${action} failed`, "error", data.message || `HTTP ${res.status}`);
        }
      } catch (err) {
        window.toast && window.toast(`Bulk ${action} failed`, "error", String(err));
      } finally {
        btn.disabled = false;
      }
    } else if (action === "export") {
      const rows = ids.map((id) => {
        const tr = tbody.querySelector(`[data-row-id="${id}"]`);
        if (!tr) return null;
        return {
          id,
          name: $(".table__name-text strong", tr)?.textContent?.trim(),
          email: $(".table__name-text small", tr)?.textContent?.trim(),
          state: tr.dataset.state,
          visa: tr.dataset.visa,
        };
      }).filter(Boolean);
      const blob = new Blob([JSON.stringify(rows, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `clients-export-${Date.now()}.json`;
      a.click();
      URL.revokeObjectURL(url);
    }
  });

  // 3. Table search — hide non-matching rows.
  const search = $("[data-table-search]");
  if (search) {
    search.addEventListener("input", () => {
      const q = search.value.trim().toLowerCase();
      $$("[data-row-id]", tbody).forEach((tr) => {
        tr.hidden = q && !tr.textContent.toLowerCase().includes(q);
      });
    });
  }

  // 4. Filter selects (state, visa_type).
  function applyFilters() {
    const stateFilter = $("[data-filter='state']")?.value || "";
    const visaFilter = $("[data-filter='visa_type']")?.value || "";
    $$("[data-row-id]", tbody).forEach((tr) => {
      const stateOk = !stateFilter || tr.dataset.state === stateFilter;
      const visaOk = !visaFilter || tr.dataset.visa === visaFilter;
      tr.hidden = !(stateOk && visaOk);
    });
  }
  document.addEventListener("change", (e) => {
    if (e.target.matches("[data-filter]")) applyFilters();
  });

  // 5. Row density toggle.
  const table = $("[data-clients-table]");
  $$("[data-density]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const mode = btn.dataset.density;
      $$("[data-density]").forEach((b) => b.setAttribute("aria-pressed", String(b === btn)));
      if (table) {
        table.classList.remove("table--density-comfortable", "table--density-compact");
        table.classList.add("table--density-" + mode);
      }
      try { localStorage.setItem("visactrl:clients:density", mode); } catch (e) {}
    });
  });
  try {
    const saved = localStorage.getItem("visactrl:clients:density");
    if (saved && table) {
      table.classList.remove("table--density-comfortable", "table--density-compact");
      table.classList.add("table--density-" + saved);
      $$("[data-density]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.density === saved)));
    }
  } catch (e) {}

  // 6. Modal open/close (link-modal).
  function openModal(name) {
    const modal = $(`[data-modal="${name}"]`);
    if (modal) modal.hidden = false;
    document.body.style.overflow = "hidden";
  }
  function closeModal(name) {
    const modal = $(`[data-modal="${name}"]`);
    if (modal) modal.hidden = true;
    document.body.style.overflow = "";
  }
  document.addEventListener("click", (e) => {
    const trigger = e.target.closest("[data-modal-trigger]");
    if (trigger) {
      e.preventDefault();
      openModal(trigger.dataset.modalTrigger);
      return;
    }
    const closer = e.target.closest("[data-modal-close]");
    if (closer) {
      const modal = closer.closest("[data-modal]");
      if (modal) closeModal(modal.dataset.modal);
    }
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") $$("[data-modal]").forEach((m) => { if (!m.hidden) closeModal(m.dataset.modal); });
  });

  // 7. Drawer open/close. The persistent <aside id="client-drawer"> lives
  //    in clients.html. htmx swaps the body content into #client-drawer-body.
  //    We just toggle the .hidden attribute on the persistent container.
  const drawer = $("#client-drawer");
  const overlay = $("[data-drawer-overlay]");
  function openDrawer() {
    if (!drawer) return;
    drawer.hidden = false;
    if (overlay) overlay.hidden = false;
    requestAnimationFrame(() => drawer.classList.add("drawer--in"));
    document.body.style.overflow = "hidden";
  }
  function closeDrawer() {
    if (!drawer) return;
    drawer.classList.remove("drawer--in");
    drawer.hidden = true;
    if (overlay) overlay.hidden = true;
    document.body.style.overflow = "";
  }
  document.addEventListener("click", (e) => {
    const trigger = e.target.closest("[data-drawer-trigger]");
    if (trigger) {
      e.preventDefault();
      openDrawer();
      const title = trigger.getAttribute("data-drawer-title");
      const titleEl = drawer && drawer.querySelector("[data-drawer-title]");
      if (title && titleEl) titleEl.textContent = title;
      return;
    }
    if (e.target.closest("[data-drawer-close]")) {
      closeDrawer();
      return;
    }
    if (overlay && e.target === overlay) closeDrawer();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && drawer && !drawer.hidden) closeDrawer();
  });

  // 8. Live refetch on snapshot changes.
  window.store.subscribeSlice("snapshot", () => {
    if (tbody && tbody.getAttribute("hx-get")) {
      htmx.ajax("GET", tbody.getAttribute("hx-get"), tbody);
    }
    refreshBulk();
  });

  // 9. Hydrate from snapshot to set the active count pill.
  try {
    const res = await fetch(window.APP.snapshotUrl, { credentials: "same-origin" });
    if (res.ok) {
      const snap = await res.json();
      window.store.hydrate(snap);
      const pill = $("[data-pill='active-count']");
      if (pill) {
        const n = (snap.metrics && snap.metrics.running) || 0;
        pill.hidden = n === 0;
        pill.textContent = String(n);
      }
    }
  } catch (e) {
    window.toast && window.toast("Clients snapshot failed", "error", String(e));
  }
})();
