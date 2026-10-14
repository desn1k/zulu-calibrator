// Reads the chosen JSON export in the browser and sends only what the calculator needs.
// Consumer names and addresses (Name, Bld, Adres and any field whose name contains "adres" or
// "address") are removed here, before anything leaves the browser. The server removes them again.
(function () {
  "use strict";

  var PRIVATE = ["Name", "Bld", "Adres"];
  var KEEP_INPUTS = /^(f_|g[A-Z]|tnv$|dTcold$|punit$|objName$)/;

  function isPrivate(key) {
    var k = key.toLowerCase();
    return PRIVATE.indexOf(key) !== -1 || k.indexOf("adres") !== -1 || k.indexOf("address") !== -1;
  }

  function strip(obj) {
    if (!obj || typeof obj !== "object") return obj;
    var out = {};
    Object.keys(obj).forEach(function (k) {
      if (!isPrivate(k)) out[k] = obj[k];
    });
    return out;
  }

  function clean(data) {
    var inputs = {};
    var src = data["все_поля_ввода"] || {};
    Object.keys(src).forEach(function (k) {
      if (KEEP_INPUTS.test(k)) inputs[k] = src[k];
    });
    return {
      "объект": data["объект"],
      "настройки": data["настройки"] || {},
      "все_поля_ввода": inputs,
      "карточка_ЦТП": strip(data["карточка_ЦТП"] || {}),
      "дома": (data["дома"] || []).map(strip),
    };
  }

  function attach(form) {
    var file = form.querySelector("[data-import-file]");
    var payload = form.querySelector("textarea[name=payload]");
    if (!file || !payload) return;
    form.addEventListener("submit", function (event) {
      if (payload.value) return; // already prepared
      event.preventDefault();
      var f = file.files && file.files[0];
      if (!f) return;
      var reader = new FileReader();
      reader.onload = function () {
        var data;
        try {
          data = JSON.parse(String(reader.result));
        } catch (e) {
          alert("Файл не похож на JSON выгрузки калькулятора.");
          return;
        }
        payload.value = JSON.stringify(clean(data));
        file.disabled = true; // the raw file itself is never sent
        form.submit();
      };
      reader.readAsText(f, "utf-8");
    });
  }

  if (typeof module !== "undefined" && module.exports) {
    module.exports = { clean: clean }; // used by tests/web/test_import_js.py
  } else {
    document.addEventListener("DOMContentLoaded", function () {
      document.querySelectorAll("form.import-form").forEach(attach);
    });
  }
})();
