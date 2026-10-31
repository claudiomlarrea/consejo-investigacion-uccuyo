const state = {
  catalogo: null,
  actas: [],
  acta: null,
  detalle: null,
  page: "inicio",
  pubTab: "revista",
  sheetsOk: false,
};

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

function toast(msg) {
  const el = $("#toast");
  el.textContent = msg;
  el.hidden = false;
  clearTimeout(el._t);
  el._t = setTimeout(() => { el.hidden = true; }, 4200);
}

function escapeHtml(s) {
  return String(s || "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

async function api(path, opts) {
  const res = await fetch(path, opts);
  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch (e) { data = { detail: text }; }
  if (!res.ok) {
    const detail = data && data.detail;
    const msg = Array.isArray(detail && detail.errores)
      ? detail.errores.join(" ")
      : (typeof detail === "string" ? detail : (detail && JSON.stringify(detail)) || res.statusText);
    throw new Error(msg);
  }
  return data;
}

function escribirSheets() {
  return $("#escribir-sheets").checked;
}

async function confirmarEscritura() {
  if (!escribirSheets()) return true;
  return window.confirm("Esto agrega una fila en la planilla real de Google Sheets. ¿Continuar?");
}

const PAGINAS = ["inicio", "acta", "cargar", "od", "archivos"];
let heroListo = false;

function entrarHero(reiniciar) {
  const hero = $(".hero-copy");
  if (!hero) return;
  if (reiniciar) {
    hero.classList.remove("is-in");
    void hero.offsetWidth;
  }
  hero.classList.add("is-in");
  heroListo = true;
}

function ir(page, replay) {
  if (!PAGINAS.includes(page)) page = "inicio";
  state.page = page;
  $$(".page").forEach((el) => el.classList.toggle("is-on", el.id === page));
  $$(".menu-link").forEach((el) => el.classList.toggle("is-on", el.dataset.go === page));
  history.replaceState(null, "", "#" + page);
  window.scrollTo(0, 0);
  if (page === "inicio") {
    if (!heroListo) entrarHero(false);
    else if (replay !== false) entrarHero(true);
  }
  if (page === "od" && state.acta) {
    const od = $("#vista-previa-od");
    if (od) od.innerHTML = previewHtml();
  }
}

function grupoVisible(tipo) {
  const c = state.catalogo || { tipos_puntaje: [], tipos_director: [] };
  return {
    puntaje: (c.tipos_puntaje || []).includes(tipo),
    director: (c.tipos_director || []).includes(tipo),
    docente: tipo === "Categorización Docente",
    finanzas: tipo !== "Categorización Docente",
  };
}

function pintarGrupos() {
  const form = $("#form-tema");
  const tipo = form.tipo.value;
  const vis = grupoVisible(tipo);
  form.querySelectorAll("[data-group]").forEach((el) => {
    el.hidden = !vis[el.dataset.group];
  });
  pintarRevision();
}

function textoConteo(a) {
  if ((a.temas_hoja || 0) > 0) {
    return a.temas_hoja + " tema" + (a.temas_hoja === 1 ? "" : "s");
  }
  if (!state.sheetsOk && (a.temas_ensayo || 0)) {
    return a.temas_ensayo + " ensayo" + (a.temas_ensayo === 1 ? "" : "s");
  }
  return a.temas + " tema" + (a.temas === 1 ? "" : "s");
}

function opcionesActa() {
  return state.actas.map((a) =>
    "<option value=\"" + a.numero + "\">Acta " + a.numero + " · " + a.mes + " · " + a.estado_etiqueta + " (" + textoConteo(a) + ")</option>"
  ).join("");
}

function sincronizarSelectores() {
  $$("#selector-acta, #selector-acta-od, #selector-acta-inicio, #selector-acta-cargar").forEach((sel) => {
    if (!sel) return;
    const actual = String(sel.value);
    sel.innerHTML = opcionesActa();
    if (state.acta) sel.value = String(state.acta);
    else if (actual) sel.value = actual;
  });
}

function pintarAvisoPlanilla() {
  const hayHoja = (state.actas || []).some((a) => (a.temas_hoja || 0) > 0);
  let texto = "";
  if (state.sheetsOk) texto = "";
  else if (hayHoja) texto = "Temas leídos de la planilla del Consejo. Streamlit no se tocó.";
  else texto = "La planilla real no está conectada. Se ven solo ensayos de esta Mac.";
  $$("[data-aviso-planilla]").forEach((el) => {
    el.textContent = texto;
    el.classList.toggle("hidden", !texto);
  });
}

function renderMenus() {
  $("#menu-actas").innerHTML = state.actas.map((a) => `
    <button type="button" data-acta="${a.numero}">
      Acta ${a.numero} · ${a.mes}
      <small>${textoConteo(a)} · <span class="badge ${a.estado}">${a.estado_etiqueta}</span></small>
    </button>
  `).join("");
  $("#menu-actas").querySelectorAll("[data-acta]").forEach((btn) => {
    btn.addEventListener("click", () => elegirActa(Number(btn.dataset.acta), true));
  });
  $("#menu-od").innerHTML = state.actas.map((a) => `
    <button type="button" data-od="${a.numero}">
      Acta ${a.numero} · ${a.mes}
      <small>${textoConteo(a)}</small>
    </button>
  `).join("");
  $("#menu-od").querySelectorAll("[data-od]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      await elegirActa(Number(btn.dataset.od), false);
      ir("od");
    });
  });
  sincronizarSelectores();

  const archivos = state.actas.filter((a) => a.drive_url).map((a) => `
    <a href="${a.drive_url}" target="_blank" rel="noopener">Acta ${a.numero} · ${a.mes}</a>
  `).join("");
  $("#menu-archivos").innerHTML = archivos + '<a href="#archivos" data-go="archivos">Ver todas las carpetas</a>';
  $("#menu-archivos").querySelector('[data-go="archivos"]').addEventListener("click", (e) => {
    e.preventDefault();
    ir("archivos");
  });

  $("#lista-archivos").innerHTML = state.actas.map((a) => `
    <article class="card">
      <h2>Acta ${a.numero} · ${a.mes}</h2>
      <p>${a.fecha}</p>
      ${a.drive_url
        ? `<a class="btn btn-navy" href="${a.drive_url}" target="_blank" rel="noopener">Abrir carpeta</a>`
        : "<p>Esta acta todavía no tiene carpeta de Drive.</p>"}
    </article>
  `).join("");
}

function poblarFormulario() {
  const c = state.catalogo;
  const opts = (arr, extra) => (extra || "") + arr.map((x) => "<option>" + escapeHtml(x) + "</option>").join("");
  $("#campo-tipo").innerHTML = opts(c.tipos);
  $("#campo-cat-dir").innerHTML = '<option value="">Seleccionar</option>' + opts(c.categorias);
  $("#campo-cat-codir").innerHTML = '<option value="">Seleccionar</option>' + opts(c.categorias);
  $("#campo-unidades").innerHTML = c.unidades.map((u) =>
    "<label><input type='checkbox' name='unidades' value=\"" + escapeHtml(u) + "\"><span>" + escapeHtml(u) + "</span></label>"
  ).join("");
  const draft = localStorage.getItem("consejo-borrador");
  if (draft) {
    try { aplicarBorrador(JSON.parse(draft)); } catch (e) {}
  }
  const resp = localStorage.getItem("consejo-responsable");
  if (resp && $("#form-tema").responsable && !$("#form-tema").responsable.value) {
    $("#form-tema").responsable.value = resp;
  }
  pintarGrupos();
}

function datosForm() {
  const form = $("#form-tema");
  const fd = new FormData(form);
  return {
    tipo: fd.get("tipo"),
    titulo: fd.get("titulo") || "",
    anio: fd.get("anio") || "2026",
    descripcion: fd.get("descripcion") || "",
    unidades: fd.getAll("unidades"),
    responsable: fd.get("responsable") || "",
    puntaje: fd.get("puntaje") || "",
    docente: fd.get("docente") || "",
    dni: fd.get("dni") || "",
    director: fd.get("director") || "",
    cat_director: fd.get("cat_director") || "",
    codirector: fd.get("codirector") || "",
    cat_codirector: fd.get("cat_codirector") || "",
    equipo: fd.get("equipo") || "",
    instituto: fd.get("instituto") || "",
    catedra: fd.get("catedra") || "",
    alumnos: fd.get("alumnos") || "",
    resolucion_cd: fd.get("resolucion_cd") || "",
    resolucion_cs: fd.get("resolucion_cs") || "",
    tipo_financiamiento: fd.get("tipo_financiamiento") || "",
    fuente: fd.get("fuente") || "",
    monto: fd.get("monto") || "",
  };
}

function aplicarBorrador(data) {
  const form = $("#form-tema");
  Object.keys(data).forEach((k) => {
    if (k === "unidades") return;
    if (form.elements[k]) form.elements[k].value = data[k];
  });
  (data.unidades || []).forEach((u) => {
    const box = form.querySelector("input[name='unidades'][value=\"" + CSS.escape(u) + "\"]");
    if (box) box.checked = true;
  });
}

function item(label, valor, req) {
  const texto = String(valor || "").trim();
  if (texto) return [label, texto, "ok"];
  return [label, req ? "Pendiente" : "Sin cargar", req ? "pend" : "vacio"];
}

function tituloDuplicado(titulo) {
  const t = (titulo || "").trim().toLowerCase();
  if (!t || !state.detalle) return false;
  return (state.detalle.temas || []).some((x) => (x.titulo || "").trim().toLowerCase() === t);
}

function pintarRevision() {
  const d = datosForm();
  localStorage.setItem("consejo-borrador", JSON.stringify(d));
  if (d.responsable) localStorage.setItem("consejo-responsable", d.responsable);
  const vis = grupoVisible(d.tipo);
  const actaTxt = state.acta ? "Acta " + state.acta : "Elegí un acta";
  const dup = tituloDuplicado(d.titulo);
  const filas = [
    ["Acta", actaTxt, state.acta ? "ok" : "pend"],
    item("Tipo", d.tipo, true),
    item("Denominación", d.titulo, true),
    item("Descripción", d.descripcion, false),
    vis.puntaje ? item("Puntaje", d.puntaje, false) : null,
    vis.docente ? item("Docente", d.docente, true) : null,
    vis.director ? item("Director", d.director, false) : null,
    vis.director ? item("Cátedra", d.catedra, d.tipo === "Proyecto de Cátedra") : null,
    item("Unidad", (d.unidades || []).join("; "), true),
    item("Responsable", d.responsable, true),
  ].filter(Boolean);
  const aviso = dup
    ? "<div class='aviso-dup'>Ya hay un tema con esa denominación en esta acta.</div>"
    : "";
  $("#revision").innerHTML = "<strong>Revisión</strong><ul>" + filas.map(([k, v, cls]) =>
    "<li><span>" + k + "</span><span class='" + cls + "'>" + escapeHtml(v) + "</span></li>"
  ).join("") + "</ul>" + aviso;
}

let _actaSeq = 0;

function previewHtml() {
  const numero = state.acta;
  const temas = (state.detalle && state.detalle.temas) || [];
  if (!numero) return "";
  if (!temas.length) {
    return "<article class='card'><h2>Vista previa · Acta " + numero + "</h2><p>Esta acta no tiene temas.</p></article>";
  }
  let html = "<div class='preview-od'><h2>Vista previa · Acta " + numero + "</h2>";
  let unidadActual = null;
  temas.forEach((t, i) => {
    const unidad = t.unidad || "";
    if (unidad && unidad !== unidadActual) {
      html += "<h3>" + escapeHtml(unidad) + "</h3>";
      unidadActual = unidad;
    }
    html += "<article><strong>" + (i + 1) + ". " + escapeHtml(t.tipo) + " - " + escapeHtml(t.titulo || "(sin título)") + "</strong>";
    if (t.descripcion) html += "<p>Descripción: " + escapeHtml(t.descripcion) + "</p>";
    if (t.director) html += "<p>Director: " + escapeHtml(t.director) + "</p>";
    if (t.responsable) html += "<p>Responsable: " + escapeHtml(t.responsable) + "</p>";
    html += "</article>";
  });
  return html + "</div>";
}

function pintarCuerpoActa(htmlTemas, htmlPreview) {
  const box = $("#lista-temas");
  if (box) box.innerHTML = htmlTemas;
  const home = $("#lista-temas-inicio");
  if (home) home.innerHTML = htmlTemas;
  const od = $("#vista-previa-od");
  if (od && htmlPreview !== undefined) od.innerHTML = htmlPreview;
}

async function elegirActa(numero, abrir) {
  const seq = ++_actaSeq;
  state.acta = Number(numero);
  state.detalle = { acta: { numero: state.acta }, temas: [] };
  sincronizarSelectores();
  const cargando = "<article class='card'><p>Temas del Acta " + state.acta + "…</p></article>";
  pintarCuerpoActa(cargando, "<article class='card'><h2>Vista previa · Acta " + state.acta + "</h2><p>Cargando temas de esta acta.</p></article>");
  const data = await api("/api/actas/" + state.acta);
  if (seq !== _actaSeq) return;
  state.detalle = data;
  const a = data.acta;
  $("#acta-fecha").textContent = a.fecha;
  $("#acta-titulo").textContent = "Acta " + a.numero + " · " + a.mes;
  $("#acta-meta").textContent =
    textoConteo(a) +
    " · " + a.unidades + " de " + a.unidades_total + " unidades";
  $("#cargar-acta-label").textContent = "Se guarda en el Acta " + a.numero + " · " + a.mes + " · " + a.fecha + ".";
  $("#od-label").textContent = "Word del Acta " + a.numero + " · " + a.mes + ".";
  $("#aviso-cerrada").classList.toggle("hidden", a.estado !== "cerrada");
  const drive = $("#link-drive-acta");
  if (drive) {
    if (a.drive_url) {
      drive.href = a.drive_url;
      drive.classList.remove("hidden");
    } else {
      drive.removeAttribute("href");
      drive.classList.add("hidden");
    }
  }
  const pend = $("#pendientes");
  if (a.pendientes.length) {
    pend.innerHTML = "<div class='pills'><span class='pill'>Sin carga: " + a.pendientes.length + " unidades</span>" +
      a.pendientes.slice(0, 8).map((u) => "<span class='pill'>" + escapeHtml(u.split("-")[0]) + "</span>").join("") +
      "</div>";
  } else {
    pend.innerHTML = "<div class='pills'><span class='pill'>Todas las unidades tienen al menos un tema</span></div>";
  }
  $("#lista-responsables").innerHTML = data.responsables.map((r) =>
    "<option value=\"" + escapeHtml(r) + "\">"
  ).join("");
  const homeK = $("#home-acta-kicker");
  const homeT = $("#home-acta-titulo");
  if (homeK) homeK.textContent = a.fecha;
  if (homeT) homeT.textContent = "Temas cargados · Acta " + a.numero + " · " + a.mes;
  renderTemas();
  pintarRevision();
  sincronizarSelectores();
  if (abrir) ir("acta");
}

function puedeReordenar() {
  return !!(state.detalle && state.detalle.acta && state.detalle.acta.estado === "en_curso");
}

function tablaTemas(filas, conOrden) {
  if (!filas.length) {
    return "<article class='card'><p>Esta acta todavía no tiene temas cargados.</p></article>";
  }
  const orden = conOrden === undefined ? puedeReordenar() : !!conOrden;
  return `<div class="tabla-wrap"><table class="tabla-temas">
    <thead>
      <tr>
        ${orden ? '<th class="ord"></th>' : ""}
        <th>Tipo</th>
        <th>Denominación</th>
        <th>Unidad académica</th>
        <th>Director</th>
        <th>Responsable de carga</th>
      </tr>
    </thead>
    <tbody>
      ${filas.map((t) => `
        <tr data-fp="${encodeURIComponent(t.fingerprint)}">
          ${orden ? `<td class="ord">
            <button type="button" data-move="-1" title="Subir">↑</button>
            <button type="button" data-move="1" title="Bajar">↓</button>
          </td>` : ""}
          <td>${escapeHtml(t.tipo)}${t.ensayo ? " <span class='tag ensayo'>Ensayo</span>" : ""}</td>
          <td>${escapeHtml(t.titulo || "(sin título)")}</td>
          <td>${escapeHtml(t.unidad || "")}</td>
          <td>${escapeHtml(t.director || "")}</td>
          <td>${escapeHtml(t.responsable || "")}</td>
        </tr>
      `).join("")}
    </tbody>
  </table></div>`;
}

function renderTemas() {
  const q = (($("#buscar") && $("#buscar").value) || "").trim().toLowerCase();
  const temas = (state.detalle && state.detalle.temas) || [];
  const filtrados = temas.filter((t) => {
    const blob = [t.tipo, t.titulo, t.unidad, t.director, t.responsable].join(" ").toLowerCase();
    return !q || blob.includes(q);
  });
  const conteo = $("#conteo-temas");
  if (conteo) conteo.textContent = filtrados.length + " en pantalla";
  const html = !state.acta
    ? "<article class='card'><p>Elegí un acta en el menú superior Actas.</p></article>"
    : (!filtrados.length
      ? "<article class='card'><p>No hay temas" + (q ? " para esa búsqueda." : " cargados en esta acta.") + "</p></article>"
      : tablaTemas(filtrados));
  const box = $("#lista-temas");
  if (box) {
    box.innerHTML = html;
    box.querySelectorAll("tr[data-fp]").forEach((el) => {
      el.querySelectorAll("[data-move]").forEach((btn) => {
        btn.addEventListener("click", () => moverTema(decodeURIComponent(el.dataset.fp), Number(btn.dataset.move)));
      });
    });
  }
  const home = $("#lista-temas-inicio");
  if (home) home.innerHTML = state.acta ? tablaTemas(temas, false) : html;
  const od = $("#vista-previa-od");
  if (od) od.innerHTML = previewHtml();
}

async function moverTema(fp, delta) {
  if (!puedeReordenar()) {
    toast("Solo se reordenan los temas del acta en curso.");
    return;
  }
  const temas = state.detalle.temas.slice();
  const i = temas.findIndex((t) => t.fingerprint === fp);
  const j = i + delta;
  if (i < 0 || j < 0 || j >= temas.length) return;
  if ((temas[i].unidad || "").toLowerCase() !== (temas[j].unidad || "").toLowerCase()) {
    toast("Solo se reordena dentro de la misma unidad.");
    return;
  }
  const tmp = temas[i];
  temas[i] = temas[j];
  temas[j] = tmp;
  state.detalle.temas = temas;
  await api("/api/actas/" + state.acta + "/orden", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ fingerprints: temas.map((t) => t.fingerprint) }),
  });
  renderTemas();
}

async function enviarTema(ev) {
  ev.preventDefault();
  if (!state.acta) {
    toast("Elegí un acta en el menú Actas.");
    return;
  }
  const d = datosForm();
  if (tituloDuplicado(d.titulo)) {
    toast("Ese título ya está cargado en esta acta.");
    return;
  }
  if (state.detalle && state.detalle.acta && state.detalle.acta.estado === "cerrada") {
    if (!window.confirm("Esta acta está cerrada. ¿Cargar el tema igual?")) return;
  }
  if (!(await confirmarEscritura())) return;
  const body = datosForm();
  body.escribir_en_sheets = escribirSheets();
  try {
    const res = await api("/api/actas/" + state.acta + "/temas", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    localStorage.removeItem("consejo-borrador");
    if (body.responsable) localStorage.setItem("consejo-responsable", body.responsable);
    ev.target.reset();
    if (body.responsable) ev.target.responsable.value = body.responsable;
    if (state.catalogo) $("#campo-tipo").value = state.catalogo.tipos[0];
    pintarGrupos();
    toast(res.modo === "sheets" ? "Tema agregado a Google Sheets." : "Tema guardado en ensayo local.");
    state.actas = await api("/api/actas");
    renderMenus();
    await elegirActa(state.acta, true);
  } catch (err) {
    toast(err.message);
  }
}

async function descargarOD() {
  if (!state.acta) { toast("Elegí un acta en el menú."); return; }
  const res = await fetch("/api/actas/" + state.acta + "/od.docx");
  if (!res.ok) {
    const t = await res.json().catch(() => ({ detail: "No se pudo generar." }));
    toast(t.detail || "No se pudo generar.");
    return;
  }
  const blob = await res.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "Acta_" + state.acta + ".docx";
  a.click();
  URL.revokeObjectURL(a.href);
}

async function descargarInforme() {
  if (!state.acta) { toast("Elegí un acta en el menú."); return; }
  const nombre = $("#responsable-informe").value.trim();
  if (!nombre) { toast("Ingresá el responsable."); return; }
  const res = await fetch("/api/actas/" + state.acta + "/informe.docx?responsable=" + encodeURIComponent(nombre));
  if (!res.ok) {
    const t = await res.json().catch(() => ({ detail: "No hay temas." }));
    toast(t.detail || "No hay temas.");
    return;
  }
  const blob = await res.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "Informe_" + nombre + "_Acta_" + state.acta + ".docx";
  a.click();
}

async function verPreview() {
  if (!state.acta) { toast("Elegí un acta."); return; }
  if (!state.detalle || !state.detalle.acta || state.detalle.acta.numero !== state.acta) {
    await elegirActa(state.acta, false);
  }
  $("#vista-previa-od").innerHTML = previewHtml();
  ir("od");
}

let _buscaT = null;
async function buscarGlobal() {
  const q = ($("#buscar-global").value || "").trim();
  const box = $("#resultados-global");
  if (q.length < 2) {
    box.hidden = true;
    box.innerHTML = "";
    return;
  }
  const filas = await api("/api/temas?q=" + encodeURIComponent(q));
  if (!filas.length) {
    box.innerHTML = "<p style='padding:12px'>No hay coincidencias.</p>";
    box.hidden = false;
    return;
  }
  box.innerHTML = filas.map((t) => `
    <button type="button" data-ir-acta="${t.acta}">
      ${escapeHtml(t.titulo || "(sin título)")}
      <small>Acta ${t.acta} · ${escapeHtml(t.mes)} · ${escapeHtml(t.tipo)}</small>
    </button>
  `).join("");
  box.hidden = false;
  box.querySelectorAll("[data-ir-acta]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      box.hidden = true;
      await elegirActa(Number(btn.dataset.irActa), true);
    });
  });
}

async function conectarPlanilla() {
  const texto = $("#json-sa").value.trim();
  if (!texto) { toast("Pegá el JSON de la cuenta de servicio."); return; }
  try {
    const res = await api("/api/conectar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ json_text: texto }),
    });
    $("#json-sa").value = "";
    toast("Planilla conectada. " + res.filas + " filas leídas. Streamlit no se tocó.");
    state.sheetsOk = true;
    $("#card-conexion").classList.add("hidden");
    pintarAvisoPlanilla();
    state.actas = await api("/api/actas");
    renderMenus();
    if (state.acta) await elegirActa(state.acta, false);
  } catch (err) {
    toast(err.message);
  }
}

async function iniciar() {
  const [estado, catalogo, actas] = await Promise.all([
    api("/api/estado"),
    api("/api/catalogo"),
    api("/api/actas"),
  ]);
  state.catalogo = catalogo;
  state.actas = actas;
  state.sheetsOk = !!estado.sheets_ok;
  if (estado.sheets_ok || estado.produccion) {
    $("#card-conexion").classList.add("hidden");
  } else {
    $("#card-conexion").classList.remove("hidden");
  }
  pintarAvisoPlanilla();
  renderMenus();
  poblarFormulario();
  const enCurso = actas.find((a) => a.estado === "en_curso");
  if (enCurso) await elegirActa(enCurso.numero, false);
  const hash = (location.hash || "#inicio").replace("#", "");
  ir(PAGINAS.includes(hash) ? hash : "inicio", false);
}

document.addEventListener("click", (e) => {
  const go = e.target.closest("[data-go]");
  if (!go) return;
  const page = go.dataset.go;
  if (!page) return;
  e.preventDefault();
  ir(page);
  if (go.dataset.focus === "informe") $("#responsable-informe").focus();
});

$$(".btn-actualizar").forEach((btn) => {
  btn.addEventListener("click", async () => {
    await api("/api/actas/actualizar", { method: "POST" });
    state.actas = await api("/api/actas");
    renderMenus();
    if (state.acta) await elegirActa(state.acta, false);
    toast(state.sheetsOk ? "Planilla releída." : "Todavía no hay planilla. Se ven solo los ensayos.");
  });
});
function onCambioSelector(ev) {
  const n = Number(ev.target.value);
  if (n && n !== Number(state.acta)) elegirActa(n, false);
}
$$("#selector-acta, #selector-acta-od, #selector-acta-inicio, #selector-acta-cargar").forEach((sel) => {
  sel.addEventListener("change", onCambioSelector);
});
$("#btn-od").addEventListener("click", descargarOD);
$("#btn-od-inicio").addEventListener("click", descargarOD);
$("#btn-preview").addEventListener("click", verPreview);
$("#btn-conectar").addEventListener("click", conectarPlanilla);
$("#buscar-global").addEventListener("input", () => {
  clearTimeout(_buscaT);
  _buscaT = setTimeout(buscarGlobal, 250);
});
$("#descargar-informe").addEventListener("click", descargarInforme);
$("#buscar").addEventListener("input", renderTemas);
$("#form-tema").addEventListener("input", pintarRevision);
$("#form-tema").addEventListener("change", pintarGrupos);
$("#form-tema").addEventListener("submit", enviarTema);
window.addEventListener("hashchange", () => {
  const hash = location.hash.replace("#", "");
  if (PAGINAS.includes(hash)) ir(hash);
});

if ((location.hash || "#inicio").replace("#", "") === "inicio") {
  entrarHero(false);
}
iniciar().catch((err) => {
  toast(err.message);
});
