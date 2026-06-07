// views/dashboard.js — wire the dashboard view to the reactive store.

(async function () {
  // Wait for store + sse to be available.
  await new Promise((resolve) => {
    if (window.store && window.sse) return resolve();
    const t = setInterval(() => {
      if (window.store && window.sse) { clearInterval(t); resolve(); }
    }, 30);
  });

  window.store.restore();

  // 1. Hydrate from /snapshot.
  try {
    const res = await fetch(window.APP.snapshotUrl, { credentials: "same-origin" });
    if (res.ok) {
      const snap = await res.json();
      window.store.hydrate(snap);
      applyMetrics(snap.metrics);
      applyPendingPill(snap.metrics.pending);
    }
  } catch (e) {
    window.toast && window.toast("Snapshot failed", "error", String(e));
  }

  // 2. On metric changes (from SSE), update KPI tiles in place.
  window.store.subscribeSlice("metrics", (s) => {
    applyMetrics(s.metrics);
    applyPendingPill(s.metrics.pending);
  });

  // 3. On any state change, re-fetch the htmx fragments that the page
  //    initially loaded. This keeps the rendered HTML in sync with reality
  //    without us having to write a custom renderer for every section.
  let pendingRefetch = null;
  function refetchFragments() {
    if (pendingRefetch) return;
    pendingRefetch = setTimeout(() => {
      pendingRefetch = null;
      const dash = document.getElementById("dash-metrics");
      const monitors = document.querySelector("[data-dash-monitors]");
      if (dash) htmx.ajax("GET", dash.dataset.href || dash.getAttribute("hx-get"), dash);
      if (monitors) htmx.ajax("GET", monitors.getAttribute("hx-get"), monitors);
    }, 200);
  }
  window.store.subscribeSlice("snapshot", refetchFragments);
  window.store.subscribeSlice("screenshots", refetchFragments);

  // 4. Connection status — flash the topbar dot amber when disconnected.
  window.store.subscribeSlice("connection", (s) => {
    const dot = document.querySelector("[data-status-dot]");
    if (!dot) return;
    dot.classList.remove("topbar__dot--ok", "topbar__dot--warn", "topbar__dot--down");
    dot.classList.add(s.connected ? "topbar__dot--ok" : "topbar__dot--warn");
    dot.title = s.connected ? "Live updates connected" : "Reconnecting…";
  });

  function applyMetrics(m) {
    if (!m) return;
    const tile = (label) => {
      const el = document.querySelector(`[data-stat="${label}"] [data-stat-value]`);
      if (el) el.textContent = m[label] ?? "—";
    };
    tile("total");
    tile("running");
    tile("pending");
    tile("errors-24h");
  }

  function applyPendingPill(n) {
    const pill = document.querySelector("[data-pill='pending-count']");
    if (!pill) return;
    if (n && n > 0) {
      pill.hidden = false;
      pill.textContent = String(n);
    } else {
      pill.hidden = true;
    }
  }
})();
