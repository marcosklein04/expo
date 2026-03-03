(function () {
  const body = document.body;
  const autoPrint = body?.dataset?.autoPrint === "1";
  const autoClose = body?.dataset?.autoClose === "1";
  const ticketNumero = body?.dataset?.ticketNumero || "";
  const isPopup = Boolean(window.opener);

  function emitPrintedSignal() {
    if (!window.opener) {
      return;
    }

    try {
      window.opener.postMessage(
        {
          type: "ticket-printed",
          ticket_numero: ticketNumero,
        },
        window.location.origin
      );
    } catch (error) {
      // The opener may no longer be available.
    }
  }

  window.addEventListener("afterprint", () => {
    emitPrintedSignal();
    if (autoClose && isPopup) {
      window.setTimeout(() => window.close(), 180);
    }
  });

  window.addEventListener("load", () => {
    if (!autoPrint) {
      return;
    }
    window.setTimeout(() => {
      window.focus();
      window.print();
    }, 120);
  });
})();
