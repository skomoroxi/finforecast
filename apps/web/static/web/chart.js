// Price chart with the forecast overlay. The library and data load only when the chart comes near
// the screen, so the page itself stays light.
(function () {
  "use strict";

  const COLORS = { arima: "#1431cd", reversion: "#b0662f", montecarlo: "#7a3fb0", consensus: "#181d27" };
  const RANGES = { "1M": 31, "6M": 183, "1Y": 366, "5Y": 1827, "10Y": 3653 };
  const library = document.currentScript.dataset.lib;

  const loadLibrary = () =>
    new Promise((resolve, reject) => {
      const tag = document.createElement("script");
      tag.src = library;
      tag.onload = resolve;
      tag.onerror = reject;
      document.head.appendChild(tag);
    });

  const toPoints = (rows) => rows.filter(([, v]) => v != null).map(([time, value]) => ({ time, value }));
  const day = (date) => date.toISOString().slice(0, 10);

  // The default of two decimals would show a $0.0000047 coin as 0.00.
  function priceFormat(price) {
    const digits = price >= 1000 ? 0 : price >= 10 ? 2 : price >= 1 ? 3 : Math.min(10, 3 - Math.floor(Math.log10(price)));
    const number = new Intl.NumberFormat(document.documentElement.lang || "en", {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    });
    return { type: "custom", minMove: 10 ** -digits, formatter: (value) => number.format(value) };
  }

  async function init(el) {
    const [, data] = await Promise.all([loadLibrary(), fetch(`/api/chart/${el.dataset.code}.json`).then((r) => r.json())]);
    const { createChart, AreaSeries, LineSeries, LineStyle } = window.LightweightCharts;
    const box = el.querySelector(".pc__chart");
    const color = el.dataset.color || "#8a96a8";
    const format = priceFormat(data.history.at(-1)[1]);
    const chart = createChart(box, {
      autoSize: true,
      layout: {
        background: { color: "#ffffff" },
        textColor: "rgba(24,29,39,0.62)",
        fontFamily: "Inter, system-ui, sans-serif",
        fontSize: 11,
        attributionLogo: false,
      },
      grid: { vertLines: { visible: false }, horzLines: { color: "#f0f0f0" } },
      rightPriceScale: { borderVisible: false },
      timeScale: { borderVisible: false },
      crosshair: { mode: 0 },
      handleScroll: false,
      handleScale: false,
    });

    chart
      .addSeries(AreaSeries, {
        lineColor: color,
        lineWidth: 2,
        topColor: `${color}38`,
        bottomColor: `${color}00`,
        priceLineColor: color,
        priceFormat: format,
      })
      .setData(toPoints(data.history));

    const band = () =>
      chart.addSeries(LineSeries, {
        color: "rgba(24,29,39,0.25)",
        lineWidth: 1,
        lineStyle: LineStyle.Dotted,
        lastValueVisible: false,
        priceLineVisible: false,
        crosshairMarkerVisible: false,
        priceFormat: format,
      });
    const low = band();
    const high = band();
    low.setData(toPoints(data.forecast.low));
    high.setData(toPoints(data.forecast.high));

    const lines = {};
    for (const key of ["arima", "reversion", "montecarlo", "consensus"]) {
      lines[key] = chart.addSeries(LineSeries, {
        color: COLORS[key],
        lineWidth: key === "consensus" ? 2 : 1,
        lineStyle: key === "consensus" ? LineStyle.Solid : LineStyle.Dashed,
        lastValueVisible: false,
        priceLineVisible: false,
        priceFormat: format,
      });
      lines[key].setData(toPoints(data.forecast[key]));
    }

    const lastHistory = data.history.at(-1)[0];
    const lastForecast = data.forecast.consensus.at(-1)?.[0] ?? lastHistory;
    const range = el.querySelector(".pc__range");
    const mode = el.querySelector(".pc__fc");

    function apply() {
      const shown = mode.value;
      for (const [key, series] of Object.entries(lines)) {
        series.applyOptions({ visible: shown === "all" || (shown === "consensus" && key === "consensus") });
      }
      low.applyOptions({ visible: shown !== "none" });
      high.applyOptions({ visible: shown !== "none" });
      const days = RANGES[range.value];
      const end = new Date(lastHistory);
      const from = days ? new Date(end.getTime() - days * 864e5) : new Date(data.history[0][0]);
      // As much forecast as history, at least a month, up to the last forecast date.
      const ahead = shown === "none" ? 0 : Math.max(31, days ?? 3653);
      const to = new Date(Math.min(end.getTime() + ahead * 864e5, new Date(lastForecast).getTime()));
      chart.timeScale().setVisibleRange({ from: day(from), to: day(to) });
    }
    range.addEventListener("change", apply);
    mode.addEventListener("change", apply);
    apply();
  }

  const io = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting) {
          io.unobserve(entry.target);
          init(entry.target);
        }
      }
    },
    { rootMargin: "200px" },
  );
  document.querySelectorAll(".pc").forEach((el) => io.observe(el));
})();
