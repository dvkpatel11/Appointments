// command.js — ⌘K / Ctrl+K command palette. Minimal v1 (search nav).

(function () {
  const NAV = [
    { label: "Dashboard", href: "/admin/", hint: "G D" },
    { label: "Clients",  href: "/admin/clients", hint: "G C" },
    { label: "Requests", href: "/admin/requests", hint: "G R" },
    { label: "Settings", href: "/admin/settings", hint: "G S" },
    { label: "Logs",     href: "/admin/logs", hint: "G L" },
  ];

  let overlay = null;
  let input = null;
  let list = null;
  let active = 0;
  let items = [];

  function open() {
    if (overlay) return;
    overlay = document.createElement("div");
    overlay.className = "cmd-overlay";
    overlay.setAttribute("role", "dialog");
    overlay.setAttribute("aria-modal", "true");
    overlay.setAttribute("aria-label", "Command palette");
    overlay.innerHTML = `
      <div class="cmd" role="document">
        <input class="cmd__input" type="text" placeholder="Search pages, actions…" aria-label="Command query" />
        <div class="cmd__list" role="listbox"></div>
      </div>
    `;
    document.body.appendChild(overlay);
    input = overlay.querySelector(".cmd__input");
    list = overlay.querySelector(".cmd__list");
    items = NAV.slice();
    render();

    input.addEventListener("input", () => {
      const q = input.value.trim().toLowerCase();
      items = q
        ? NAV.filter((n) => n.label.toLowerCase().includes(q))
        : NAV.slice();
      active = 0;
      render();
    });

    input.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown") { e.preventDefault(); active = Math.min(items.length - 1, active + 1); render(); }
      else if (e.key === "ArrowUp") { e.preventDefault(); active = Math.max(0, active - 1); render(); }
      else if (e.key === "Enter") { e.preventDefault(); commit(); }
      else if (e.key === "Escape") { e.preventDefault(); close(); }
    });

    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) close();
    });

    requestAnimationFrame(() => input.focus());
  }

  function render() {
    if (!list) return;
    list.innerHTML = items
      .map(
        (item, i) => `
        <div class="cmd__item" role="option" aria-selected="${i === active}" data-index="${i}">
          <span>${item.label}</span>
          <span class="cmd__item-hint">${item.hint || ""}</span>
        </div>`
      )
      .join("") || '<div class="cmd__item" aria-disabled="true">No matches</div>';

    list.querySelectorAll(".cmd__item").forEach((el) => {
      el.addEventListener("mouseenter", () => {
        active = Number(el.dataset.index);
        list.querySelectorAll(".cmd__item").forEach((x, i) => x.setAttribute("aria-selected", String(i === active)));
      });
      el.addEventListener("click", () => {
        active = Number(el.dataset.index);
        commit();
      });
    });
  }

  function commit() {
    const it = items[active];
    if (!it || !it.href) return;
    window.location.href = it.href;
  }

  function close() {
    if (!overlay) return;
    overlay.remove();
    overlay = null;
    input = null;
    list = null;
  }

  document.addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
      e.preventDefault();
      overlay ? close() : open();
    } else if (e.key === "Escape" && overlay) {
      close();
    }
  });

  document.addEventListener("click", (e) => {
    if (e.target.closest("[data-action='open-command']")) {
      e.preventDefault();
      open();
    }
  });

  window.command = { open, close };
})();
