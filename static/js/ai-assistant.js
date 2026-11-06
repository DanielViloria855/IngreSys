/* Asistente del tablero: envía la pregunta + los últimos turnos a /analytics/ask/ y pinta la conversación.
   La memoria vive en el navegador (el servidor no guarda conversaciones). */
(function () {
  var panel = document.querySelector("[data-assistant]");
  if (!panel) return;

  var MAX_TURNS = 6;
  var log = panel.querySelector("[data-assistant-log]");
  var empty = panel.querySelector("[data-assistant-empty]");
  var form = panel.querySelector("[data-assistant-form]");
  var input = form.querySelector("input");
  var submit = form.querySelector("button[type=submit]");
  var reset = panel.querySelector("[data-assistant-reset]");
  var meta = panel.querySelector("[data-assistant-meta]");
  var history = [];

  function csrf() {
    var m = document.querySelector('meta[name="csrf-token"]');
    return m ? m.content : "";
  }

  function range() {
    var out = {};
    new URLSearchParams(panel.dataset.query).forEach(function (value, key) { out[key] = value; });
    return out;
  }

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function addRow(kind, who, text) {
    if (empty) empty.hidden = true;
    var row = el("div", "chat-row chat-row--" + kind);
    row.appendChild(el("span", "chat-who", who));
    row.appendChild(el("p", "chat-text", text));
    log.appendChild(row);
    log.scrollTop = log.scrollHeight;
    return row;
  }

  function remember(role, text) {
    history.push({ role: role, text: text });
    if (history.length > MAX_TURNS) history = history.slice(-MAX_TURNS);
    reset.hidden = false;
  }

  function origin(result) {
    var when = new Date(result.generated_at);
    var time = isNaN(when) ? "" : when.toLocaleTimeString("es-CO", { hour: "2-digit", minute: "2-digit" });
    var base = result.fallback_used
      ? "Respuesta de " + result.model_used.toLowerCase() + " (la IA no estuvo disponible)"
      : (/^reglas/i.test(result.model_used) ? "Respuesta de " + result.model_used.toLowerCase() : "Respuesta generada por IA · modelo " + result.model_used);
    return (base + (time ? " · " + time : "")).replace(/\.?$/, ".");
  }

  function ask(question) {
    question = question.trim();
    if (!question) return;
    addRow("user", "Usted", question);
    var pending = addRow("assistant", "Asistente", "Consultando…");
    pending.classList.add("is-pending");
    input.value = "";
    input.disabled = submit.disabled = true;
    log.setAttribute("aria-busy", "true");

    var payload = Object.assign({ question: question, history: history }, range());
    fetch(panel.dataset.url, {
      method: "POST",
      credentials: "same-origin",
      headers: { "X-CSRFToken": csrf(), "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
      .then(function (res) { return res.json().then(function (body) { return { ok: res.ok, body: body }; }); })
      .then(function (r) {
        pending.classList.remove("is-pending");
        var text = pending.querySelector(".chat-text");
        if (!r.ok) {
          pending.classList.add("is-error");
          text.textContent = r.body.error || "No se pudo responder. Intente de nuevo.";
          return;
        }
        text.textContent = r.body.answer;
        meta.textContent = origin(r.body);
        remember("user", question);
        remember("assistant", r.body.answer);
      })
      .catch(function () {
        pending.classList.remove("is-pending");
        pending.classList.add("is-error");
        pending.querySelector(".chat-text").textContent = "Sin conexión con el servidor. Intente de nuevo.";
      })
      .finally(function () {
        input.disabled = submit.disabled = false;
        log.setAttribute("aria-busy", "false");
        input.focus();
        log.scrollTop = log.scrollHeight;
      });
  }

  form.addEventListener("submit", function (e) { e.preventDefault(); ask(input.value); });

  panel.querySelectorAll("[data-assistant-suggestion]").forEach(function (btn) {
    btn.addEventListener("click", function () { ask(btn.textContent); });
  });

  reset.addEventListener("click", function () {
    history = [];
    log.querySelectorAll(".chat-row").forEach(function (row) { row.remove(); });
    if (empty) empty.hidden = false;
    reset.hidden = true;
    input.focus();
  });
})();
