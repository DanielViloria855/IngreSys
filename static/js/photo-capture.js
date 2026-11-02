/* Vista previa de la foto tomada con la cámara (molécula photo_capture). */
(function () {
  document.querySelectorAll("[data-photo]").forEach(function (box) {
    var input = box.querySelector("input[type=file]");
    var preview = box.querySelector(".photo-preview");
    var empty = box.querySelector(".photo-empty");
    var name = box.querySelector(".photo-name");
    var currentUrl = null;

    input.addEventListener("change", function () {
      var file = input.files && input.files[0];
      if (currentUrl) { URL.revokeObjectURL(currentUrl); currentUrl = null; }
      if (!file) {
        preview.hidden = true; empty.hidden = false; name.textContent = "";
        box.classList.remove("has-file");
        return;
      }
      currentUrl = URL.createObjectURL(file);
      preview.src = currentUrl;
      preview.hidden = false;
      empty.hidden = true;
      name.textContent = file.name + " · " + (file.size / 1024 / 1024).toFixed(1) + " MB";
      box.classList.add("has-file");
    });
  });
})();
