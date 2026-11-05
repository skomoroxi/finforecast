// Menu, table expansion, technical-analysis tabs and live prices. Works as an enhancement: every
// number on a page is already in the HTML.
(function () {
  "use strict";

  const toggle = document.querySelector(".nav__toggle");
  const menu = document.getElementById("nav-menu");
  if (toggle && menu) {
    toggle.addEventListener("click", () => {
      const open = toggle.getAttribute("aria-expanded") !== "true";
      toggle.setAttribute("aria-expanded", String(open));
      menu.classList.toggle("open", open);
      document.body.style.overflow = open ? "hidden" : "";
    });
  }

  const dropdowns = document.querySelectorAll(".dropdown__btn");
  const closeAll = () => dropdowns.forEach((b) => b.setAttribute("aria-expanded", "false"));
  dropdowns.forEach((btn) =>
    btn.addEventListener("click", () => {
      const open = btn.getAttribute("aria-expanded") !== "true";
      closeAll();
      btn.setAttribute("aria-expanded", String(open));
    }),
  );
  document.addEventListener("click", (e) => {
    if (!e.target.closest(".dropdown")) closeAll();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeAll();
  });

  document.querySelectorAll(".dt__more").forEach((btn) => {
    btn.addEventListener("click", () => {
      const box = btn.closest(".dt");
      const open = box.dataset.collapsed === "true";
      box.dataset.collapsed = open ? "false" : "true";
      btn.setAttribute("aria-expanded", String(open));
      btn.textContent = open ? btn.dataset.less : `${btn.dataset.all} (${btn.dataset.total})`;
    });
  });

  document.querySelectorAll("[data-tabs]").forEach((root) => {
    const tabs = [...root.querySelectorAll('[role="tab"]')];
    const select = (tab) => {
      tabs.forEach((t) => {
        const on = t === tab;
        t.setAttribute("aria-selected", String(on));
        t.tabIndex = on ? 0 : -1;
        document.getElementById(t.getAttribute("aria-controls")).hidden = !on;
      });
      tab.focus();
    };
    tabs.forEach((tab, i) => {
      tab.addEventListener("click", () => select(tab));
      tab.addEventListener("keydown", (e) => {
        const step = { ArrowRight: 1, ArrowLeft: -1 }[e.key];
        if (step) select(tabs[(i + step + tabs.length) % tabs.length]);
      });
    });
  });

  // Live prices. Coins come straight from Binance's public stream, so the server carries no load.
  // Delayed US quotes come from our own cached endpoint. Anything else stays on the last close.
  const locale = document.documentElement.lang || "en";
  const formatUsd = (v) =>
    new Intl.NumberFormat(locale, {
      style: "currency",
      currency: "USD",
      maximumFractionDigits: v >= 1000 ? 0 : v >= 10 ? 2 : v >= 1 ? 3 : 4,
      maximumSignificantDigits: v < 0.01 ? 3 : undefined,
    }).format(v);

  function show(el, price, pct) {
    const value = el.querySelector("[data-price]");
    if (value) value.textContent = formatUsd(price);
    const change = el.querySelector("[data-change]");
    if (change && pct != null) {
      const up = pct >= 0;
      change.textContent = `${up ? "▲ +" : "▼ −"}${Math.abs(pct).toFixed(2)}%`;
      change.className = `chg ${up ? "up" : "down"}`;
    }
  }

  const streams = {};
  document.querySelectorAll("[data-stream]").forEach((el) => (streams[el.dataset.stream] ??= []).push(el));
  const names = Object.keys(streams);
  if (names.length && "WebSocket" in window) {
    const socket = new WebSocket(
      `wss://stream.binance.com:9443/stream?streams=${names.map((n) => `${n}@miniTicker`).join("/")}`,
    );
    socket.addEventListener("message", (event) => {
      const { stream, data } = JSON.parse(event.data);
      const price = Number(data.c);
      const open = Number(data.o);
      (streams[stream.split("@")[0]] || []).forEach((el) => show(el, price, (price / open - 1) * 100));
    });
  }

  const quoted = document.querySelectorAll("[data-quote]");
  if (quoted.length) {
    const refresh = () =>
      fetch("/api/live/")
        .then((r) => r.json())
        .then((quotes) => {
          quoted.forEach((el) => {
            const q = quotes[el.dataset.quote];
            if (q) show(el, q.price, q.change_pct);
          });
        })
        .catch(() => {});
    refresh();
    setInterval(() => {
      if (!document.hidden) refresh();
    }, 60000);
  }
})();
