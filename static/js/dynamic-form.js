/* Formulario dinámico: ramificación, validación en el navegador y progreso.
   La regla de visibilidad replica VisibilityRule (apps/questionnaire/domain/visibility.py);
   el servidor sigue siendo la autoridad. */
(function () {
  var form = document.querySelector("[data-dynamic-form]");
  if (!form) return;

  var items = Array.prototype.slice.call(form.querySelectorAll(".q-item"));
  var byId = {};
  items.forEach(function (el) { byId[el.dataset.qId] = el; });
  var progressText = form.querySelector("[data-progress-text]");

  function norm(v) { return String(v).trim().toLowerCase(); }

  // Valor "crudo" de una pregunta, igual que el que usa el servidor para decidir visibilidad.
  function rawValue(item) {
    var type = item.dataset.qType;
    if (type === "boolean" || type === "single_choice") {
      var checked = item.querySelector("input[type=radio]:checked");
      if (checked) return checked.value;
      var select = item.querySelector("select");
      return select ? select.value : null;
    }
    if (type === "multi_choice") {
      return Array.prototype.map.call(item.querySelectorAll("input[type=checkbox]:checked"), function (i) { return i.value; });
    }
    if (type === "photo") return null;
    var field = item.querySelector("input[type=text],input[type=number],input[type=date]");
    return field ? field.value.trim() : null;
  }

  function matches(raw, expected) {
    if (raw === null || raw === "" || (Array.isArray(raw) && !raw.length)) return false;
    if (Array.isArray(raw)) return raw.some(function (x) { return norm(x) === norm(expected); });
    return norm(raw) === norm(expected);
  }

  function isEmpty(item) {
    var type = item.dataset.qType;
    if (type === "photo") {
      var file = item.querySelector("input[type=file]");
      return !(file && file.files && file.files.length);
    }
    var raw = rawValue(item);
    return raw === null || raw === "" || (Array.isArray(raw) && raw.length === 0);
  }

  function clearError(item) {
    item.classList.remove("has-error");
    var msg = item.querySelector(".js-error");
    if (msg) msg.remove();
  }

  function showError(item, text) {
    clearError(item);
    item.classList.add("has-error");
    var div = document.createElement("div");
    div.className = "field-error js-error";
    div.setAttribute("role", "alert");
    div.textContent = text;
    item.querySelector(".q-body").appendChild(div);
  }

  function refresh() {
    var visible = {};
    items.forEach(function (item) { // el orden del DOM es el orden de las preguntas
      var dep = item.dataset.dependsOn;
      var show = true;
      if (dep) show = !!byId[dep] && visible[dep] === true && matches(rawValue(byId[dep]), item.dataset.dependsValue);
      item.hidden = !show;
      // Los campos de preguntas ocultas no se envían ni se validan.
      item.querySelectorAll("input,select,textarea").forEach(function (el) { el.disabled = !show; });
      if (show) visible[item.dataset.qId] = true;
    });
    updateProgress();
  }

  function updateProgress() {
    if (!progressText) return;
    var missing = items.filter(function (i) { return !i.hidden && i.hasAttribute("data-required") && isEmpty(i); }).length;
    progressText.className = "form-hint" + (missing ? "" : " ready");
    progressText.textContent = missing
      ? "Faltan " + missing + " campo" + (missing === 1 ? "" : "s") + " obligatorio" + (missing === 1 ? "" : "s")
      : "Formulario completo";
  }

  form.addEventListener("change", function (e) {
    var item = e.target.closest(".q-item");
    if (item) clearError(item);
    refresh();
  });
  form.addEventListener("input", function (e) {
    var item = e.target.closest(".q-item");
    if (item) clearError(item);
    updateProgress();
  });

  form.addEventListener("submit", function (e) {
    var first = null;
    items.forEach(function (item) {
      if (item.hidden) return;
      clearError(item);
      if (item.hasAttribute("data-required") && isEmpty(item)) {
        showError(item, item.dataset.qType === "photo" ? "Adjunta una foto." : "Este campo es obligatorio.");
        first = first || item;
      }
    });
    if (first) {
      e.preventDefault();
      first.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "center" });
      var focusable = first.querySelector("input:not([type=file]):not([type=hidden]),select,textarea,label.photo-drop");
      if (focusable) focusable.focus({ preventScroll: true });
      return;
    }
    var btn = form.querySelector("[data-submit]");
    if (btn) {
      btn.disabled = true;
      btn.textContent = "Registrando…";
    }
  });

  refresh();
  var firstError = form.querySelector(".q-item.has-error");
  if (firstError) firstError.scrollIntoView({ block: "center" });
})();
