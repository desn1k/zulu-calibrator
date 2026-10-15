// «Копировать»: copies the «ввести» table as Sys / field / value, tab-separated.
// «Скопировать SQL»: copies the Zulu UPDATE block; the «по одной» toggle switches between the batch
// (with «;») and the one-by-one form (no «;»).
(function () {
  "use strict";

  function copy(text) {
    if (navigator.clipboard && window.isSecureContext) {
      return navigator.clipboard.writeText(text);
    }
    var area = document.createElement("textarea");
    area.value = text;
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    document.execCommand("copy");
    document.body.removeChild(area);
    return Promise.resolve();
  }

  function attachSqlToggle(block) {
    var toggle = block.querySelector("[data-sql-toggle]");
    var batch = block.querySelector("[data-sql-batch]");
    var single = block.querySelector("[data-sql-single]");
    var button = block.querySelector("[data-sql-copy]");
    if (!toggle || !batch || !single || !button) return;
    toggle.addEventListener("change", function () {
      batch.hidden = toggle.checked;
      single.hidden = !toggle.checked;
      button.setAttribute(
        "data-copy-target",
        button.getAttribute(toggle.checked ? "data-single" : "data-batch")
      );
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-sql]").forEach(attachSqlToggle);
    document.querySelectorAll("[data-copy-target]").forEach(function (button) {
      button.addEventListener("click", function () {
        var source = document.getElementById(button.getAttribute("data-copy-target"));
        if (!source) return;
        copy(source.value).then(function () {
          var label = button.textContent;
          button.textContent = "Скопировано";
          setTimeout(function () { button.textContent = label; }, 1500);
        });
      });
    });
  });
})();
