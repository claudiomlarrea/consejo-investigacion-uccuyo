const cuerpo = document.body;
const params = new URLSearchParams(location.search);
const estadoEl = document.getElementById("estado");

const state = {
  sala: params.get("sala") || cuerpo.dataset.sala || "",
  client: localStorage.getItem("aula-client") || "",
  nombre: localStorage.getItem("aula-nombre") || "",
  funcion: localStorage.getItem("aula-funcion") || "",
  room: null,
  timer: 0,
  fallos: 0,
  pulso: 0,
  captura: 0,
  caraTimer: 0,
  stream: null,
  camara: null,
  frameV: 0,
  lleno: false,
};

if (!state.client) {
  state.client = crypto.randomUUID();
  localStorage.setItem("aula-client", state.client);
}

if (!state.sala) document.body.classList.add("sin-sala");

const $ = (id) => document.getElementById(id);

function decir(texto) {
  estadoEl.textContent = texto || "";
}

function identidad() {
  return {
    nombre: $("nombre").value.trim(),
    funcion: $("funcion").value.trim(),
  };
}

function guardarIdentidad() {
  const datos = identidad();
  localStorage.setItem("aula-nombre", datos.nombre);
  localStorage.setItem("aula-funcion", datos.funcion);
  return datos;
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

async function cargarSala() {
  const url = "/api/aula/" + encodeURIComponent(state.sala)
    + "?client=" + encodeURIComponent(state.client);
  try {
    state.room = await api(url);
    state.fallos = 0;
    pintarSala();
  } catch (err) {
    state.fallos += 1;
    if (state.room) decir("Reconectando la sala…");
    else decir(err.message);
  }
}

async function enviar(accion, extra) {
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
    if (accion !== "pulso" && accion !== "senal" && accion !== "voz") decir("");
    pintarSala();
  } catch (err) {
    if (err.message && err.message.indexOf("llena") !== -1) state.lleno = true;
    decir(err.message);
    await cargarSala();
  }
}

function sincronizar(input, anterior, nuevo) {
  if (document.activeElement === input) return;
  if (anterior === undefined || input.value === anterior) input.value = nuevo;
}

function exigirIdentidad() {
  const datos = guardarIdentidad();
  if (!datos.nombre) {
    decir("Escribí tu nombre.");
    $("nombre").focus();
    return null;
  }
  if (!datos.funcion) {
    decir("Escribí tu función. Por ejemplo: Secretario de Investigación.");
    $("funcion").focus();
    return null;
  }
  return datos;
}

function sentado() {
  return state.room && state.room.sentado !== null && state.room.sentado !== undefined;
}

function pintarSala() {
  const sala = state.room;
  if (!sala) return;
  const sync = $("sync");
  const compartida = sala.sync === "drive" || sala.sync === "hoja";
  sync.textContent = (compartida ? "Sala compartida" : sala.sync === "degradado" ? "Reconectando" : "Sala de este servidor")
    + " · " + (sala.presentes || 0) + "/" + (sala.cupo || 100);
  sync.classList.toggle("is-off", !compartida);

  const antes = state.anterior || {};
  sincronizar($("organo"), antes.organo, sala.organo || "");
  sincronizar($("unidad"), antes.unidad, sala.unidad || "");
  sincronizar($("acta"), antes.acta, sala.acta || "");
  state.anterior = { organo: sala.organo || "", unidad: sala.unidad || "", acta: sala.acta || "" };
  const meet = $("meet");
  if (document.activeElement !== meet && sala.meet_url && !meet.value) meet.value = sala.meet_url;

  const turno = sala.turno;
  const palabra = $("palabra");
  if (turno && turno.nombre) {
    palabra.textContent = "Tiene la palabra: " + turno.nombre;
    palabra.classList.add("is-on");
  } else {
    palabra.textContent = "Nadie tiene la palabra";
    palabra.classList.remove("is-on");
  }

  pintarAsientos(sala, turno);

  const cola = $("cola");
  cola.textContent = sala.cola.length
    ? "Piden la palabra: " + sala.cola.map((p) => p.nombre).filter(Boolean).join(", ")
    : "";

  $("btn-palabra").disabled = !sentado();
  $("btn-salir").disabled = !sentado();
  $("btn-conceder").disabled = !sala.conduzco || !sala.cola.length;
  const hablo = turno && sentado() && turno.id === sala.sentado;
  $("btn-ceder").disabled = !(hablo || (sala.conduzco && turno));
  $("btn-entrar").textContent = sala.adentro ? "Actualizar mi función" : "Entrar y prender mi cámara";
  pintarPantalla(sala);
  pintarRoster(sala);
  pintarAgenda();
  conectarVoces();
}

function pintarAsientos(sala, turno) {
  const cont = $("asientos");
  const video = $("mi-cara");
  const ancla = $("mi-camara-video");
  const presentes = new Set(sala.asientos.map((asiento) => String(asiento.id)));
  [...cont.children].forEach((nodo) => {
    if (!presentes.has(nodo.dataset.id)) nodo.remove();
  });
  const marca = Math.floor(Date.now() / 4000);
  let videoEnAsiento = false;
  sala.asientos.forEach((asiento, indice) => {
    let boton = cont.querySelector('[data-id="' + asiento.id + '"]');
    if (!boton) {
      boton = document.createElement("button");
      boton.type = "button";
      boton.dataset.id = String(asiento.id);
      const cara = document.createElement("span");
      cara.className = "cara";
      const mano = document.createElement("span");
      mano.className = "mano";
      mano.textContent = "✋";
      mano.hidden = true;
      cara.append(mano);
      const silla = document.createElement("span");
      silla.className = "silla";
      const cargo = document.createElement("strong");
      const quien = document.createElement("em");
      silla.append(cargo, quien);
      boton.append(cara, silla);
      boton.addEventListener("click", () => clickAsiento(boton._asiento));
      cont.append(boton);
    }
    boton._asiento = asiento;
    const total = sala.asientos.length;
    const t = total === 1 ? 0.5 : indice / (total - 1);
    const x = 8 + t * 84;
    const y = 54 - Math.sin(t * Math.PI) * 16;
    const habla = Boolean(turno && turno.id === asiento.id);
    const pide = habla || (sala.cola || []).some((persona) => persona.id === asiento.id);
    const funcion = asiento.funcion || "";
    boton.className = "asiento"
      + (asiento.nombre ? "" : " is-libre")
      + (asiento.propio ? " is-mio" : "")
      + (habla ? " is-habla" : "")
      + (pide ? " is-mano" : "");
    boton.style.left = x + "%";
    boton.style.top = y + "%";
    boton.style.zIndex = String(Math.round(y));
    const rotulo = asiento.nombre
      ? (funcion ? funcion + ", " + asiento.nombre : asiento.nombre)
      : "Libre";
    boton.title = asiento.nombre
      ? (sala.conduzco && !asiento.propio ? "Dar la palabra a " + asiento.nombre : rotulo)
      : "Sentarme";
    boton.setAttribute("aria-label", rotulo + (pide ? ", con la mano levantada" : ""));
    const cara = boton.querySelector(".cara");
    const mano = cara.querySelector(".mano");
    mano.hidden = !pide;
    const propiaEnVivo = Boolean(asiento.propio && state.camara && video);
    if (propiaEnVivo) {
      if (video.parentElement !== cara) cara.append(video);
      video.hidden = false;
      videoEnAsiento = true;
    }
    let img = cara.querySelector("img");
    if (!propiaEnVivo && asiento.cara && asiento.quien) {
      const src = "/api/aula/" + encodeURIComponent(state.sala)
        + "/cara?client=" + encodeURIComponent(asiento.quien)
        + "&v=" + marca;
      if (!img) {
        img = document.createElement("img");
        img.alt = "";
        cara.append(img);
      }
      if (img.dataset.src !== src) {
        const previa = new Image();
        previa.onload = () => {
          if (img.dataset.pedido === src) {
            img.src = previa.src;
            img.dataset.src = src;
          }
        };
        img.dataset.pedido = src;
        previa.src = src;
      }
    } else if (img) {
      img.remove();
    }
    const cargo = boton.querySelector("strong");
    const quien = boton.querySelector("em");
    cargo.textContent = funcion;
    cargo.hidden = !funcion;
    quien.textContent = asiento.nombre || "Libre";
  });
  if (!videoEnAsiento && video && ancla && video.parentElement !== ancla) ancla.append(video);
}

function pintarRoster(sala) {
  const cuenta = $("roster-cuenta");
  const lista = $("roster-lista");
  if (!cuenta || !lista) return;
  const total = sala.presentes || 0;
  cuenta.textContent = total + " de " + (sala.cupo || 100) + " en la sala";
  lista.textContent = (sala.roster || []).map((p) => {
    return p.funcion ? p.nombre + " · " + p.funcion : p.nombre;
  }).join("  ·  ");
}

function pintarPantalla(sala) {
  const caja = $("pantalla-caja");
  const local = $("pantalla-local");
  const remota = $("pantalla-remota");
  const quien = $("pantalla-quien");
  const boton = $("btn-pantalla");
  const activa = sala.pantalla && sala.pantalla.activa;
  if (state.stream && (!activa || !sala.pantalla.propia)) dejarPantalla(false);
  if (!activa) {
    caja.hidden = true;
    local.hidden = true;
    remota.hidden = true;
    boton.textContent = "Compartir pantalla";
    return;
  }
  caja.hidden = false;
  quien.textContent = sala.pantalla.propia
    ? "Estás compartiendo tu pantalla. Cualquiera puede reemplazarla."
    : (sala.pantalla.nombre || "Alguien") + " está compartiendo su pantalla. Podés reemplazarla.";
  if (sala.pantalla.propia && state.stream) {
    local.hidden = false;
    remota.hidden = true;
    if (local.srcObject !== state.stream) local.srcObject = state.stream;
    boton.textContent = "Dejar de compartir";
    return;
  }
  local.hidden = true;
  remota.hidden = false;
  const marca = Math.floor(Date.now() / 2000);
  if (state.frameV !== marca) {
    state.frameV = marca;
    remota.src = "/api/aula/" + encodeURIComponent(state.sala) + "/pantalla?v=" + marca;
  }
  boton.textContent = "Compartir mi pantalla";
}

function pintarAgenda() {
  const sala = state.room;
  if (!sala) return;
  const items = sala.temas || [];
  const indice = items.length ? Math.min(Math.max(sala.tema || 0, 0), items.length - 1) : 0;
  state.indice = indice;
  const partes = [sala.organo_nombre, sala.unidad].filter(Boolean);
  const acta = sala.acta ? "Acta " + sala.acta : "";
  $("agenda-kicker").textContent = partes.concat(acta ? [acta] : []).join(" · ") || "Para comenzar";
  $("agenda-titulo").textContent = items.length
    ? items[indice]
    : "Todavía no hay temas en el orden del día.";
  const aviso = $("agenda-aviso");
  if (sala.cerrada) {
    $("agenda-meta").textContent = "La reunión está cerrada. Los temas quedan a la vista.";
  } else if (items.length) {
    $("agenda-meta").textContent = "El orden del día tiene " + items.length + (items.length === 1 ? " tema." : " temas.");
  } else {
    $("agenda-meta").textContent = "Elegí el Word o el PDF del orden del día. Los temas aparecen acá arriba.";
  }
  if (aviso && !aviso.dataset.fijo) aviso.textContent = "";
  const botonReunion = $("btn-reunion");
  if (botonReunion) botonReunion.textContent = sala.organo ? "Actualizar reunión" : "Comenzar reunión";
  const botonCerrar = $("btn-cerrar");
  if (botonCerrar) botonCerrar.textContent = sala.cerrada ? "Reabrir reunión" : "Cerrar reunión";
  const lead = $("guia-lead");
  if (lead) {
    if (sala.sync !== "drive" && sala.sync !== "hoja" && location.hostname === "consejo-investigacion.vercel.app") {
      lead.textContent = "Esta dirección no junta a los demás. Tocá Entrar a la reunión: seguís en el aula, en la sala compartida.";
    } else if (!sala.organo) {
      lead.textContent = "Ya estás en la reunión, en esta aula. Completá los datos y tocá Comenzar reunión. El micrófono se enciende acá.";
    } else {
      lead.textContent = "La reunión comenzó, en esta aula. El micrófono se enciende acá. Los demás entran con el mismo enlace.";
    }
  }
  $("btn-anterior").disabled = !sala.conduzco || indice <= 0;
  $("btn-siguiente").disabled = !sala.conduzco || !items.length || indice >= items.length - 1;

  const lista = $("agenda-lista");
  lista.replaceChildren();
  items.forEach((titulo, i) => {
    const li = document.createElement("li");
    const boton = document.createElement("button");
    boton.type = "button";
    if (i === indice) boton.className = "is-on";
    boton.disabled = sala.conduzco === false;
    const n = document.createElement("span");
    n.className = "n";
    n.textContent = String(i + 1);
    boton.append(n, document.createTextNode(titulo || "Sin título"));
    boton.addEventListener("click", () => enviar("ir", { tema: i }));
    li.append(boton);
    if (sala.conduzco) {
      const quitar = document.createElement("button");
      quitar.type = "button";
      quitar.className = "btn-texto";
      quitar.textContent = "Quitar";
      quitar.addEventListener("click", () => enviar("quitar", { tema: i }));
      li.append(quitar);
    }
    lista.append(li);
  });
}

function clickAsiento(asiento) {
  if (!asiento.nombre) {
    if (!exigirIdentidad()) return;
    enviar("sentarse", { asiento: asiento.id });
    return;
  }
  if (asiento.propio) return;
  if (state.room && state.room.conduzco) {
    enviar("conceder", { asiento: asiento.id });
    return;
  }
  decir("Entrá con tu nombre y tu función para dar la palabra.");
}

async function guardarReunion(event) {
  event.preventDefault();
  if (!state.room || !state.room.adentro) {
    decir("Primero entrá con tu nombre y tu función. Después guardá el órgano, la unidad y el acta.");
    $("nombre").focus();
    return;
  }
  await enviar("reunion", {
    organo: $("organo").value,
    unidad: $("unidad").value.trim(),
    acta: $("acta").value.trim(),
  });
  if (state.room && state.room.organo) decir("La reunión comenzó. Los demás entran pegando el mismo enlace de Meet.");
}

function encenderMicrofono() {
  alternarMicrofono();
}

const vocesPc = new Map();
const vocesHechas = new Set();
let microLocal = null;

function iceListo(pc) {
  if (pc.iceGatheringState === "complete") return Promise.resolve();
  return new Promise((resolver) => {
    const tope = setTimeout(resolver, 2500);
    pc.addEventListener("icegatheringstatechange", () => {
      if (pc.iceGatheringState === "complete") {
        clearTimeout(tope);
        resolver();
      }
    });
  });
}

function crearPc(otro) {
  const pc = new RTCPeerConnection({
    iceServers: [{ urls: "stun:stun.l.google.com:19302" }],
  });
  vocesPc.set(otro, pc);
  pc.addEventListener("track", (evento) => {
    let audio = document.getElementById("voz-" + otro);
    if (!audio) {
      audio = document.createElement("audio");
      audio.autoplay = true;
      audio.id = "voz-" + otro;
      audio.setAttribute("playsinline", "");
      document.body.appendChild(audio);
    }
    audio.srcObject = evento.streams[0] || new MediaStream([evento.track]);
    audio.play().catch(() => {});
  });
  return pc;
}

function agregarPistas(pc) {
  if (!microLocal) return;
  microLocal.getTracks().forEach((pista) => {
    if (!pc.getSenders().some((envio) => envio.track === pista)) pc.addTrack(pista, microLocal);
  });
}

async function ofrecer(otro) {
  if (vocesPc.has(otro) || vocesHechas.has("offer:" + otro)) return;
  vocesHechas.add("offer:" + otro);
  try {
    const pc = crearPc(otro);
    agregarPistas(pc);
    await pc.setLocalDescription(await pc.createOffer());
    await iceListo(pc);
    await enviar("senal", { senal: { para: otro, tipo: "offer", cuerpo: pc.localDescription.sdp } });
  } catch (_err) {
    vocesHechas.delete("offer:" + otro);
    const pc = vocesPc.get(otro);
    if (pc) pc.close();
    vocesPc.delete(otro);
  }
}

async function recibirSenal(senal) {
  if (!state.room || !state.room.adentro || senal.para !== state.client) return;
  if (senal.tipo === "offer") {
    const otroHabla = (state.room.voces || []).some((voz) => voz.client === senal.de);
    if (microLocal && otroHabla && state.client < senal.de) return;
    let pc = vocesPc.get(senal.de);
    if (pc && pc.signalingState === "stable") return;
    if (!pc) pc = crearPc(senal.de);
    agregarPistas(pc);
    await pc.setRemoteDescription({ type: "offer", sdp: senal.cuerpo });
    await pc.setLocalDescription(await pc.createAnswer());
    await iceListo(pc);
    await enviar("senal", { senal: { para: senal.de, tipo: "answer", cuerpo: pc.localDescription.sdp } });
    return;
  }
  if (senal.tipo !== "answer") return;
  const pc = vocesPc.get(senal.de);
  if (!pc || pc.signalingState !== "have-local-offer") return;
  await pc.setRemoteDescription({ type: "answer", sdp: senal.cuerpo });
}

function conectarVoces() {
  const boton = $("btn-micro");
  if (boton) {
    boton.textContent = microLocal ? "Apagar micrófono" : "Encender micrófono";
    boton.classList.toggle("is-vivo", Boolean(microLocal));
  }
  const sala = state.room;
  if (!sala || !sala.adentro) return;
  const idsVoces = new Set((sala.voces || []).map((voz) => voz.client));
  const otros = (sala.roster || []).map((persona) => persona.client).filter((id) => id && id !== state.client).slice(0, 30);
  Array.from(vocesPc.keys()).forEach((id) => {
    const sigue = idsVoces.has(id) || (microLocal && otros.indexOf(id) !== -1);
    if (sigue) return;
    vocesPc.get(id).close();
    vocesPc.delete(id);
    vocesHechas.delete("offer:" + id);
    const audio = document.getElementById("voz-" + id);
    if (audio) audio.remove();
  });
  if (microLocal) {
    otros.forEach((id) => {
      const otroHabla = idsVoces.has(id);
      if (!otroHabla || state.client < id) ofrecer(id);
    });
  }
  (sala.senales || []).forEach((senal) => {
    if (vocesHechas.has("senal:" + senal.id)) return;
    vocesHechas.add("senal:" + senal.id);
    recibirSenal(senal).catch(() => {});
  });
}

async function alternarMicrofono() {
  if (microLocal) {
    microLocal.getTracks().forEach((pista) => pista.stop());
    microLocal = null;
    vocesPc.forEach((pc) => pc.close());
    vocesPc.clear();
    document.querySelectorAll("audio[id^='voz-']").forEach((nodo) => nodo.remove());
    if (state.room && state.room.adentro) await enviar("voz", { micro: false });
    conectarVoces();
    decir("Micrófono apagado. Seguís en el aula.");
    return;
  }
  if (!state.sala) {
    decir("Pegá el enlace y tocá Entrar a la reunión. El micrófono se enciende en esta aula.");
    $("meet").focus();
    return;
  }
  if (!state.room || !state.room.adentro) {
    if (!exigirIdentidad()) return;
    await enviar("perfil");
  }
  if (!state.room || !state.room.adentro) return;
  try {
    microLocal = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
  } catch (_err) {
    decir("El navegador no dejó prender el micrófono. Permitilo en esta página, sin salir del aula.");
    return;
  }
  await enviar("voz", { micro: true });
  conectarVoces();
  decir("Micrófono encendido. Seguís en el aula.");
}

async function cargarArchivo() {
  const input = $("archivo-temas");
  const archivo = input.files && input.files[0];
  if (!archivo) {
    decir("Elegí un Word (.docx) o un PDF con los temas.");
    return;
  }
  if (!state.room || !state.room.adentro) {
    decir("Entrá con tu nombre y tu función para cargar los temas.");
    return;
  }
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
    pintarSala();
    const cantidad = (state.room.temas || []).length;
    const texto = "Temas cargados. El orden del día tiene " + cantidad + ".";
    const aviso = $("agenda-aviso");
    if (aviso) {
      aviso.dataset.fijo = "1";
      aviso.textContent = texto;
    }
    decir(texto);
    const titulo = $("agenda-titulo");
    if (titulo) titulo.scrollIntoView({ block: "center" });
  } catch (err) {
    const aviso = $("agenda-aviso");
    if (aviso) {
      aviso.dataset.fijo = "1";
      aviso.textContent = err.message;
    }
    decir(err.message);
  }
}

async function cerrarReunion() {
  if (!state.room || !state.room.adentro) {
    decir("Entrá con tu nombre y tu función para cerrar la reunión.");
    $("nombre").focus();
    return;
  }
  const cerrar = !state.room.cerrada;
  await enviar(cerrar ? "cerrar" : "reabrir");
  const texto = state.room && state.room.cerrada ? "Reunión cerrada." : "La reunión sigue abierta.";
  const aviso = $("agenda-aviso");
  if (aviso) {
    aviso.dataset.fijo = "1";
    aviso.textContent = texto;
  }
  decir(texto);
}

async function agregarTema(event) {
  event.preventDefault();
  const titulo = $("tema-titulo").value.trim();
  if (!titulo) return;
  if (!state.room || !state.room.adentro) {
    decir("Entrá con tu nombre y tu función para cargar temas.");
    return;
  }
  await enviar("agregar", { titulo: titulo });
  $("tema-titulo").value = "";
}

function origenCompartido() {
  if (state.room && (state.room.sync === "drive" || state.room.sync === "hoja")) return location.origin;
  if (location.hostname === "consejo-investigacion.vercel.app") {
    return "https://consejo-investigacion-uccuyo.vercel.app";
  }
  return location.origin;
}

async function guardarMeet(event) {
  event.preventDefault();
  const crudo = $("meet").value.trim();
  if (!crudo) {
    decir("Pegá el enlace de Meet del calendario.");
    $("meet").focus();
    return;
  }
  let data;
  try {
    data = await api("/api/aula/codigo?texto=" + encodeURIComponent(crudo));
  } catch (err) {
    decir(err.message);
    return;
  }
  const destino = origenCompartido() + "/aula?sala=" + encodeURIComponent(data.codigo);
  const misma = data.codigo === state.sala && origenCompartido() === location.origin;
  if (misma) {
    decir("Ya estás en la reunión, en esta aula. El micrófono se enciende acá.");
    return;
  }
  location.href = destino;
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
  } catch (_err) {
    decir("Meet no abrió la sesión del complemento. El aula sigue en esta página.");
  }
}

function arrancarPoll() {
  clearTimeout(state.timer);
  const paso = () => {
    const espera = state.fallos > 2 ? 8000 : 3000;
    state.timer = setTimeout(async () => {
      if (!document.hidden) await cargarSala();
      paso();
    }, espera);
  };
  paso();
}

function latido() {
  clearInterval(state.pulso);
  state.pulso = setInterval(() => {
    const datos = identidad();
    if (!datos.nombre || !datos.funcion || state.lleno || document.hidden) return;
    if (!state.room || !state.room.adentro) return;
    enviar("pulso", datos).catch(() => {});
  }, 20000);
}

async function prenderCamara() {
  if (state.camara) return true;
  try {
    state.camara = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "user", width: 320, height: 240 },
      audio: false,
    });
  } catch (_err) {
    decir("El navegador no mostró la cámara. Revisá el permiso y probá de nuevo.");
    return false;
  }
  const video = $("mi-cara");
  video.hidden = false;
  video.srcObject = state.camara;
  $("mi-cara-ayuda").hidden = true;
  $("btn-camara").textContent = "Apagar mi cámara";
  return true;
}

async function apagarCamara() {
  clearInterval(state.caraTimer);
  state.caraTimer = 0;
  if (state.camara) {
    state.camara.getTracks().forEach((pista) => pista.stop());
    state.camara = null;
  }
  const video = $("mi-cara");
  video.srcObject = null;
  video.hidden = true;
  $("mi-cara-ayuda").hidden = false;
  $("btn-camara").textContent = "Prender mi cámara";
  if (state.room && state.room.adentro) await enviar("camara", { camara: false });
}

function arrancarEnvioCara() {
  clearInterval(state.caraTimer);
  state.caraTimer = setInterval(enviarCara, 4000);
  enviarCara();
}

async function enviarCara() {
  const video = $("mi-cara");
  if (!state.camara || !video || !video.videoWidth) return;
  const ancho = 280;
  const alto = Math.max(1, Math.round(video.videoHeight * (ancho / video.videoWidth)));
  const lienzo = enviarCara.lienzo || (enviarCara.lienzo = document.createElement("canvas"));
  lienzo.width = ancho;
  lienzo.height = alto;
  const ctx = lienzo.getContext("2d");
  ctx.save();
  ctx.translate(ancho, 0);
  ctx.scale(-1, 1);
  ctx.drawImage(video, 0, 0, ancho, alto);
  ctx.restore();
  const blob = await new Promise((resolver) => lienzo.toBlob(resolver, "image/jpeg", 0.72));
  if (!blob || blob.size > 48000) return;
  try {
    await fetch(
      "/api/aula/" + encodeURIComponent(state.sala) + "/cara?client=" + encodeURIComponent(state.client),
      { method: "POST", headers: { "Content-Type": "image/jpeg" }, body: blob }
    );
  } catch (_err) {
    /* el próximo cuadro reintenta */
  }
}

async function entrar() {
  if (!exigirIdentidad()) return;
  const camara = prenderCamara();
  await enviar("perfil");
  const videoOk = await camara;
  if (videoOk) {
    await enviar("camara", { camara: true });
    arrancarEnvioCara();
    decir("Ya estás en la sala y se ve tu cara. El micrófono se enciende acá, con el botón de arriba.");
  } else if (state.room && state.room.adentro) {
    decir("Entraste. La cámara no se prendió: probá «Prender mi cámara». El micrófono se enciende acá.");
  }
}

async function alternarCamara() {
  if (state.camara) {
    await apagarCamara();
    return;
  }
  if (!exigirIdentidad()) return;
  if (!(await prenderCamara())) return;
  await enviar("perfil");
  await enviar("camara", { camara: true });
  arrancarEnvioCara();
}

async function compartirPantalla() {
  if (state.stream) {
    await dejarPantalla(true);
    return;
  }
  if (!exigirIdentidad()) return;
  let stream;
  try {
    stream = await navigator.mediaDevices.getDisplayMedia({ video: { frameRate: 5 }, audio: false });
  } catch (_err) {
    decir("No se compartió la pantalla.");
    return;
  }
  state.stream = stream;
  stream.getVideoTracks()[0].addEventListener("ended", () => dejarPantalla(true));
  await enviar("perfil");
  await enviar("pantalla");
  await enviarFrame();
  state.captura = setInterval(enviarFrame, 2000);
}

async function enviarFrame() {
  const video = $("pantalla-local");
  if (!state.stream || !video) return;
  if (!video.srcObject) video.srcObject = state.stream;
  if (!video.videoWidth) return;
  const ancho = Math.min(video.videoWidth, 1280);
  const alto = Math.max(1, Math.round(video.videoHeight * (ancho / video.videoWidth)));
  const lienzo = enviarFrame.lienzo || (enviarFrame.lienzo = document.createElement("canvas"));
  lienzo.width = ancho;
  lienzo.height = alto;
  lienzo.getContext("2d").drawImage(video, 0, 0, ancho, alto);
  const blob = await new Promise((resolver) => lienzo.toBlob(resolver, "image/jpeg", 0.55));
  if (!blob || blob.size > 180000) return;
  try {
    const respuesta = await fetch(
      "/api/aula/" + encodeURIComponent(state.sala) + "/pantalla?client=" + encodeURIComponent(state.client),
      { method: "POST", headers: { "Content-Type": "image/jpeg" }, body: blob }
    );
    if (respuesta.status === 403) dejarPantalla(false);
  } catch (_err) {
    /* el próximo cuadro reintenta */
  }
}

async function dejarPantalla(avisar) {
  clearInterval(state.captura);
  state.captura = 0;
  if (state.stream) {
    state.stream.getTracks().forEach((pista) => pista.stop());
    state.stream = null;
  }
  const local = $("pantalla-local");
  if (local) local.srcObject = null;
  if (avisar) await enviar("cortar");
}

async function iniciar() {
  $("nombre").value = state.nombre;
  $("funcion").value = state.funcion;
  $("nombre").addEventListener("change", guardarIdentidad);
  $("funcion").addEventListener("change", guardarIdentidad);
  $("btn-entrar").addEventListener("click", () => entrar());
  $("btn-camara").addEventListener("click", () => alternarCamara());
  $("btn-pantalla").addEventListener("click", () => compartirPantalla());
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
  $("form-reunion").addEventListener("submit", guardarReunion);
  $("form-tema").addEventListener("submit", agregarTema);
  $("form-meet").addEventListener("submit", guardarMeet);
  $("btn-micro").addEventListener("click", encenderMicrofono);
  $("btn-archivo").addEventListener("click", cargarArchivo);
  $("archivo-temas").addEventListener("change", () => {
    if ($("archivo-temas").files && $("archivo-temas").files.length) cargarArchivo();
  });
  $("btn-cerrar").addEventListener("click", cerrarReunion);

  if (!state.sala) {
    decir("Pegá el enlace de Meet del calendario y tocá Entrar a la reunión.");
    return;
  }

  await engancharMeet();
  await cargarSala();
  if (state.nombre && state.funcion) await enviar("perfil");
  if (state.room && !state.room.organo) {
    decir("Ya estás en la reunión, en esta aula. El micrófono se enciende acá. Falta tocar Comenzar reunión.");
  }
  arrancarPoll();
  latido();
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) cargarSala();
  });
}

iniciar().catch((err) => decir(err.message));
