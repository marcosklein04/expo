/*function rawBtPrintText(text, packageName = "ru.a402d.rawbtprinter") {
  const textEncoded = encodeURI(String(text || ""));
  const suffix = `#Intent;scheme=rawbt;package=${packageName};end;`;
  window.location.href = `intent:${textEncoded}${suffix}`;
}

function startPrinterRawBt() {
  rawBtPrintText("test");
}*/

function closePrint() {
  if (this && this.__container__ && this.__container__.parentNode) {
    this.__container__.parentNode.removeChild(this.__container__);
  }
}

function setPrint() {
  this.contentWindow.__container__ = this;
  this.contentWindow.onbeforeunload = closePrint;
  this.contentWindow.onafterprint = closePrint;
  this.contentWindow.focus();
  this.contentWindow.print();
}

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
