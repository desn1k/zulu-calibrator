// «Копировать»: copies the «ввести» table as Sys / field / value, tab-separated.
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

  document.addEventListener("DOMContentLoaded", function () {
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
