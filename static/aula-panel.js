const cuerpo = document.body;
const estado = document.getElementById("estado");
const project = cuerpo.dataset.meetProject || "";

const state = {
  sala: "",
  client: localStorage.getItem("aula-client") || "",
  room: null,
  enMeet: false,
  reunionPendiente: false,
  sidePanel: null,
  timer: 0,
  cargando: false,
};

if (!state.client) {
  state.client = crypto.randomUUID();
  localStorage.setItem("aula-client", state.client);
}

const $ = (id) => document.getElementById(id);

function decir(texto) {
  estado.textContent = texto || "";
}

function aviso(texto, error) {
  const nodo = $("p-aviso");
  if (!nodo) return;
  nodo.textContent = texto || "";
  nodo.classList.toggle("is-error", Boolean(error && texto));
}

async function api(url, opciones) {
  const respuesta = await fetch(url, opciones);
  let data = null;
  try {
    data = await respuesta.json();
  } catch (_err) {
    data = null;
  }
  if (!respuesta.ok) {
    const detalle = data && (data.detail || data.error);
    const mensaje = typeof detalle === "string" ? detalle : "No se pudo actualizar el aula.";
    throw new Error(mensaje);
  }
  return data;
}

function identidad() {
  return {
    nombre: $("p-nombre").value.trim(),
    funcion: $("p-funcion").value.trim(),
  };
}

async function cargarSala(ingreso) {
  if (!state.sala) return;
  const url = "/api/aula/" + encodeURIComponent(state.sala)
    + "?client=" + encodeURIComponent(state.client)
    + (ingreso ? "&ingreso=1" : "");
  try {
    state.room = await api(url);
    pintar();
  } catch (err) {
    if (!state.room) decir(err.message);
  }
}

async function enviar(accion, extra, reintento) {
  if (!state.sala) return false;
  const datos = identidad();
  const cuerpoAccion = Object.assign({
    client: state.client,
    accion: accion,
    rev: state.room ? state.room.rev : null,
    nombre: datos.nombre,
    funcion: datos.funcion,
  }, extra || {});
  try {
    state.room = await api("/api/aula/" + encodeURIComponent(state.sala), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(cuerpoAccion),
    });
    pintar();
    return true;
  } catch (err) {
    if (!reintento && err.message && err.message.indexOf("Reintentá") !== -1) {
      await cargarSala();
      return enviar(accion, extra, true);
    }
    decir(err.message);
    if (accion === "agregar" || accion === "cargar") aviso(err.message, true);
    await cargarSala();
    return false;
  }
}

function sincronizar(input, valor) {
  if (!input || document.activeElement === input) return;
  if (input.value !== valor) input.value = valor;
}

function pintar() {
  const sala = state.room;
  if (!sala) return;
  sincronizar($("p-organo"), sala.organo || "");
  sincronizar($("p-unidad"), sala.unidad || "");
  sincronizar($("p-acta"), sala.acta || "");
  const items = sala.temas || [];
  const indice = items.length ? Math.min(Math.max(sala.tema || 0, 0), items.length - 1) : 0;
  $("p-tema").textContent = items.length
    ? items[indice]
    : "Agregá los temas del orden del día.";
  const empezar = $("p-comenzar");
  const activa = Boolean(sala.organo) && !sala.cerrada;
  if (empezar) {
    empezar.classList.toggle("is-pendiente", Boolean(state.reunionPendiente));
    empezar.classList.toggle("is-activa", activa && !state.reunionPendiente);
    if (state.reunionPendiente) {
      empezar.textContent = "Comenzar reunión";
      empezar.disabled = true;
    } else if (activa) {
      empezar.textContent = "Reunión en curso";
      empezar.disabled = true;
    } else {
      empezar.textContent = "Comenzar reunión";
      empezar.disabled = false;
    }
  }
  const entrarBtn = $("p-entrar");
  entrarBtn.textContent = sala.adentro ? "Guardar función" : "Entrar a la reunión";
  entrarBtn.classList.toggle("btn-oro", !sala.adentro);
  entrarBtn.classList.toggle("btn-fantasma", Boolean(sala.adentro));
  const lista = $("p-lista");
  lista.replaceChildren();
  items.forEach((titulo, i) => {
    const li = document.createElement("li");
    const boton = document.createElement("button");
    boton.type = "button";
    if (i === indice) boton.className = "is-on";
    boton.textContent = (i + 1) + ". " + (titulo || "Sin título");
    boton.addEventListener("click", () => enviar("ir", { tema: i }));
    li.append(boton);
    lista.append(li);
  });
  const turno = sala.turno && sala.turno.nombre;
  if (turno) decir("Tiene la palabra: " + turno);
}

async function entrar() {
  const datos = identidad();
  if (!datos.nombre) {
    decir("Escribí tu nombre.");
    $("p-nombre").focus();
    return;
  }
  if (!datos.funcion) {
    decir("Escribí tu función.");
    $("p-funcion").focus();
    return;
  }
  const ok = await enviar("perfil");
  if (ok) decir("Entraste al aula. Seguís en esta reunión.");
}

async function reunion(event) {
  event.preventDefault();
  if (state.reunionPendiente) return;
  if (state.room && state.room.organo && !state.room.cerrada) return;
  if (!state.room || !state.room.adentro) {
    decir("Primero entrá con tu nombre y tu función.");
    $("p-nombre").focus();
    return;
  }
  state.reunionPendiente = true;
  pintar();
  const ok = await enviar("reunion", {
    organo: $("p-organo").value,
    unidad: $("p-unidad").value.trim(),
    acta: $("p-acta").value.trim(),
  });
  state.reunionPendiente = false;
  pintar();
  if (ok && state.room && state.room.organo && !state.room.cerrada) {
    decir("La reunión comenzó. El aula sigue en el escenario.");
  }
}

async function agregar(event) {
  event.preventDefault();
  const titulo = $("p-titulo").value.trim();
  if (!titulo) {
    aviso("Escribí el tema.", true);
    return;
  }
  aviso("Agregando el tema…", false);
  const ok = await enviar("agregar", { titulo: titulo });
  if (!ok) return;
  $("p-titulo").value = "";
  aviso("Tema agregado. Ya se ve en el escenario.", false);
}

async function cargarArchivo() {
  const input = $("p-archivo");
  const archivo = input.files && input.files[0];
  if (!archivo) {
    aviso("Elegí un Word (.docx) o un PDF.", true);
    return;
  }
  if (state.cargando) return;
  state.cargando = true;
  aviso("Cargando temas de " + archivo.name + "…", false);
  const datos = new FormData();
  datos.append("archivo", archivo);
  datos.append("client", state.client);
  if (state.room && state.room.rev != null) datos.append("rev", String(state.room.rev));
  try {
    state.room = await api("/api/aula/" + encodeURIComponent(state.sala) + "/temas", {
      method: "POST",
      body: datos,
    });
    input.value = "";
    pintar();
    const cantidad = (state.room.temas || []).length;
    aviso("Temas cargados. El orden del día tiene " + cantidad + ".", false);
  } catch (err) {
    aviso(err.message, true);
  } finally {
    state.cargando = false;
  }
}

function mostrarControles() {
  $("controles").hidden = false;
  $("abrir").hidden = true;
  $("p-nombre").value = "";
  $("p-funcion").value = "";
  clearInterval(state.timer);
  state.timer = setInterval(() => {
    if (!document.hidden) cargarSala();
  }, 3000);
}

function urlEscenario() {
  return location.origin + "/aula?sala=" + encodeURIComponent(state.sala);
}

async function mostrarAula() {
  if (!state.sidePanel || !state.sala) return;
  decir("Abriendo el aula en el escenario…");
  await state.sidePanel.startActivity({
    mainStageUrl: urlEscenario(),
    additionalData: JSON.stringify({ sala: state.sala }),
  });
  decir("El aula está en el escenario. Todos la ven en esta reunión.");
  $("escenario").hidden = false;
  $("escenario").textContent = "El aula ya está en el escenario";
}

async function prepararMeet() {
  if (window.parent === window) return false;
  if (!project || !window.meet || !window.meet.addon) {
    decir("Falta MEET_CLOUD_PROJECT_NUMBER en el servidor. El aula sigue en este panel, sin salir de Meet.");
    $("abrir").hidden = true;
    return true;
  }
  const session = await window.meet.addon.createAddonSession({
    cloudProjectNumber: String(project),
  });
  state.sidePanel = await session.createSidePanelClient();
  state.enMeet = true;
  document.body.classList.add("en-meet");
  $("nota-meet").hidden = false;
  $("panel-texto").textContent = "El aula es el escenario de esta reunión. Desde acá manejás el orden del día y la palabra.";
  $("pasos-lista").innerHTML = ""
    + "<li>El aula se abre en el escenario para todos, sin salir de Meet.</li>"
    + "<li>Escribí tu nombre y tu función.</li>"
    + "<li>El micrófono, la cámara y la pantalla los maneja Meet.</li>"
    + "<li>El orden del día y la palabra se ven acá y en el escenario.</li>";
  let codigo = "";
  try {
    const info = await state.sidePanel.getMeetingInfo();
    codigo = info && info.meetingCode ? String(info.meetingCode).toLowerCase() : "";
  } catch (_err) {
    codigo = "";
  }
  if (!codigo) {
    decir("Meet no pasó el código de la reunión. El aula sigue en este panel.");
    return true;
  }
  state.sala = codigo;
  mostrarControles();
  await cargarSala(true);
  $("escenario").hidden = false;
  let yaEsta = false;
  try {
    const inicial = await state.sidePanel.getActivityStartingState();
    yaEsta = Boolean(inicial && (inicial.mainStageUrl || inicial.additionalData));
  } catch (_err) {
    yaEsta = false;
  }
  if (yaEsta) {
    decir("El aula ya está en el escenario. Todos la ven en esta reunión.");
    $("escenario").textContent = "El aula ya está en el escenario";
    return true;
  }
  try {
    await mostrarAula();
  } catch (_err) {
    decir("Tocá Mostrar el aula a todos para abrir el escenario, sin salir de Meet.");
    $("escenario").textContent = "Mostrar el aula a todos";
  }
  return true;
}

function abrirSuelto() {
  const codigo = "uc-" + crypto.randomUUID().replace(/-/g, "").slice(0, 8);
  location.href = "/aula?sala=" + encodeURIComponent(codigo);
}

async function iniciar() {
  $("abrir").addEventListener("click", () => {
    if (state.enMeet || window.parent !== window) {
      decir("El aula se abre en el escenario. No hace falta salir de Meet.");
      return;
    }
    abrirSuelto();
  });
  $("escenario").addEventListener("click", () => {
    mostrarAula().catch(() => decir("No pude abrir el escenario. Probá de nuevo, sin salir de Meet."));
  });
  $("p-entrar").addEventListener("click", () => entrar());
  $("p-reunion").addEventListener("submit", reunion);
  $("p-tema-form").addEventListener("submit", agregar);
  $("p-cargar").addEventListener("click", () => cargarArchivo());
  $("p-archivo").addEventListener("change", () => {
    if ($("p-archivo").files && $("p-archivo").files.length) cargarArchivo();
  });
  $("p-palabra").addEventListener("click", () => enviar("palabra"));
  $("p-conceder").addEventListener("click", () => enviar("conceder"));
  $("p-ceder").addEventListener("click", () => enviar("ceder"));
  localStorage.removeItem("aula-nombre");
  localStorage.removeItem("aula-funcion");

  try {
    const adentro = await prepararMeet();
    if (!adentro) decir("");
  } catch (_err) {
    if (window.parent !== window) {
      decir("Meet no abrió el complemento. El aula sigue en este panel, sin salir de la reunión.");
      $("abrir").hidden = true;
    }
  }
}

iniciar();
