// Prepares imports in the browser and sends only what the calculator needs.
//
// Two forms:
// - Zulu: the CTP card pasted from Zulu (Field<TAB>value lines) and the consumer query export
//   (xlsx or csv, read with SheetJS);
// - the old calculator JSON export.
//
// Consumer names and addresses (Name, Bld, Adres, FIAS_Adress, FIAS_ID, UUTE_Name and any field
// whose name contains "adres", "address" or "fias") are removed here, before anything leaves the
// browser. The CTP card keeps Name (the CTP name). The server removes them again.
(function () {
  "use strict";

  var PRIVATE = ["Name", "Bld", "Adres", "FIAS_Adress", "FIAS_ID", "UUTE_Name"];
  var PRIVATE_PARTS = ["adres", "address", "fias"];
  var KEEP_INPUTS = /^(f_|g[A-Z]|tnv$|dTcold$|punit$|objName$)/;
  var SEPARATOR = /\t| {2,}/;

  function isPrivate(key) {
    var k = String(key).toLowerCase();
    if (PRIVATE.indexOf(key) !== -1) return true;
    return PRIVATE_PARTS.some(function (p) { return k.indexOf(p) !== -1; });
  }

  function isPrivateCard(key) {
    return key !== "Name" && isPrivate(key);
  }

  function strip(obj) {
    if (!obj || typeof obj !== "object") return obj;
    var out = {};
    Object.keys(obj).forEach(function (k) {
      if (!isPrivate(k)) out[k] = obj[k];
    });
    return out;
  }

  // Old calculator JSON export.
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

  // CTP card text: drops the lines of address fields.
  function cleanCard(text) {
    return String(text || "")
      .split(/\r?\n/)
      .filter(function (line) {
        var key = line.trim().split(SEPARATOR)[0].trim();
        return !isPrivateCard(key);
      })
      .join("\n");
  }

  function pad(n) {
    return (n < 10 ? "0" : "") + n;
  }

  function cellValue(v) {
    if (v instanceof Date) {
      return v.getFullYear() + "-" + pad(v.getMonth() + 1) + "-" + pad(v.getDate());
    }
    return v;
  }

  // Consumer rows ({column: value}): drops private columns, dates become YYYY-MM-DD.
  function cleanRows(rows) {
    return (rows || []).map(function (row) {
      var out = {};
      Object.keys(row).forEach(function (k) {
        if (!isPrivate(k)) out[k] = cellValue(row[k]);
      });
      return out;
    });
  }

  // First sheet of an xlsx (bytes) or a csv (text) as rows keyed by the header row.
  function parseRows(data, csv) {
    var wb = csv
      ? XLSX.read(String(data), { type: "string", raw: true })
      : XLSX.read(data, { type: "array", cellDates: true });
    var ws = wb.Sheets[wb.SheetNames[0]];
    return XLSX.utils.sheet_to_json(ws, { defval: null, raw: true });
  }

  function readRows(file, done) {
    var csv = /\.csv$/i.test(file.name);
    var reader = new FileReader();
    reader.onload = function () {
      var rows;
      try {
        rows = parseRows(csv ? reader.result : new Uint8Array(reader.result), csv);
      } catch (e) {
        alert("Выгрузка потребителей не прочитана (нужен xlsx или csv с заголовками).");
        return;
      }
      done(rows);
    };
    if (csv) reader.readAsText(file, "utf-8");
    else reader.readAsArrayBuffer(file);
  }

  function attachLegacy(form) {
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

  function attachZulu(form) {
    var card = form.querySelector("[data-card]");
    var file = form.querySelector("[data-consumers-file]");
    var payload = form.querySelector("textarea[name=payload]");
    if (!card || !file || !payload) return;
    form.addEventListener("submit", function (event) {
      if (payload.value) return; // already prepared
      event.preventDefault();
      var f = file.files && file.files[0];
      if (!f) return;
      readRows(f, function (rows) {
        payload.value = JSON.stringify({
          format: "zulu",
          card: cleanCard(card.value),
          consumers: cleanRows(rows),
        });
        // Neither the raw card nor the raw file is sent (they have no name; disabled for safety).
        card.disabled = true;
        file.disabled = true;
        form.submit();
      });
    });
  }

  if (typeof module !== "undefined" && module.exports) {
    // used by tests/web/test_import_js.py
    module.exports = { clean: clean, cleanCard: cleanCard, cleanRows: cleanRows, parseRows: parseRows };
  } else {
    document.addEventListener("DOMContentLoaded", function () {
      document.querySelectorAll("form.import-form").forEach(attachLegacy);
      document.querySelectorAll("form.zulu-import-form").forEach(attachZulu);
    });
  }
})();
