/* Tablero: gráficos con Chart.js a partir de /analytics/metrics/ (colores desde los tokens CSS). */
(function () {
  var root = document.getElementById("dashboard");
  if (!root || typeof Chart === "undefined") return;

  var charts = {};
  var lastData = null;
  var reduceMotion = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;

  function css(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }

  function palette() {
    return {
      primary: css("--c-primary"), ink2: css("--c-ink-2"), line: css("--c-line"), surface: css("--c-surface"),
      warning: css("--c-warning"), success: css("--c-success"), soft: "#8fb0cf",
    };
  }

  function applyDefaults() {
    var p = palette();
    Chart.defaults.font.family = css("--font-body") || "sans-serif";
    Chart.defaults.font.size = 13;
    Chart.defaults.color = p.ink2;
    Chart.defaults.borderColor = p.line;
    Chart.defaults.animation = reduceMotion ? false : { duration: 350 };
    Chart.defaults.plugins.legend.labels.usePointStyle = true;
  }

  function labels(points) { return points.map(function (p) { return p.label; }); }
  function values(points) { return points.map(function (p) { return p.value; }); }
  function total(points) { return values(points).reduce(function (a, b) { return a + b; }, 0); }

  function toggleEmpty(id, empty) {
    var el = document.querySelector('[data-chart-empty="' + id + '"]');
    if (el) el.hidden = !empty;
  }
  function summary(id, text) {
    var el = document.querySelector('[data-chart-summary="' + id + '"]');
    if (el && text) el.textContent = text;
  }

  function make(id, config, points) {
    if (charts[id]) charts[id].destroy();
    var empty = total(points) === 0;
    toggleEmpty(id, empty);
    if (empty) { charts[id] = null; return; }
    charts[id] = new Chart(document.getElementById(id), config);
  }

  var gridY = { beginAtZero: true, ticks: { precision: 0 }, grid: { color: function () { return css("--c-line"); } } };
  var noGrid = { grid: { display: false } };

  function draw(d) {
    lastData = d;
    applyDefaults();
    var p = palette();

    // Por hora: la barra más alta se resalta en naranja y se dice en texto.
    var peak = d.by_hour.reduce(function (a, b) { return b.value > a.value ? b : a; }, { label: "", value: 0 });
    summary("chart-hour", peak.value ? "Hora pico: " + peak.label + " · " + peak.value + " ingreso" + (peak.value === 1 ? "" : "s") : null);
    make("chart-hour", {
      type: "bar",
      data: { labels: labels(d.by_hour), datasets: [{ label: "Ingresos", data: values(d.by_hour), borderRadius: 2,
        backgroundColor: d.by_hour.map(function (x) { return x.value && x.value === peak.value ? p.primary : p.soft; }) }] },
      options: { maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { y: gridY, x: noGrid } },
    }, d.by_hour);

    make("chart-day", {
      type: "line",
      data: { labels: labels(d.by_day), datasets: [{ label: "Ingresos", data: values(d.by_day), borderColor: p.primary, backgroundColor: p.primary + "22",
        fill: true, tension: 0.3, pointRadius: d.by_day.length > 20 ? 0 : 3, pointBackgroundColor: p.primary }] },
      options: { maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { y: gridY, x: noGrid } },
    }, d.by_day);

    make("chart-novelty", {
      type: "bar",
      data: { labels: labels(d.novelty_by_type), datasets: [{ label: "Reportes", data: values(d.novelty_by_type), backgroundColor: p.warning, borderRadius: 2 }] },
      options: { indexAxis: "y", maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: gridY, y: noGrid } },
    }, d.novelty_by_type);

    make("chart-suppliers", {
      type: "bar",
      data: { labels: labels(d.top_suppliers), datasets: [{ label: "Ingresos", data: values(d.top_suppliers), backgroundColor: p.primary, borderRadius: 2 }] },
      options: { indexAxis: "y", maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: gridY, y: noGrid } },
    }, d.top_suppliers);

    var statusColors = [p.primary, p.warning, p.success];
    make("chart-status", {
      type: "doughnut",
      data: { labels: d.status_breakdown.map(function (s) { return s.label + " (" + s.value + ")"; }), datasets: [{ data: values(d.status_breakdown),
        backgroundColor: statusColors, borderColor: p.surface, borderWidth: 3 }] },
      options: { maintainAspectRatio: false, cutout: "62%", plugins: { legend: { position: "bottom" } } },
    }, d.status_breakdown);
  }

  function load() {
    fetch(root.dataset.metricsUrl, { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(draw)
      .catch(function () {
        document.querySelectorAll("[data-chart-empty]").forEach(function (el) { el.hidden = false; el.textContent = "No se pudieron cargar los datos."; });
      });
  }

  load();
})();
