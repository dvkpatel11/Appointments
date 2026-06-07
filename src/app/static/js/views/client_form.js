// views/client_form.js — 2-step wizard step navigation for /client/<token>.
// Pre-submit only. Submit + post-submit logic stays inline in the template.

(function () {
  const form = document.getElementById("missionForm");
  if (!form) return;

  const panels = Array.from(form.querySelectorAll("[data-panel]"));
  const steps = Array.from(form.querySelectorAll("[data-step]"));
  let current = 0;

  function show(i) {
    if (i < 0 || i >= panels.length) return;
    panels.forEach((p, idx) => { p.hidden = idx !== i; });
    steps.forEach((s, idx) => {
      s.classList.toggle("is-active", idx === i);
      s.classList.toggle("is-done", idx < i);
      s.setAttribute("aria-current", idx === i ? "step" : "false");
    });
    current = i;
    const first = panels[i].querySelector("input, select, textarea, button:not([type='hidden'])");
    if (first && i > 0) first.focus({ preventScroll: true });
    panels[i].scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function clearError(panel) {
    const err = panel.querySelector(".wizard-error");
    if (err) err.remove();
  }

  function showError(panel, msg) {
    clearError(panel);
    const err = document.createElement("p");
    err.className = "wizard-error";
    err.setAttribute("role", "alert");
    err.textContent = msg;
    panel.insertBefore(err, panel.firstChild.nextSibling);
  }

  function validatePanel(i) {
    clearError(panels[i]);
    const required = panels[i].querySelectorAll("[required]");
    const missing = [];
    required.forEach((el) => {
      el.classList.remove("is-invalid");
      if (!el.value.trim()) {
        el.classList.add("is-invalid");
        missing.push(el);
      }
    });
    if (missing.length) {
      showError(panels[i], "Please fill in all required fields.");
      missing[0].focus();
      return false;
    }
    return true;
  }

  form.addEventListener("click", (e) => {
    if (e.target.closest("[data-wizard-next]")) {
      e.preventDefault();
      if (validatePanel(current)) show(current + 1);
    } else if (e.target.closest("[data-wizard-prev]")) {
      e.preventDefault();
      show(current - 1);
    }
  });

  form.addEventListener("keydown", (e) => {
    if (e.key !== "Enter") return;
    if (e.target.matches("textarea, button[type='submit']")) return;
    if (current >= panels.length - 1) return;
    e.preventDefault();
    if (validatePanel(current)) show(current + 1);
  });

  // Clear invalid state as the user types.
  form.addEventListener("input", (e) => {
    if (e.target.classList.contains("is-invalid") && e.target.value.trim()) {
      e.target.classList.remove("is-invalid");
      const panel = e.target.closest("[data-panel]");
      if (panel && !panel.querySelector(".is-invalid")) clearError(panel);
    }
  });

  show(0);
})();
