// sse.js — EventSource wrapper with auto-reconnect and typed dispatch.

(function () {
  const RECONNECT_BASE_MS = 1000;
  const RECONNECT_MAX_MS = 30000;

  let source = null;
  let attempt = 0;
  let intentionallyClosed = false;

  function connect(url) {
    if (source) source.close();
    intentionallyClosed = false;
    attempt = 0;
    open(url);
  }

  function open(url) {
    try {
      source = new EventSource(url, { withCredentials: true });
    } catch (e) {
      scheduleReconnect(url);
      return;
    }

    source.addEventListener("open", () => {
      attempt = 0;
      window.store && window.store.setConnected(true);
      setStatus("connected");
    });

    // Generic message handler catches every typed event; EventSource fires
    // onmessage only for unnamed events.
    const handler = (evt) => {
      let data = {};
      try {
        data = JSON.parse(evt.data);
      } catch (e) {
        return;
      }
      if (window.store) window.store.applyDelta(evt.type, data.data || data);
    };

    [
      "state.changed",
      "log.line",
      "screenshot.ready",
      "metric.tick",
      "request.new",
      "alert",
      "health",
    ].forEach((name) => source.addEventListener(name, handler));

    source.addEventListener("error", () => {
      if (intentionallyClosed) return;
      window.store && window.store.setConnected(false);
      setStatus("reconnecting");
      source.close();
      scheduleReconnect(url);
    });
  }

  function scheduleReconnect(url) {
    attempt++;
    const delay = Math.min(RECONNECT_BASE_MS * 2 ** (attempt - 1), RECONNECT_MAX_MS);
    setTimeout(() => !intentionallyClosed && open(url), delay);
  }

  function close() {
    intentionallyClosed = true;
    if (source) source.close();
    source = null;
  }

  function setStatus(state) {
    const el = document.querySelector("[data-sse-status]");
    if (!el) return;
    if (state === "connected") {
      el.textContent = "Live";
    } else {
      el.textContent = "Reconnecting…";
    }
  }

  // Auto-connect when the page is ready and a streamUrl was provided.
  document.addEventListener("DOMContentLoaded", () => {
    if (window.APP && window.APP.streamUrl) {
      connect(window.APP.streamUrl);
    }
  });

  window.sse = { connect, close };
})();
