(function () {
  const body = document.body;
  const dniUrl = body?.dataset?.dniUrl;
  const startBtn = document.getElementById("start-btn");
  const startScreen = document.getElementById("start-screen");

  if (!dniUrl || !startBtn || !startScreen) {
    return;
  }

  let navigating = false;

  function goDni() {
    if (navigating) {
      return;
    }
    navigating = true;

    window.location.href = dniUrl;
  }

  startBtn.addEventListener("click", goDni);
  startScreen.addEventListener("touchstart", goDni, { passive: true });
})();
