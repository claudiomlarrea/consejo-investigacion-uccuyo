const cuerpo = document.body;
const params = new URLSearchParams(location.search);
const estadoEl = document.getElementById("estado");

const state = {
  sala: params.get("sala") || cuerpo.dataset.sala || "consejo",
  client: localStorage.getItem("aula-client") || "",
  nombre: localStorage.getItem("aula-nombre") || "",
  room: null,
  items: [],
  actas: [],
  timer: 0,
};

if (!state.client) {
  state.client = crypto.randomUUID();
  localStorage.setItem("aula-client", state.client);
}

const $ = (id) => document.getElementById(id);

function decir(texto) {
  estadoEl.textContent = texto || "";
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

function actaInicial() {
  const q = params.get("acta");
  if (q) return q;
  return cuerpo.dataset.acta || "";
}

async function cargarSala() {
  const acta = state.room ? "" : actaInicial();
  const url = "/api/aula/" + encodeURIComponent(state.sala)
    + "?client=" + encodeURIComponent(state.client)
    + (acta ? "&acta=" + encodeURIComponent(acta) : "");
  const sala = await api(url);
  const cambioActa = !state.room || state.room.acta !== sala.acta;
  state.room = sala;
  pintarSala();
  if (cambioActa) await cargarTemas();
}

async function cargarTemas() {
  if (!state.room) return;
  try {
    const data = await api("/api/actas/" + state.room.acta + "/preview");
    state.items = data.items || [];
  } catch (err) {
    state.items = [];
    decir(err.message);
  }
  pintarAgenda();
}

async function enviar(accion, extra) {
  const cuerpoAccion = Object.assign({
    client: state.client,
    accion: accion,
    rev: state.room ? state.room.rev : null,
    nombre: $("nombre").value.trim(),
  }, extra || {});
  try {
    state.room = await api("/api/aula/" + encodeURIComponent(state.sala), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(cuerpoAccion),
    });
    decir("");
    pintarSala();
    if (accion === "acta") await cargarTemas();
  } catch (err) {
    decir(err.message);
    await cargarSala();
  }
}

function sentado() {
  return state.room && state.room.sentado !== null && state.room.sentado !== undefined;
}

function pintarSala() {
  const sala = state.room;
  if (!sala) return;
  const sync = $("sync");
  sync.textContent = sala.sync === "drive"
    ? "Sala compartida · " + sala.codigo
    : "Sala de este servidor · " + sala.codigo;
  sync.classList.toggle("is-off", sala.sync !== "drive");

  const select = $("acta");
  if (document.activeElement !== select && select.value !== String(sala.acta)) {
    select.value = String(sala.acta);
  }
  select.disabled = sala.conduzco === false;

  const turno = sala.turno;
  const palabra = $("palabra");
  if (turno && turno.nombre) {
    palabra.textContent = "Tiene la palabra: " + turno.nombre;
    palabra.classList.add("is-on");
  } else {
    palabra.textContent = "Nadie tiene la palabra";
    palabra.classList.remove("is-on");
  }

  const cont = $("asientos");
  cont.replaceChildren();
  sala.asientos.forEach((asiento, indice) => {
    const total = sala.asientos.length;
    const t = total === 1 ? 0.5 : indice / (total - 1);
    const x = 8 + t * 84;
    const y = 38 - Math.sin(t * Math.PI) * 22;
    const boton = document.createElement("button");
    boton.type = "button";
    boton.className = "asiento"
      + (asiento.nombre ? "" : " is-libre")
      + (asiento.propio ? " is-mio" : "")
      + (turno && turno.id === asiento.id ? " is-habla" : "");
    boton.dataset.rol = asiento.rol;
    boton.style.left = x + "%";
    boton.style.top = y + "%";
    boton.style.zIndex = String(Math.round(y));
    boton.title = asiento.nombre
      ? (sala.conduzco && !asiento.propio ? "Dar la palabra a " + asiento.nombre : asiento.nombre)
      : "Sentarme en " + asiento.etiqueta;
    boton.setAttribute("aria-label", asiento.etiqueta + (asiento.nombre ? ", " + asiento.nombre : ", libre"));

    const silla = document.createElement("span");
    silla.className = "silla";
    if (asiento.rol !== "consejero") {
      const rol = document.createElement("strong");
      rol.textContent = asiento.etiqueta;
      silla.append(rol);
    }
    const quien = document.createElement("em");
    quien.textContent = asiento.nombre || "Libre";
    silla.append(quien);
    boton.append(silla);
    boton.addEventListener("click", () => clickAsiento(asiento));
    cont.append(boton);
  });

  const cola = $("cola");
  cola.textContent = sala.cola.length
    ? "Piden la palabra: " + sala.cola.map((p) => p.nombre).filter(Boolean).join(", ")
    : "";

  $("btn-palabra").disabled = !sentado();
  $("btn-salir").disabled = !sentado();
  $("btn-conceder").disabled = !sala.conduzco || !sala.cola.length;
  const hablo = turno && sentado() && turno.id === sala.sentado;
  $("btn-ceder").disabled = !(hablo || (sala.conduzco && turno));
  $("btn-meet-abrir").disabled = !sala.meet_url;
  pintarAgenda();
}

function pintarAgenda() {
  const sala = state.room;
  if (!sala) return;
  const items = state.items;
  const indice = items.length ? Math.min(Math.max(sala.tema, 0), items.length - 1) : 0;
  state.indice = indice;
  const item = items[indice];
  $("agenda-kicker").textContent = sala.fecha
    ? "Acta " + sala.acta + " · " + sala.fecha
    : "Acta " + sala.acta;
  $("agenda-titulo").textContent = item
    ? item.titulo
    : (items.length ? "Ese tema no está en el orden del día." : "Esta acta todavía no tiene temas.");
  $("agenda-meta").textContent = item
    ? [item.tipo, item.unidad, item.director].filter(Boolean).join(" · ")
    : "";
  $("btn-anterior").disabled = !sala.conduzco || indice <= 0;
  $("btn-siguiente").disabled = !sala.conduzco || !items.length || indice >= items.length - 1;

  const lista = $("agenda-lista");
  lista.replaceChildren();
  items.forEach((tema, i) => {
    const li = document.createElement("li");
    const boton = document.createElement("button");
    boton.type = "button";
    if (i === indice) boton.className = "is-on";
    boton.disabled = sala.conduzco === false;
    const n = document.createElement("span");
    n.className = "n";
    n.textContent = String(i + 1);
    boton.append(n, document.createTextNode(tema.titulo || "Sin título"));
    boton.addEventListener("click", () => enviar("ir", { tema: i }));
    li.append(boton);
    lista.append(li);
  });
}

function clickAsiento(asiento) {
  const nombre = $("nombre").value.trim();
  if (!asiento.nombre) {
    if (!nombre) {
      decir("Escribí tu nombre y después elegí un asiento.");
      $("nombre").focus();
      return;
    }
    localStorage.setItem("aula-nombre", nombre);
    enviar("sentarse", { asiento: asiento.id, nombre: nombre });
    return;
  }
  if (asiento.propio) return;
  if (state.room && state.room.conduzco) {
    enviar("conceder", { asiento: asiento.id });
    return;
  }
  decir("Ese asiento está ocupado.");
}

function unirMeet(event) {
  event.preventDefault();
  const crudo = $("meet").value.trim();
  if (!crudo) return;
  api("/api/aula/codigo?texto=" + encodeURIComponent(crudo))
    .then((data) => {
      const url = new URL(location.href);
      url.pathname = "/aula";
      url.search = "";
      url.searchParams.set("sala", data.codigo);
      if (state.room) url.searchParams.set("acta", String(state.room.acta));
      location.href = url.href;
    })
    .catch((err) => decir(err.message));
}

async function engancharMeet() {
  if (window.parent === window) return;
  const project = cuerpo.dataset.meetProject;
  if (!project || !window.meet || !window.meet.addon) return;
  try {
    const session = await window.meet.addon.createAddonSession({ cloudProjectNumber: String(project) });
    const main = await session.createMainStageClient();
    const info = await main.getMeetingInfo();
    const codigo = info && info.meetingCode ? String(info.meetingCode).toLowerCase() : "";
    if (codigo && codigo !== state.sala) {
      const url = new URL(location.href);
      url.searchParams.set("sala", codigo);
      location.replace(url.href);
    }
  } catch (err) {
    decir("Meet no abrió la sesión del complemento. El aula sigue disponible en esta página.");
  }
}

function arrancarPoll() {
  clearInterval(state.timer);
  state.timer = setInterval(() => {
    if (!document.hidden) cargarSala().catch((err) => decir(err.message));
  }, 2000);
}

async function iniciar() {
  $("nombre").value = state.nombre;
  $("nombre").addEventListener("change", () => {
    localStorage.setItem("aula-nombre", $("nombre").value.trim());
  });
  if (sessionStorage.getItem("aula-banner") === "off") $("banner").classList.add("hidden");
  $("cerrar-banner").addEventListener("click", () => {
    $("banner").classList.add("hidden");
    sessionStorage.setItem("aula-banner", "off");
  });
  $("btn-palabra").addEventListener("click", () => enviar("palabra"));
  $("btn-ceder").addEventListener("click", () => enviar("ceder"));
  $("btn-conceder").addEventListener("click", () => enviar("conceder"));
  $("btn-salir").addEventListener("click", () => enviar("salir"));
  $("btn-anterior").addEventListener("click", () => {
    enviar("ir", { tema: Math.max(0, (state.indice || 0) - 1) });
  });
  $("btn-siguiente").addEventListener("click", () => {
    enviar("ir", { tema: (state.indice || 0) + 1 });
  });
  $("acta").addEventListener("change", () => {
    enviar("acta", { acta: Number($("acta").value) });
  });
  $("form-meet").addEventListener("submit", unirMeet);
  $("btn-meet-abrir").addEventListener("click", () => {
    if (state.room && state.room.meet_url) window.open(state.room.meet_url, "_blank", "noopener");
    else decir("Pegá el enlace de Meet para abrir la videollamada.");
  });
  $("btn-copiar").addEventListener("click", async () => {
    const enlace = location.origin + "/aula?sala=" + encodeURIComponent(state.sala)
      + (state.room ? "&acta=" + state.room.acta : "");
    try {
      await navigator.clipboard.writeText(enlace);
      decir("Enlace copiado. Pegalo en el chat de Meet.");
    } catch (_err) {
      decir(enlace);
    }
  });

  state.actas = await api("/api/actas");
  const select = $("acta");
  state.actas.forEach((acta) => {
    const opcion = document.createElement("option");
    opcion.value = String(acta.numero);
    opcion.textContent = "Acta " + acta.numero + " · " + acta.mes;
    select.append(opcion);
  });

  await engancharMeet();
  await cargarSala();
  arrancarPoll();
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) cargarSala().catch((err) => decir(err.message));
  });
}

iniciar().catch((err) => decir(err.message));
