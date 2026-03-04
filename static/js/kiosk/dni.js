(function () {
  const body = document.body;
  const idleMs = Number(body?.dataset?.idleMs || "0");
  const startUrl = body?.dataset?.startUrl;
  const vouchersUrl = body?.dataset?.vouchersUrl;

  const screen = document.querySelector(".kiosk-shell");
  const input = document.getElementById("document-input");
  const hint = document.getElementById("document-hint");
  const continueBtn = document.getElementById("continue");
  const typeButtons = Array.from(document.querySelectorAll("[data-doc-type]"));

  if (
    !startUrl ||
    !vouchersUrl ||
    !screen ||
    !input ||
    !hint ||
    !continueBtn ||
    typeButtons.length === 0
  ) {
    return;
  }

  let idleTimer = null;
  let currentType = "DNI";

  function resetIdle() {
    clearTimeout(idleTimer);
    if (idleMs <= 0) {
      return;
    }
    idleTimer = window.setTimeout(() => {
      window.location.href = startUrl;
    }, idleMs);
  }

  function normalizeValue(value, docType) {
    const source = String(value || "").trim();
    if (!source) {
      return "";
    }

    if (docType === "PASAPORTE") {
      return source.toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 12);
    }

    return source.replace(/\D/g, "").slice(0, 12);
  }

  function focusInput(delayMs = 0) {
    const run = () => input.focus({ preventScroll: true });
    if (delayMs > 0) {
      window.setTimeout(run, delayMs);
      return;
    }
    run();
  }

  function updateConfirmState() {
    continueBtn.disabled = normalizeValue(input.value, currentType).length === 0;
  }

  function setDniKeyboardMode() {
    input.type = "text";
    input.setAttribute("inputmode", "numeric");
    input.setAttribute("pattern", "[0-9]*");
    input.setAttribute("autocapitalize", "off");
    input.setAttribute("placeholder", "Ingresá tu DNI");
    hint.textContent = "Ingresá tu DNI sin puntos.";
  }

  function setPassportKeyboardMode() {
    input.type = "text";
    input.setAttribute("inputmode", "text");
    input.removeAttribute("pattern");
    input.setAttribute("autocapitalize", "characters");
    input.setAttribute("placeholder", "Ingresá tu pasaporte");
    hint.textContent = "Ingresá letras y números de tu pasaporte.";
  }

  function applyType(docType) {
    currentType = docType === "PASAPORTE" ? "PASAPORTE" : "DNI";

    typeButtons.forEach((button) => {
      button.classList.toggle("is-active", button.dataset.docType === currentType);
    });

    const hadFocus = document.activeElement === input;
    if (hadFocus) {
      input.blur();
    }

    if (currentType === "PASAPORTE") {
      setPassportKeyboardMode();
    } else {
      setDniKeyboardMode();
    }

    input.value = normalizeValue(input.value, currentType);
    updateConfirmState();

    // In Android kiosks, blur/focus helps force keyboard layout switch.
    if (hadFocus) {
      focusInput(40);
    }
  }

  function goToVouchers() {
    const documentValue = normalizeValue(input.value, currentType);
    if (!documentValue) {
      focusInput();
      return;
    }

    const params = new URLSearchParams({
      doc: documentValue,
      doc_type: currentType,
    });

    window.location.href = `${vouchersUrl}?${params.toString()}`;
  }

  typeButtons.forEach((button) => {
    button.addEventListener("click", () => {
      applyType(button.dataset.docType);
      focusInput(40);
      resetIdle();
    });
  });

  input.addEventListener("input", () => {
    const normalized = normalizeValue(input.value, currentType);
    if (normalized !== input.value) {
      input.value = normalized;
    }
    updateConfirmState();
  });

  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      goToVouchers();
    }
  });

  continueBtn.addEventListener("click", goToVouchers);

  screen.addEventListener(
    "touchstart",
    (event) => {
      if (event.target instanceof HTMLElement && event.target.closest("button")) {
        return;
      }
      focusInput(20);
    },
    { passive: true }
  );

  document.addEventListener("click", resetIdle, { passive: true });
  document.addEventListener("touchstart", resetIdle, { passive: true });
  document.addEventListener("keydown", resetIdle);

  applyType("DNI");
  resetIdle();
  focusInput(140);
})();
