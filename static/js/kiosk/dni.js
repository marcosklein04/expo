(function () {
  const body = document.body;
  const idleMs = Number(body?.dataset?.idleMs || "0");
  const startUrl = body?.dataset?.startUrl;
  const vouchersUrl = body?.dataset?.vouchersUrl;

  const dniInput = document.getElementById("dni");
  const pad = document.getElementById("pad");
  const clearBtn = document.getElementById("clear");
  const continueBtn = document.getElementById("continue");

  if (!startUrl || !vouchersUrl || !dniInput || !pad || !clearBtn || !continueBtn) {
    return;
  }

  let idleTimer = null;

  function resetIdle() {
    clearTimeout(idleTimer);
    if (idleMs <= 0) {
      return;
    }
    idleTimer = window.setTimeout(() => {
      window.location.href = startUrl;
    }, idleMs);
  }

  function addDigit(digit) {
    if (dniInput.value.length >= 12) {
      return;
    }
    dniInput.value += digit;
  }

  const keys = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "", "0", ""];

  keys.forEach((value) => {
    if (!value) {
      const gap = document.createElement("div");
      gap.className = "number-gap";
      pad.appendChild(gap);
      return;
    }

    const button = document.createElement("button");
    button.type = "button";
    button.className = "number-key";
    button.textContent = value;
    button.addEventListener("click", () => {
      addDigit(value);
      resetIdle();
    });
    pad.appendChild(button);
  });

  clearBtn.addEventListener("click", () => {
    dniInput.value = "";
    resetIdle();
  });

  continueBtn.addEventListener("click", () => {
    const dni = dniInput.value.trim();
    if (!dni) {
      return;
    }
    window.location.href = `${vouchersUrl}?dni=${encodeURIComponent(dni)}`;
  });

  document.addEventListener("click", resetIdle, { passive: true });
  document.addEventListener("touchstart", resetIdle, { passive: true });
  document.addEventListener("keydown", resetIdle);

  resetIdle();
})();
