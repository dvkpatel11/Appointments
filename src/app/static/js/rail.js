// rail.js — collapsible sidebar rail. State persists in localStorage.

(function () {
  const STORAGE_KEY = "visactrl:rail";
  const shell = document.querySelector(".l-shell");
  if (!shell) return;

  function current() {
    return shell.dataset.rail === "expanded" ? "expanded" : "collapsed";
  }

  function apply(state) {
    shell.dataset.rail = state;
    try { localStorage.setItem(STORAGE_KEY, state); } catch (e) {}
  }

  function toggle() {
    apply(current() === "collapsed" ? "expanded" : "collapsed");
  }

  // Restore prior preference.
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === "expanded" || saved === "collapsed") shell.dataset.rail = saved;
  } catch (e) {}

  document.addEventListener("click", (e) => {
    if (e.target.closest("[data-action='toggle-rail']")) {
      e.preventDefault();
      toggle();
    }
  });

  // Keyboard: ⌘\ / Ctrl+\ to toggle.
  document.addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === "\\") {
      e.preventDefault();
      toggle();
    }
  });

  window.rail = { toggle, apply, current };
})();
