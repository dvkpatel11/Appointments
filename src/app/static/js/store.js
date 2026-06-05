// store.js — reactive in-memory store for the browser.
// Hydrates from /snapshot, applies SSE deltas, persists prefs to localStorage.
// Views subscribe via store.subscribe(listener) and re-render their slice.

(function () {
  const STORAGE_KEY = "visactrl:state:v1";

  const initial = {
    ts: 0,
    clients: {},     // id -> client dict
    states: {},      // id -> automation state dict
    pending: [],
    approved: [],
    metrics: { total: 0, running: 0, pending: 0, errors_24h: 0, active_24h: 0 },
    screenshots: {},
    settings: { email_enabled: "true", telegram_enabled: "false" },
    connected: false,
  };

  const state = structuredClone(initial);
  const listeners = new Set();
  const sliceListeners = new Map(); // key -> Set<fn>

  function notify(slice) {
    listeners.forEach((fn) => fn(state, slice));
    if (slice && sliceListeners.has(slice)) {
      sliceListeners.get(slice).forEach((fn) => fn(state));
    }
  }

  function get() {
    return state;
  }

  function setConnected(v) {
    if (state.connected !== v) {
      state.connected = v;
      notify("connection");
    }
  }

  function hydrate(snapshot) {
    Object.assign(state, snapshot);
    persist();
    notify("snapshot");
  }

  function applyDelta(type, data) {
    switch (type) {
      case "metric.tick":
        if (typeof data.pending === "number") {
          state.metrics.pending = data.pending;
          notify("metrics");
        }
        break;
      case "request.new":
        // Re-fetch snapshot on new request so the new client shows up.
        hydrate
          ? fetch(window.APP.snapshotUrl, { credentials: "same-origin" })
              .then((r) => (r.ok ? r.json() : null))
              .then((snap) => snap && hydrate(snap))
              .catch(() => {})
          : null;
        break;
      case "state.changed":
        // Re-fetch snapshot (cheap, <5KB) on any state change.
        fetch(window.APP.snapshotUrl, { credentials: "same-origin" })
          .then((r) => (r.ok ? r.json() : null))
          .then((snap) => snap && hydrate(snap))
          .catch(() => {});
        break;
      case "log.line":
        // No-op at the store level; views can listen directly.
        notify("log");
        if (window.toast && data && data.line && /ERROR|EXCEPTION/i.test(data.line)) {
          window.toast("Scraper error", "error", data.client_id, { duration: 6000 });
        }
        break;
      case "screenshot.ready":
        if (data && data.client_id && data.path) {
          state.screenshots[data.client_id] = data.path;
          notify("screenshots");
        }
        break;
      case "alert":
        if (data && window.toast) {
          window.toast(data.title || "Alert", data.severity || "info", data.msg || "");
        }
        break;
      default:
        break;
    }
  }

  function persist() {
    try {
      const small = { ts: state.ts, metrics: state.metrics, settings: state.settings };
      localStorage.setItem(STORAGE_KEY, JSON.stringify(small));
    } catch (e) {
      // ignore quota errors
    }
  }

  function restore() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return;
      const cached = JSON.parse(raw);
      if (cached.metrics) state.metrics = { ...state.metrics, ...cached.metrics };
      if (cached.settings) state.settings = { ...state.settings, ...cached.settings };
    } catch (e) {
      // ignore parse errors
    }
  }

  function subscribe(fn) {
    listeners.add(fn);
    return () => listeners.delete(fn);
  }

  function subscribeSlice(slice, fn) {
    if (!sliceListeners.has(slice)) sliceListeners.set(slice, new Set());
    sliceListeners.get(slice).add(fn);
    return () => sliceListeners.get(slice).delete(fn);
  }

  window.store = { get, hydrate, applyDelta, setConnected, subscribe, subscribeSlice, restore };
})();
