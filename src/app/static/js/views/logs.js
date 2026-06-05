// views/logs.js — wire the logs viewer: pause, clear, search, level filter, source filter, download.

(async function () {
  await new Promise((resolve) => {
    if (window.APP) return resolve();
    const t = setInterval(() => {
      if (window.APP) { clearInterval(t); resolve(); }
    }, 30);
  });

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  const viewer = $("[data-log-viewer]");
  const search = $("[data-log-search]");
  const sourceSel = $("[data-log-source]");
  const pauseBtn = $("[data-log-action='pause']");
  const clearBtn = $("[data-log-action='clear']");
  const downloadBtn = $("[data-log-action='download']");

  // 1. Pause/resume polling.
  function setPaused(paused) {
    window.__logPaused = paused;
    if (!pauseBtn) return;
    pauseBtn.setAttribute("aria-pressed", String(paused));
    const label = pauseBtn.querySelector("[data-label]");
    const pauseIcon = pauseBtn.querySelector("[data-icon='pause']");
    const playIcon = pauseBtn.querySelector("[data-icon='play']");
    if (label) label.textContent = paused ? "Resume" : "Pause";
    if (pauseIcon) pauseIcon.hidden = paused;
    if (playIcon) playIcon.hidden = !paused;
  }
  if (pauseBtn) {
    pauseBtn.addEventListener("click", () => setPaused(!window.__logPaused));
  }

  // 2. Clear viewer.
  if (clearBtn) {
    clearBtn.addEventListener("click", () => {
      if (viewer) {
        viewer.innerHTML = '<div style="padding: var(--s-6); text-align: center; color: rgba(250,250,250,0.4); font-size: var(--text-xs);">Log viewer cleared.</div>';
      }
    });
  }

  // 3. Filter visible lines by text + level.
  function applyFilters() {
    if (!viewer) return;
    const q = (search && search.value || "").trim().toLowerCase();
    const levelsOn = {
      error:   !!$("[data-log-level='error']:checked"),
      warning: !!$("[data-log-level='warning']:checked"),
      info:    !!$("[data-log-level='info']:checked"),
      success: !!$("[data-log-level='success']:checked"),
    };
    $$("[data-log-level]", viewer).forEach((line) => {
      const lvl = line.dataset.logLevel;
      const text = line.textContent.toLowerCase();
      line.hidden = !levelsOn[lvl] || (q && !text.includes(q));
    });
  }
  if (search) search.addEventListener("input", applyFilters);
  document.addEventListener("change", (e) => {
    if (e.target.matches("[data-log-level]")) applyFilters();
  });

  // 4. Source switch → re-fetch viewer.
  function refetch() {
    if (!viewer || window.__logPaused) return;
    const source = sourceSel ? sourceSel.value : "";
    const url = window.APP.logsStreamUrl
      + (source ? "?source=" + encodeURIComponent(source) : "");
    htmx.ajax("GET", url, viewer);
  }
  if (sourceSel) sourceSel.addEventListener("change", refetch);

  // 5. Download filtered lines.
  if (downloadBtn) {
    downloadBtn.addEventListener("click", () => {
      const visible = $$("[data-log-level]", viewer).filter((el) => !el.hidden);
      const text = visible.map((el) => el.textContent.trim()).join("\n") + "\n";
      const blob = new Blob([text], { type: "text/plain" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `visactrl-logs-${Date.now()}.txt`;
      a.click();
      URL.revokeObjectURL(url);
    });
  }

  // 6. Poll every 3s when not paused, and refilter after each htmx swap.
  let pollTimer = null;
  function startPolling() {
    if (pollTimer) return;
    pollTimer = setInterval(refetch, 3000);
  }
  if (viewer) {
    viewer.addEventListener("htmx:afterSwap", applyFilters);
    startPolling();
  }

  // 7. Initialize pause state.
  setPaused(false);
})();
