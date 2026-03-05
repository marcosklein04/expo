(function () {
  const screen = document.getElementById("screen");
  if (!screen) {
    return;
  }

  const idleMs = Number(screen.dataset.idleMs || "0");
  const startUrl = screen.dataset.startUrl || "/";
  const dniUrl = screen.dataset.dniUrl || "/";
  const redeemUrl = screen.dataset.redeemUrl || "";
  const totemId = screen.dataset.totemId || "";
  const empresaCodigo = screen.dataset.empresaCodigo || "";
  const PRINTING_WAIT_MESSAGE = "Por favor, aguarde que se impriman todos sus vouchers";
  const PRINTING_MIN_VISIBLE_MS = 20000;
  const UNLIMITED_GUEST_SOFT_MAX = 999;

  const isAndroidDevice = /Android/i.test(navigator.userAgent || "");
  const forceBrowserMode = new URLSearchParams(window.location.search).get("print_mode") === "browser";
  const preferRawBt = isAndroidDevice && !forceBrowserMode && Boolean(window.RawBtPrinter?.printText);

  const personaPrintData = {
    nombre: screen.dataset.personaNombre || "",
    dni: screen.dataset.personaDni || "",
    credencial: screen.dataset.personaCredencial || "-",
    concesionario: screen.dataset.personaConcesionario || "-",
    tipoVianda: screen.dataset.personaTipoVianda || "-",
  };

  const notice = document.getElementById("notice");
  const selectedCount = document.getElementById("selected-count");
  const flowPrinting = document.getElementById("flow-printing");
  const flowPrintingText = document.getElementById("flow-printing-text");
  const reprintLastBtn = document.getElementById("reprint-last");
  const finalizeBtn = document.getElementById("finalize-selection");
  const clearBtn = document.getElementById("clear-selection");

  const mealCards = Array.from(document.querySelectorAll("[data-meal-card]"));
  const ownByMeal = new Map();
  const invitedByMeal = new Map();

  let idleTimer = null;
  let processing = false;
  let lastPrintedTicket = null;

  function goDni() {
    window.location.href = dniUrl;
  }

  document.querySelectorAll("[data-go-dni]").forEach((button) => {
    button.addEventListener("click", goDni);
  });

  function resetIdle() {
    clearTimeout(idleTimer);
    if (idleMs <= 0) {
      return;
    }
    idleTimer = window.setTimeout(() => {
      window.location.href = startUrl;
    }, idleMs);
  }

  document.addEventListener("click", resetIdle, { passive: true });
  document.addEventListener("touchstart", resetIdle, { passive: true });
  document.addEventListener("keydown", resetIdle);

  function setNotice(message) {
    if (notice) {
      notice.textContent = message;
    }
  }

  function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) {
      return parts.pop().split(";").shift();
    }
    return "";
  }

  function toNumber(value) {
    return Number(value || "0");
  }

  function cardCode(card) {
    return card.dataset.comida;
  }

  function fixedUsed(card) {
    return toNumber(card.dataset.fixedUsed);
  }

  function fixedAvailable(card) {
    return Math.max(toNumber(card.dataset.fixedAvailable), 0);
  }

  function fixedStockAvailable(card) {
    return Math.max(toNumber(card.dataset.fixedStockAvailable), 0);
  }

  function canRedeemOwn(card) {
    return fixedAvailable(card) > 0 && fixedStockAvailable(card) > 0;
  }

  function guestUsed(card) {
    return toNumber(card.dataset.guestUsed);
  }

  function guestUnlimited(card) {
    return card.dataset.guestUnlimited === "1";
  }

  function guestQuota(card) {
    return toNumber(card.dataset.guestQuota);
  }

  function guestAvailable(card) {
    return Math.max(toNumber(card.dataset.guestAvailable), 0);
  }

  function guestStockAvailable(card) {
    return Math.max(toNumber(card.dataset.guestStockAvailable), 0);
  }

  function guestMax(card) {
    if (guestUnlimited(card)) {
      return UNLIMITED_GUEST_SOFT_MAX;
    }
    return Math.max(Math.min(guestAvailable(card), guestStockAvailable(card)), 0);
  }

  function ownSelected(card) {
    return ownByMeal.get(cardCode(card)) || false;
  }

  function invitedSelected(card) {
    return invitedByMeal.get(cardCode(card)) || 0;
  }

  function setOwnSelected(card, selected) {
    const next = Boolean(selected) && canRedeemOwn(card);
    ownByMeal.set(cardCode(card), next);
    updateCardUI(card);
    updateSelectionInfo();
  }

  function setInvitedSelected(card, nextValue) {
    const capped = Math.max(0, Math.min(nextValue, guestMax(card)));
    invitedByMeal.set(cardCode(card), capped);
    const valueLabel = card.querySelector("[data-role='guest-value']");
    if (valueLabel) {
      valueLabel.textContent = String(capped);
    }
    updateCardUI(card);
    updateSelectionInfo();
  }

  function updateCardUI(card) {
    const ownToggle = card.querySelector("[data-role='own-toggle']");
    const ownHint = card.querySelector("[data-role='own-hint']");
    const mealStatus = card.querySelector("[data-role='meal-status']");
    const minusBtn = card.querySelector("[data-role='guest-minus']");
    const plusBtn = card.querySelector("[data-role='guest-plus']");
    const guestLimit = card.querySelector("[data-role='guest-limit']");
    const guestHint = card.querySelector("[data-role='guest-hint']");

    const ownAvailable = canRedeemOwn(card);
    const ownIsSelected = ownSelected(card);
    const invited = invitedSelected(card);
    const invitedMax = guestMax(card);

    card.classList.toggle("selected", ownIsSelected || invited > 0);

    if (mealStatus) {
      if (fixedAvailable(card) <= 0) {
        mealStatus.textContent = "Voucher propio no disponible";
      } else if (fixedStockAvailable(card) <= 0) {
        mealStatus.textContent = "Sin stock propio";
      } else {
        mealStatus.textContent = "Voucher propio disponible";
      }
    }

    if (ownHint) {
      if (fixedAvailable(card) <= 0) {
        ownHint.textContent = "Voucher propio: ya utilizado";
      } else if (fixedStockAvailable(card) <= 0) {
        ownHint.textContent = "Voucher propio: sin stock";
      } else {
        ownHint.textContent = "Voucher propio: disponible";
      }
    }

    if (ownToggle) {
      ownToggle.classList.remove("is-selected", "is-blocked");
      ownToggle.disabled = processing || !ownAvailable;

      if (ownAvailable) {
        if (ownIsSelected) {
          ownToggle.textContent = "SELECCIONADO";
          ownToggle.classList.add("is-selected");
        } else {
          ownToggle.textContent = "CANJEAR MI VOUCHER";
        }
      } else {
        ownToggle.classList.add("is-blocked");
        ownToggle.textContent = fixedAvailable(card) <= 0 ? "YA UTILIZADO" : "SIN STOCK";
      }
    }

    if (guestLimit) {
      guestLimit.textContent = guestUnlimited(card)
        ? "Ilimitado"
        : `${guestUsed(card)}/${guestQuota(card)}`;
    }

    if (guestHint) {
      guestHint.textContent = `Pool invitados: ${guestStockAvailable(card)} disponible(s)`;
    }

    if (minusBtn) {
      minusBtn.disabled = processing || invited <= 0;
    }

    if (plusBtn) {
      plusBtn.disabled = processing || invited >= invitedMax;
    }
  }

  function totals() {
    let propios = 0;
    let invitados = 0;

    mealCards.forEach((card) => {
      if (ownSelected(card)) {
        propios += 1;
      }
      invitados += invitedSelected(card);
    });

    return {
      propios,
      invitados,
      tickets: propios + invitados,
    };
  }

  function buildBatchItems() {
    const items = [];
    mealCards.forEach((card) => {
      const canjearPropio = ownSelected(card);
      const invitados = invitedSelected(card);
      if (!canjearPropio && invitados === 0) {
        return;
      }

      items.push({
        comida: cardCode(card),
        canjear_propio: canjearPropio,
        invitados,
      });
    });
    return items;
  }

  function updateSelectionInfo() {
    const total = totals();
    if (selectedCount) {
      selectedCount.textContent = `${total.propios} propio(s) · ${total.invitados} invitado(s) · ${total.tickets} ticket(s)`;
    }
    if (finalizeBtn) {
      finalizeBtn.disabled = processing || total.tickets === 0;
    }
    if (clearBtn) {
      clearBtn.disabled = processing || total.tickets === 0;
    }
  }

  function clearSelection() {
    mealCards.forEach((card) => {
      setOwnSelected(card, false);
      setInvitedSelected(card, 0);
    });
    setNotice("");
    updateSelectionInfo();
  }

  function wrapText(text, maxCharsPerLine) {
    const source = String(text || "");
    const words = source.split(" ");
    let line = "";
    let wrapped = "";

    for (const word of words) {
      if ((line + word).length > maxCharsPerLine) {
        wrapped += `${line.trim()}\n`;
        line = "";
      }
      line += `${word} `;
    }

    if (line.length > 0) {
      wrapped += line.trim();
    }

    return wrapped;
  }

  function formatDate(rawDate, withTime) {
    if (!rawDate) {
      return "-";
    }
    const parsed = new Date(rawDate);
    if (Number.isNaN(parsed.getTime())) {
      return String(rawDate);
    }
    if (withTime) {
      return parsed.toLocaleString("es-AR", {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hour12: false,
      });
    }
    return parsed.toLocaleDateString("es-AR", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    });
  }

  function buildRawBtTicketPayload(ticket) {
    const ESC = String.fromCharCode(27);
    const GS = String.fromCharCode(29);
    const LF = "\n";

    const ALIGN_LEFT = ESC + "a" + String.fromCharCode(0);
    const ALIGN_CENTER = ESC + "a" + String.fromCharCode(1);
    const BOLD_ON = ESC + "E" + "1";
    const BOLD_OFF = ESC + "E" + "0";
    const NORMAL = ESC + "!" + String.fromCharCode(0);
    const CUT = GS + "V" + String.fromCharCode(66) + String.fromCharCode(0);
    const SEP = "--------------------------------";
    const voucherCode = String(ticket.voucher || "").toUpperCase();
    const isGuestVoucher = voucherCode.includes("INVITADO");
    const mealType = String(ticket.tipo_vianda || personaPrintData.tipoVianda || "-");

    let text = ALIGN_CENTER + NORMAL;
    text += BOLD_ON + "EXPOAGRO" + BOLD_OFF + LF;
    text += "Voucher de comida" + LF + LF;

    text += ALIGN_LEFT;
    text += `Nombre: ${personaPrintData.nombre}` + LF;
    text += `Documento: ${personaPrintData.dni}` + LF;
    text += `Credencial: ${personaPrintData.credencial || "-"}` + LF;
    text += `Concesionario: ${wrapText(personaPrintData.concesionario || "-", 30)}` + LF;
    text += SEP + LF;

    text += ALIGN_CENTER + BOLD_ON + (ticket.voucher || "-") + BOLD_OFF + LF;
    if (!isGuestVoucher) {
      text += ALIGN_LEFT + `Tipo de comida: ${mealType}` + LF;
    }
    text += ALIGN_LEFT + SEP + LF;

    text += `Dia: ${ticket.dia || formatDate(ticket.creado_en, false)}` + LF;
    text += `Hora: ${formatDate(ticket.creado_en, true)}` + LF;
    text += `Totem: ${ticket.totem_id || totemId}` + LF + LF;

    text += ALIGN_CENTER + (ticket.ticket_numero || "-") + LF;
    text += "Conserve este ticket para validacion" + LF + LF + LF;
    text += CUT;
    return text;
  }

  function sendToRawBt(payloadText) {
    window.RawBtPrinter.printText(payloadText);
  }

  function printTicketInBrowser(url) {
    if (!url) {
      return;
    }
    const printUrl = `${url}${url.includes("?") ? "&" : "?"}autoprint=1&autoclose=1`;
    if (window.RawBtPrinter?.printPage) {
      window.RawBtPrinter.printPage(printUrl);
      return;
    }

    const popup = window.open(printUrl, `ticket-${Date.now()}`, "width=420,height=720");
    if (popup) {
      return;
    }

    const frame = document.createElement("iframe");
    frame.style.position = "fixed";
    frame.style.width = "1px";
    frame.style.height = "1px";
    frame.style.right = "-10000px";
    frame.style.bottom = "0";
    frame.style.opacity = "0";
    frame.setAttribute("aria-hidden", "true");
    frame.src = printUrl;
    document.body.appendChild(frame);
  }

  function printTicket(ticket) {
    if (!ticket) {
      return;
    }
    lastPrintedTicket = ticket;
    if (preferRawBt && window.RawBtPrinter) {
      sendToRawBt(buildRawBtTicketPayload(ticket));
      return;
    }
    printTicketInBrowser(ticket.print_url);
  }

  function showFlow(message) {
    if (!flowPrinting) {
      return;
    }
    if (!message) {
      flowPrinting.classList.add("hidden");
      return;
    }
    if (flowPrintingText) {
      flowPrintingText.textContent = message;
    }
    flowPrinting.classList.remove("hidden");
  }

  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  async function redeemBatch(items) {
    const response = await fetch(redeemUrl, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCookie("csrftoken"),
      },
      body: JSON.stringify({
        dni: personaPrintData.dni,
        totem_id: totemId,
        empresa_codigo: empresaCodigo || undefined,
        items,
      }),
    });

    const data = await response.json();
    if (!response.ok || !data.ok) {
      throw new Error(data?.error?.message || "No se pudo emitir la selección.");
    }
    return data;
  }

  async function printTickets(tickets) {
    if (preferRawBt) {
      for (let index = 0; index < tickets.length; index += 1) {
        const ticket = tickets[index];
        printTicket(ticket);
        await sleep(850);
      }
      return;
    }

    for (let index = 0; index < tickets.length; index += 1) {
      const ticket = tickets[index];
      printTicket(ticket);
      await sleep(280);
    }
  }

  function applySuccess(items) {
    items.forEach((item) => {
      const card = mealCards.find((row) => cardCode(row) === item.comida);
      if (!card) {
        return;
      }

      if (item.canjear_propio) {
        card.dataset.fixedUsed = String(fixedUsed(card) + 1);
        card.dataset.fixedAvailable = String(Math.max(fixedAvailable(card) - 1, 0));
        card.dataset.fixedStockAvailable = String(Math.max(fixedStockAvailable(card) - 1, 0));
      }

      if (item.invitados > 0) {
        card.dataset.guestUsed = String(guestUsed(card) + item.invitados);
        card.dataset.guestAvailable = String(Math.max(guestAvailable(card) - item.invitados, 0));
        card.dataset.guestStockAvailable = String(
          Math.max(guestStockAvailable(card) - item.invitados, 0)
        );
      }

      setOwnSelected(card, false);
      setInvitedSelected(card, 0);
    });
  }

  async function finalizeSelection() {
    if (processing) {
      return;
    }

    const items = buildBatchItems();
    if (items.length === 0) {
      setNotice("Seleccioná al menos una opción para canjear.");
      return;
    }

    processing = true;
    setNotice("Procesando selección...");
    const flowStartedAt = Date.now();
    showFlow(PRINTING_WAIT_MESSAGE);
    mealCards.forEach((card) => updateCardUI(card));
    updateSelectionInfo();

    try {
      const data = await redeemBatch(items);
      await printTickets(data.tickets || []);
      const flowElapsed = Date.now() - flowStartedAt;
      const remainingFlow = Math.max(PRINTING_MIN_VISIBLE_MS - flowElapsed, 0);
      if (remainingFlow > 0) {
        await sleep(remainingFlow);
      }

      applySuccess(items);

      const total = Number(data.total_tickets || 0);
      setNotice(`${total} ticket(s) generado(s). Finalizando...`);
      showFlow("");
      window.setTimeout(() => {
        window.location.href = startUrl;
      }, 1200);
    } catch (error) {
      showFlow("");
      setNotice(error.message || "No se pudo emitir la selección.");
    } finally {
      processing = false;
      mealCards.forEach((card) => updateCardUI(card));
      updateSelectionInfo();
    }
  }

  if (reprintLastBtn) {
    reprintLastBtn.addEventListener("click", () => {
      if (lastPrintedTicket) {
        printTicket(lastPrintedTicket);
      }
    });
  }

  if (clearBtn) {
    clearBtn.addEventListener("click", clearSelection);
  }

  if (finalizeBtn) {
    finalizeBtn.addEventListener("click", finalizeSelection);
  }

  if (!mealCards.length || !redeemUrl || !personaPrintData.dni) {
    resetIdle();
    return;
  }

  mealCards.forEach((card) => {
    ownByMeal.set(cardCode(card), false);
    invitedByMeal.set(cardCode(card), 0);

    const ownToggle = card.querySelector("[data-role='own-toggle']");
    const minusBtn = card.querySelector("[data-role='guest-minus']");
    const plusBtn = card.querySelector("[data-role='guest-plus']");

    if (ownToggle) {
      ownToggle.addEventListener("click", () => {
        setOwnSelected(card, !ownSelected(card));
      });
    }

    if (minusBtn) {
      minusBtn.addEventListener("click", () => {
        setInvitedSelected(card, invitedSelected(card) - 1);
      });
    }

    if (plusBtn) {
      plusBtn.addEventListener("click", () => {
        setInvitedSelected(card, invitedSelected(card) + 1);
      });
    }

    updateCardUI(card);
  });

  updateSelectionInfo();
  resetIdle();
})();
