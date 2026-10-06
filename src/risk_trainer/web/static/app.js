// Risk Trainer form helpers (PRD R6). The server re-checks every rule (R7).
// - Disables further "remediate" choices once the remediation slots are used, and says why.
// - Shows the approver field and requires a rationale when a finding is accepted.
(function () {
  "use strict";

  function plural(n, word) {
    return n + " " + word + (n === 1 ? "" : "s");
  }

  function update(form) {
    var slots = parseInt(form.getAttribute("data-slots"), 10) || 0;
    var remediate = form.querySelectorAll("input[data-remediate]");
    var used = 0;
    remediate.forEach(function (input) {
      if (input.checked) used += 1;
    });
    var full = used >= slots;
    remediate.forEach(function (input) {
      input.disabled = full && !input.checked;
    });

    var status = form.querySelector("#slot-status");
    if (status) {
      status.textContent = full
        ? "All " + plural(slots, "remediation slot") + " are used, so remediate is disabled for the other findings. Change one of your remediate choices to free a slot."
        : "You have used " + used + " of " + plural(slots, "remediation slot") + ".";
    }

    form.querySelectorAll("section.finding").forEach(function (section) {
      var accept = section.querySelector("input[data-accept]");
      var accepted = Boolean(accept && accept.checked);
      var approverBox = section.querySelector("[data-accept-only]");
      var approver = approverBox && approverBox.querySelector("select");
      var rationale = section.querySelector("textarea");
      if (approverBox) approverBox.hidden = !accepted;
      if (approver) approver.required = accepted;
      if (rationale) {
        rationale.required = accepted;
        if (accepted) {
          rationale.setAttribute("minlength", "10");
        } else {
          rationale.removeAttribute("minlength");
        }
      }
    });
  }

  function init(root) {
    var forms = root.querySelectorAll ? root.querySelectorAll("form[data-slots]") : [];
    forms.forEach(function (form) {
      if (form.getAttribute("data-ready") === "1") return;
      form.setAttribute("data-ready", "1");
      form.addEventListener("change", function () {
        update(form);
      });
      update(form);
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    init(document);
  });
  document.addEventListener("htmx:load", function (event) {
    init(event.detail && event.detail.elt ? event.detail.elt : document);
  });
})();
