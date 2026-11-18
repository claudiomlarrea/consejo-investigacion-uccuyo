const cuerpo = document.body;
const estado = document.getElementById("estado");
const select = document.getElementById("acta");

function decir(texto) {
  estado.textContent = texto || "";
}

async function cargarActas() {
  const respuesta = await fetch("/api/actas");
  const actas = await respuesta.json();
  const preferida = cuerpo.dataset.acta;
  actas.forEach((acta) => {
    const opcion = document.createElement("option");
    opcion.value = String(acta.numero);
    opcion.textContent = "Acta " + acta.numero + " · " + acta.mes;
    if (String(acta.numero) === preferida) opcion.selected = true;
    select.append(opcion);
  });
}

async function abrir() {
  const acta = select.value;
  const embebido = window.parent !== window;
  const project = cuerpo.dataset.meetProject;
  if (!embebido || !project || !window.meet || !window.meet.addon) {
    location.href = "/aula?acta=" + encodeURIComponent(acta);
    return;
  }
  decir("Abriendo el escenario…");
  try {
    const session = await window.meet.addon.createAddonSession({
      cloudProjectNumber: String(project),
    });
    const side = await session.createSidePanelClient();
    await side.startActivity({
      mainStageUrl: location.origin + "/aula/escenario?acta=" + encodeURIComponent(acta),
    });
    decir("El aula está en el escenario. El resto de la reunión tiene que aceptar unirse.");
  } catch (err) {
    decir(err && err.message ? err.message : "Meet no dejó abrir el aula.");
  }
}

document.getElementById("abrir").addEventListener("click", abrir);
cargarActas().catch(() => decir("No pude cargar las actas."));
