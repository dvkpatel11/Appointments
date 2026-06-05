// views/settings.js — wire the settings view: 5-tab switcher, export config.

(async function () {
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  // 1. Tabs.
  function activateTab(tab) {
    const target = tab.dataset.target;
    $$("[role='tab']").forEach((t) => {
      t.setAttribute("aria-selected", String(t === tab));
      t.tabIndex = t === tab ? 0 : -1;
    });
    $$("[data-tab-panel]").forEach((p) => { p.hidden = ("#" + p.id) !== target; });
    try { localStorage.setItem("visactrl:settings:tab", tab.dataset.tab); } catch (e) {}
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
    const saved = localStorage.getItem("visactrl:settings:tab");
    if (saved) {
      const tab = $(`[data-tab='${saved}']`);
      if (tab) activateTab(tab);
    }
  } catch (e) {}

  // 3. Export config — dump current form state as JSON.
  const exportBtn = $("[data-settings-export]");
  if (exportBtn) {
    exportBtn.addEventListener("click", () => {
      const data = {};
      $$("input, select, textarea").forEach((el) => {
        if (!el.name && !el.id) return;
        const key = el.name || el.id;
        if (el.type === "checkbox") data[key] = el.checked;
        else data[key] = el.value;
      });
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `visactrl-settings-${Date.now()}.json`;
      a.click();
      URL.revokeObjectURL(url);
      window.toast && window.toast("Config exported", "success", "Saved to downloads");
    });
  }
})();
