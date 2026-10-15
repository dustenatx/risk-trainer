// Risk Trainer theme switch. Loaded in <head> without defer, so data-theme is set before the
// first paint. "auto" (the default) leaves data-theme off and the CSS follows the device.
// Storage can be blocked, so every read and write is wrapped and the page works without it.
(function () {
  "use strict";

  var KEY = "rt-theme";
  var CHOICES = ["auto", "light", "dark"];
  var root = document.documentElement;

  function read() {
    try {
      var value = window.localStorage.getItem(KEY);
      return CHOICES.indexOf(value) === -1 ? "auto" : value;
    } catch (error) {
      return "auto";
    }
  }

  function write(value) {
    try {
      window.localStorage.setItem(KEY, value);
    } catch (error) {
      // Blocked storage: the choice lasts until the page is reloaded.
    }
  }

  var choice = read();

  function apply() {
    if (choice === "auto") {
      root.removeAttribute("data-theme");
    } else {
      root.setAttribute("data-theme", choice);
    }
  }

  function sync(group) {
    group.querySelectorAll("button[data-theme-choice]").forEach(function (button) {
      button.setAttribute("aria-pressed", String(button.getAttribute("data-theme-choice") === choice));
    });
  }

  function init(scope) {
    var groups = scope.querySelectorAll ? scope.querySelectorAll(".theme-switch") : [];
    groups.forEach(function (group) {
      sync(group);
      group.hidden = false;
      if (group.getAttribute("data-ready") === "1") return;
      group.setAttribute("data-ready", "1");
      group.addEventListener("click", function (event) {
        var button = event.target.closest("button[data-theme-choice]");
        if (!button) return;
        choice = button.getAttribute("data-theme-choice");
        apply();
        write(choice);
        sync(group);
      });
    });
  }

  apply();
  document.addEventListener("DOMContentLoaded", function () {
    init(document);
  });
  document.addEventListener("htmx:load", function (event) {
    init(event.detail && event.detail.elt ? event.detail.elt : document);
  });
})();
