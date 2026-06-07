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

  // 4. Send test — fetch admin.test_notification with the right recipient.
  const fieldByChannel = {
    email: "notif-test-email",
    telegram: "notif-test-chat",
    sms: "notif-test-phone",
  };
  const keyByChannel = { email: "email", telegram: "chat_id", sms: "phone" };
  document.addEventListener("click", async (e) => {
    const btn = e.target.closest("[data-test-channel]");
    if (!btn) return;
    e.preventDefault();
    const channel = btn.dataset.testChannel;
    const fieldId = fieldByChannel[channel];
    const payloadKey = keyByChannel[channel];
    const recipient = ($(`#${fieldId}`)?.value || "").trim();
    if (!recipient) {
      window.toast && window.toast("Missing recipient", "error", `Enter a ${payloadKey} first.`);
      return;
    }
    const original = btn.textContent;
    btn.disabled = true;
    btn.textContent = "SENDING…";
    try {
      const res = await fetch(`/admin/test_notification/${channel}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({ [payloadKey]: recipient }),
      });
      const data = await res.json().catch(() => ({}));
      if (res.ok && data.status === "ok") {
        window.toast && window.toast("Test sent", "success", `Check ${channel === "email" ? "inbox" : channel === "telegram" ? "your bot" : "your phone"}`);
      } else {
        window.toast && window.toast("Test failed", "error", data.message || `HTTP ${res.status}`);
      }
    } catch (err) {
      window.toast && window.toast("Test failed", "error", String(err));
    } finally {
      btn.disabled = false;
      btn.textContent = original;
    }
  });
})();
