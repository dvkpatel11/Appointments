// theme.js — light/dark toggle, persistent in localStorage.
// Bootstrapped in <head> to avoid FOUC; this file wires the toggle button.

(function () {
  const STORAGE_KEY = "visactrl:theme";

  function current() {
    return document.documentElement.classList.contains("theme-dark") ? "dark" : "light";
  }

  function apply(theme) {
    const root = document.documentElement;
    root.classList.remove("theme-light", "theme-dark");
    root.classList.add("theme-" + theme);
    try {
      localStorage.setItem(STORAGE_KEY, theme);
    } catch (e) {
      // ignore (private mode)
    }
    syncIcons();
  }

  function syncIcons() {
    const dark = current() === "dark";
    document.querySelectorAll("[data-theme-icon]").forEach((el) => {
      el.hidden = el.dataset.themeIcon === (dark ? "sun" : "moon");
    });
  }

  function toggle() {
    apply(current() === "dark" ? "light" : "dark");
  }

  document.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-action='toggle-theme']");
    if (btn) {
      e.preventDefault();
      toggle();
    }
  });

  // Initial icon sync (page may load with theme already applied)
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", syncIcons);
  } else {
    syncIcons();
  }

  window.theme = { apply, toggle, current };
})();
