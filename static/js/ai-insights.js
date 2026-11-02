/* Panel «Analizar con IA»: POST /analytics/insights/ y pinta las tarjetas por nivel. */
(function () {
  var panel = document.querySelector("[data-insights]");
  if (!panel) return;

  var button = panel.querySelector("[data-insights-button]");
  var list = panel.querySelector("[data-insights-list]");
  var meta = panel.querySelector("[data-insights-meta]");
  var LABEL = { info: "Información", warning: "Atención", alert: "Alerta" };

  function csrf() {
    var m = document.querySelector('meta[name="csrf-token"]');
    return m ? m.content : "";
  }

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function loading() {
    list.innerHTML = "";
    list.setAttribute("aria-busy", "true");
    for (var i = 0; i < 3; i++) list.appendChild(el("div", "skeleton"));
  }

  function message(icon, title, text) {
    list.innerHTML = "";
    var box = el("div", "insights-empty");
    box.appendChild(el("strong", "", title)); box.appendChild(document.createTextNode(text));
    list.appendChild(box);
  }

  function render(result) {
    list.innerHTML = "";
    result.insights.forEach(function (item) {
      var level = LABEL[item.level] ? item.level : "info";
      var row = el("div", "insight insight--" + level);
      row.appendChild(el("span", "insight-level", LABEL[level]));
      row.appendChild(el("h3", "", item.title));
      row.appendChild(el("p", "", item.message));
      list.appendChild(row);
    });
    var when = new Date(result.generated_at);
    var time = isNaN(when) ? "" : when.toLocaleTimeString("es-CO", { hour: "2-digit", minute: "2-digit" });
    var origin = result.fallback_used
      ? "Generado por " + result.model_used + " (la IA no estuvo disponible)"
      : (/^reglas/i.test(result.model_used) ? "Generado por " + result.model_used.toLowerCase() : "Generado por IA · modelo " + result.model_used);
    meta.textContent = origin + (time ? " · " + time : "") + (result.from_cache ? " · sin cambios desde el último análisis" : "") + ".";
  }

  button.addEventListener("click", function () {
    button.disabled = true;
    loading();
    fetch(panel.dataset.url, {
      method: "POST",
      credentials: "same-origin",
      headers: { "X-CSRFToken": csrf(), "Content-Type": "application/x-www-form-urlencoded" },
      body: panel.dataset.query,
    })
      .then(function (res) { return res.json().then(function (body) { return { ok: res.ok, body: body }; }); })
      .then(function (r) {
        if (!r.ok) { message("", "No se pudo analizar", r.body.error || "Intenta de nuevo."); return; }
        render(r.body);
      })
      .catch(function () { message("", "Sin conexión", "No se pudo contactar el servidor. Intenta de nuevo."); })
      .finally(function () { list.setAttribute("aria-busy", "false"); button.disabled = false; });
  });
})();
