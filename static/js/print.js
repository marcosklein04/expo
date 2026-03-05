
function printPage(sURL) {
  const hiddenFrame = document.createElement("iframe");
  hiddenFrame.onload = setPrint;
  hiddenFrame.style.position = "fixed";
  hiddenFrame.style.right = "0";
  hiddenFrame.style.bottom = "0";
  hiddenFrame.style.width = "0";
  hiddenFrame.style.height = "0";
  hiddenFrame.style.border = "0";
  hiddenFrame.src = sURL;
  document.body.appendChild(hiddenFrame);
}

window.RawBtPrinter = {
  printText: rawBtPrintText,
  startPrinter: startPrinterRawBt,
  printPage,
};
