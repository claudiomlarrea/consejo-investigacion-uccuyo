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

if (!state.sala) {
  state.sala = "uc-" + crypto.randomUUID().replace(/-/g, "").slice(0, 8);
  const url = new URL(location.href);
  url.pathname = "/aula";
  url.searchParams.set("sala", state.sala);
  history.replaceState(null, "", url);
}

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
    if (accion !== "pulso") decir("");
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
  const compartida = sala.sync === "drive";
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

  const cont = $("asientos");
  cont.replaceChildren();
  sala.asientos.forEach((asiento, indice) => {
    const total = sala.asientos.length;
    const t = total === 1 ? 0.5 : indice / (total - 1);
    const x = 8 + t * 84;
    const y = 46 - Math.sin(t * Math.PI) * 18;
    const boton = document.createElement("button");
    boton.type = "button";
    boton.className = "asiento"
      + (asiento.nombre ? "" : " is-libre")
      + (asiento.propio ? " is-mio" : "")
      + (turno && turno.id === asiento.id ? " is-habla" : "");
    boton.style.left = x + "%";
    boton.style.top = y + "%";
    boton.style.zIndex = String(Math.round(y));
    const funcion = asiento.funcion || "";
    const rotulo = asiento.nombre
      ? (funcion ? funcion + ", " + asiento.nombre : asiento.nombre)
      : "Libre";
    boton.title = asiento.nombre
      ? (sala.conduzco && !asiento.propio ? "Dar la palabra a " + asiento.nombre : rotulo)
      : "Sentarme";
    boton.setAttribute("aria-label", rotulo);

    const cara = document.createElement("span");
    cara.className = "cara";
    if (asiento.cara && asiento.quien) {
      const img = document.createElement("img");
      img.alt = "";
      img.src = "/api/aula/" + encodeURIComponent(state.sala)
        + "/cara?client=" + encodeURIComponent(asiento.quien)
        + "&v=" + Math.floor(Date.now() / 3000);
      cara.append(img);
    }
    boton.append(cara);

    const silla = document.createElement("span");
    silla.className = "silla";
    if (funcion) {
      const cargo = document.createElement("strong");
      cargo.textContent = funcion;
      silla.append(cargo);
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
  $("btn-entrar").textContent = sala.adentro ? "Actualizar mi función" : "Entrar y prender mi cámara";
  pintarPantalla(sala);
  pintarRoster(sala);
  pintarAgenda();
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
  $("agenda-kicker").textContent = partes.concat(acta ? [acta] : []).join(" · ") || "Reunión sin armar";
  $("agenda-titulo").textContent = items.length
    ? items[indice]
    : "Agregá los temas de esta reunión.";
  $("agenda-meta").textContent = sala.organo
    ? "El número de acta lo pone esta unidad. No está atado a otra planilla."
    : "Elegí el órgano, la unidad y el número de acta, y guardá la reunión.";
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
  if (state.room && state.room.organo) decir("Reunión guardada. Quien entre por este enlace ve el mismo órgano y la misma acta.");
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

function guardarMeet(event) {
  event.preventDefault();
  const crudo = $("meet").value.trim();
  if (!crudo) return;
  if (!state.room || !state.room.adentro) {
    decir("Primero entrá al aula. Después pegá el enlace de Meet: es el audio, no otra sala.");
    return;
  }
  enviar("meet", { meet: crudo }).then(() => {
    if (state.room && state.room.meet_url) {
      decir("Enlace de Meet guardado. Abrilo para escuchar. Esta página sigue siendo la sala.");
    }
  });
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
  state.caraTimer = setInterval(enviarCara, 3000);
  enviarCara();
}

async function enviarCara() {
  const video = $("mi-cara");
  if (!state.camara || !video || !video.videoWidth) return;
  const ancho = 160;
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
  const blob = await new Promise((resolver) => lienzo.toBlob(resolver, "image/jpeg", 0.6));
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
    decir("Ya estás en la sala y se ve tu cara. Para escucharse, abrí Meet o pegá el enlace si ya lo tenés.");
  } else if (state.room && state.room.adentro) {
    decir("Entraste. La cámara no se prendió: probá «Prender mi cámara». El audio se escucha en Meet.");
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
  $("btn-meet-abrir").addEventListener("click", () => {
    const url = state.room && state.room.meet_url ? state.room.meet_url : "https://meet.google.com/new";
    window.open(url, "_blank", "noopener");
    if (!state.room || !state.room.meet_url) {
      decir("Se abrió Meet. Cuando tengas el enlace, pegalo abajo para que todos entren a la misma llamada.");
    }
  });
  $("btn-copiar").addEventListener("click", async () => {
    const enlace = location.origin + "/aula?sala=" + encodeURIComponent(state.sala);
    try {
      await navigator.clipboard.writeText(enlace);
      decir("Enlace del aula copiado. Pegalo en el chat de Meet.");
    } catch (_err) {
      decir(enlace);
    }
  });

  await engancharMeet();
  await cargarSala();
  if (state.nombre && state.funcion) await enviar("perfil");
  arrancarPoll();
  latido();
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) cargarSala();
  });
}

iniciar().catch((err) => decir(err.message));
