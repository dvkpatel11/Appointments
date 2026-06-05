// toast.js — minimal toast manager.
// Public API: window.toast(title, tone, msg, options?)
//   tone: 'success' | 'error' | 'warning' | 'info'

(function () {
  const ICONS = {
    success: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="20 6 9 17 4 12"/></svg>',
    error:   '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>',
    warning: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
    info:    '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>',
  };

  const DEFAULTS = { duration: 4000 };

  function show(title, tone = "info", msg = "", options = {}) {
    const stack = document.querySelector("[data-toast-stack]");
    if (!stack) return;
    const opts = { ...DEFAULTS, ...options };
    const el = document.createElement("div");
    el.className = "toast toast--" + tone;
    el.setAttribute("role", tone === "error" ? "alert" : "status");
    el.innerHTML = `
      <span class="toast__icon">${ICONS[tone] || ICONS.info}</span>
      <div class="toast__body">
        <div class="toast__title">${escapeHtml(title)}</div>
        ${msg ? `<div class="toast__msg">${escapeHtml(msg)}</div>` : ""}
      </div>
      <button class="btn btn--ghost btn--icon btn--sm" type="button" aria-label="Dismiss" data-toast-dismiss>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
      </button>
    `;
    el.querySelector("[data-toast-dismiss]").addEventListener("click", () => dismiss(el));
    stack.appendChild(el);
    if (opts.duration > 0) {
      setTimeout(() => dismiss(el), opts.duration);
    }
    return el;
  }

  function dismiss(el) {
    if (!el || !el.parentNode) return;
    el.style.transition = "opacity 200ms ease, transform 200ms ease";
    el.style.opacity = "0";
    el.style.transform = "translateX(20px)";
    setTimeout(() => el.parentNode && el.parentNode.removeChild(el), 200);
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  window.toast = show;
})();
