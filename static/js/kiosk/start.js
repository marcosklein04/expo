(function () {
  const body = document.body;
  const dniUrl = body?.dataset?.dniUrl;
  const startBtn = document.getElementById("start-btn");
  const startScreen = document.getElementById("start-screen");

  if (!dniUrl || !startBtn || !startScreen) {
    return;
  }

  const isAndroidDevice = /Android/i.test(navigator.userAgent || "");
  let navigating = false;

  function goDni() {
    if (navigating) {
      return;
    }
    navigating = true;

    if (isAndroidDevice && !sessionStorage.getItem("rawbt_initialized")) {
      sessionStorage.setItem("rawbt_initialized", "1");
      try {
        window.RawBtPrinter?.startPrinter();
      } catch (error) {
        // If RawBT is unavailable, continue with kiosk navigation.
      }

      window.setTimeout(() => {
        window.location.href = dniUrl;
      }, 350);
      return;
    }

    window.location.href = dniUrl;
  }

  startBtn.addEventListener("click", goDni);
  startScreen.addEventListener("touchstart", goDni, { passive: true });
})();
