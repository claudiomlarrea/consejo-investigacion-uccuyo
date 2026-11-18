const estado = document.getElementById("estado");

document.getElementById("abrir").addEventListener("click", () => {
  const codigo = "uc-" + crypto.randomUUID().replace(/-/g, "").slice(0, 8);
  location.href = "/aula?sala=" + encodeURIComponent(codigo);
});

estado.textContent = "";
