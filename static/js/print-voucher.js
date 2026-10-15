document.addEventListener("DOMContentLoaded", () => {
  const printButton = document.querySelector("[data-print-voucher]");
  if (printButton) {
    printButton.addEventListener("click", () => window.print());
  }
});
