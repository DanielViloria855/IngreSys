/* OCR con IA: envía la foto al servidor, rellena el campo y muestra el estado.
   Las comprobaciones locales (placa e ISO 6346) replican las reglas del dominio
   para dar feedback inmediato mientras el usuario corrige a mano. */
(function () {
  var LETTER = { A: 10, B: 12, C: 13, D: 14, E: 15, F: 16, G: 17, H: 18, I: 19, J: 20, K: 21, L: 23, M: 24,
                 N: 25, O: 26, P: 27, Q: 28, R: 29, S: 30, T: 31, U: 32, V: 34, W: 35, X: 36, Y: 37, Z: 38 };

  function normalize(v) { return (v || "").toUpperCase().replace(/[\s\-.]/g, ""); }

  function checkDigit(code10) {
    var total = 0;
    for (var i = 0; i < 10; i++) {
      var c = code10.charAt(i);
      total += (/[A-Z]/.test(c) ? LETTER[c] : parseInt(c, 10)) * Math.pow(2, i);
    }
    return (total % 11) % 10;
  }

  function evaluate(kind, value) {
    var v = normalize(value);
    if (!v) return { state: "idle", text: "Sin verificar" };
    if (kind === "plate") {
      return /^[A-Z]{3}\d{3}$/.test(v) || /^[RS]\d{5}$/.test(v)
        ? { state: "valid", text: "Placa válida" }
        : { state: "verify", text: "Formato no reconocido. Usa ABC123 (vehículo) o R12345 (remolque)." };
    }
    if (!/^[A-Z]{3}[UJZ]\d{7}$/.test(v)) {
      return { state: "verify", text: "Formato no reconocido. Debe ser 3 letras + U/J/Z + 7 dígitos." };
    }
    var expected = checkDigit(v.slice(0, 10));
    return parseInt(v.charAt(10), 10) === expected
      ? { state: "valid", text: "ISO 6346 válido" }
      : { state: "invalid", text: "ISO inválido: el dígito de control debería ser " + expected, expected: expected };
  }

  var LABELS = { loading: "Procesando", valid: "Válido", verify: "Verificar", invalid: "ISO inválido", error: "Error" };

  function csrf() {
    var m = document.querySelector('meta[name="csrf-token"]');
    return m ? m.content : "";
  }

  document.querySelectorAll("[data-ocr]").forEach(function (root) {
    var kind = root.dataset.ocrKind;
    var url = root.dataset.ocrUrl;
    var file = root.querySelector("input[type=file]");
    var button = root.querySelector("[data-ocr-button]");
    var text = root.querySelector("[data-ocr-text]");
    var status = root.querySelector("[data-ocr-status]");
    var confirmBox = root.querySelector("[data-ocr-confirm]");

    function setStatus(state, message) {
      status.innerHTML = "";
      var badge = document.createElement("span");
      badge.className = "ocr-badge ocr-badge--" + state;
      if (LABELS[state]) {
        var strong = document.createElement("strong");
        strong.textContent = LABELS[state] + ": ";
        badge.appendChild(strong);
      }
      badge.appendChild(document.createTextNode(message));
      status.appendChild(badge);
      if (confirmBox) {
        var needs = state === "invalid";
        confirmBox.hidden = !needs;
        if (!needs) { var cb = confirmBox.querySelector("input"); if (cb) cb.checked = false; }
      }
    }

    function refreshFromText() {
      var result = evaluate(kind, text.value);
      if (result.state === "idle" && !text.value) { status.innerHTML = ""; if (confirmBox) confirmBox.hidden = true; return; }
      setStatus(result.state, result.text);
    }

    file.addEventListener("change", function () {
      button.disabled = !(file.files && file.files.length);
      if (file.files && file.files.length) setStatus("idle", "Foto lista. Pulsa «Leer con IA» o escribe el dato.");
    });

    text.addEventListener("input", refreshFromText);
    text.addEventListener("blur", function () { text.value = normalize(text.value); refreshFromText(); });

    button.addEventListener("click", function () {
      if (!file.files || !file.files.length) return;
      var data = new FormData();
      data.append("image", file.files[0]);
      button.disabled = true;
      setStatus("loading", "Leyendo la foto con IA…");
      fetch(url, { method: "POST", body: data, headers: { "X-CSRFToken": csrf() }, credentials: "same-origin" })
        .then(function (res) { return res.json().then(function (body) { return { ok: res.ok, body: body }; }); })
        .then(function (r) {
          if (!r.ok) { setStatus("error", r.body.error || "No se pudo leer la foto. Escribe el dato a mano."); return; }
          var b = r.body;
          if (!b.candidate) {
            var raw = (b.raw_text || "").slice(0, 60);
            setStatus("verify", "No se reconoció un código en la foto." + (raw ? " Texto leído: «" + raw + "». " : " ") + "Corrígelo a mano.");
            return;
          }
          text.value = b.candidate;
          text.dispatchEvent(new Event("input", { bubbles: true }));
          if (b.status === "valid") setStatus("valid", kind === "plate" ? "Placa leída y válida" : "Contenedor leído · ISO 6346 válido");
          else if (b.status === "invalid") setStatus("invalid", "ISO inválido: el dígito de control debería ser " + b.expected_check_digit + ". Verifica el código en el contenedor.");
          else setStatus("verify", "Verifica el texto leído.");
        })
        .catch(function () { setStatus("error", "Sin conexión con el servidor. Escribe el dato a mano."); })
        .finally(function () { button.disabled = !(file.files && file.files.length); });
    });

    if (text.value) refreshFromText();
  });
})();
