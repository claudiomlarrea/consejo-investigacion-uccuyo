#!/usr/bin/env python3
"""Consejo de Investigación. Misma planilla que el sistema anterior. No lo reemplaza en GitHub."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from catalogo import (
    ACTAS,
    DRIVE,
    FECHAS,
    MAX_UNIDADES,
    SHEET_URL,
    TIPOS,
    TIPOS_CON_DIRECTOR,
    TIPOS_CON_PUNTAJE,
    UNIDADES,
    estado_acta,
    etiqueta_estado,
)
from puntaje import contar_palabras, parse_puntaje_formulario, puntaje_a_texto_celda
from sheets_client import (
    append_tema,
    estado_conexion,
    guardar_ensayo_tema,
    leer_cache_planilla,
    leer_ensayos,
    leer_hoja2,
)
from word_docs import aplicar_orden_manual, construir_informe, construir_od, fingerprint, unidad_de

ROOT = Path(__file__).resolve().parent
LOGO = ROOT / "assets" / "logo-uccuyo.png"
CATEGORIAS = [
    "",
    "Investigador/a Superior I",
    "Investigador/a Principal II",
    "Investigador/a Independiente III",
    "Investigador/a Adjunto/a IV",
    "Investigador/a Asistente V",
    "Becario/a de Iniciación VI",
    "Sin categorización / Externo",
]

st.set_page_config(page_title="Consejo de Investigación · UCCuyo", layout="wide")
st.markdown(
    """
<style>
header[data-testid="stHeader"] { background: #fff; }
.block-container { padding-top: 1.2rem; }
.ucc-top { display:flex; align-items:center; justify-content:space-between; gap:16px; margin-bottom:8px; }
.ucc-title { text-align:center; font-weight:700; font-size:1.35rem; color:#000; flex:1; }
</style>
""",
    unsafe_allow_html=True,
)


def _norm(r):
    return {str(k).lower().strip(): v for k, v in r.items()}


def _num_acta(valor):
    if valor is None or valor == "":
        return None
    try:
        return int(float(str(valor).strip().replace(",", ".")))
    except (TypeError, ValueError):
        return None


def _titulo(r):
    row = _norm(r)
    return str(row.get("titulo") or row.get("título") or "").strip()


@st.cache_data(ttl=45)
def _hoja():
    info = estado_conexion()
    if info["sheets_ok"]:
        try:
            return leer_hoja2(), "sheets"
        except Exception:
            pass
    return leer_cache_planilla(), "cache"


def temas_acta(numero):
    hoja, _fuente = _hoja()
    temas = [r for r in hoja if _num_acta(_norm(r).get("numero_acta")) == numero]
    for extra in leer_ensayos()["temas"]:
        if _num_acta(extra.get("numero_acta")) == numero:
            temas.append(extra)
    key = "orden_%s" % numero
    orden = st.session_state.get(key)
    return aplicar_orden_manual(temas, orden)


def mover(numero, fp, delta):
    temas = temas_acta(numero)
    fps = [fingerprint(r) for r in temas]
    if fp not in fps:
        return
    i = fps.index(fp)
    j = i + delta
    if j < 0 or j >= len(fps):
        return
    if unidad_de(temas[i]).casefold() != unidad_de(temas[j]).casefold():
        st.warning("Solo se reordena dentro de la misma unidad.")
        return
    fps[i], fps[j] = fps[j], fps[i]
    st.session_state["orden_%s" % numero] = fps


col_logo, col_name, col_space = st.columns([1, 3, 1])
with col_logo:
    if LOGO.is_file():
        st.image(str(LOGO), width=72)
    st.caption("Consejo de Investigación")
    st.caption("Secretaría de Investigación")
with col_name:
    st.markdown('<p class="ucc-title">Universidad Católica de Cuyo</p>', unsafe_allow_html=True)

seccion = st.radio(
    "Secciones",
    ["Inicio", "Actas", "Cargar tema", "Orden del Día", "Carga de archivos"],
    horizontal=True,
    label_visibility="collapsed",
)

info = estado_conexion()
if not st.session_state.get("acta"):
    en_curso = next((n for n in ACTAS if estado_acta(n) == "en_curso"), 195)
    st.session_state.acta = en_curso

acta = st.session_state.acta
opciones = {
    n: "Acta %s · %s · %s (%s temas)"
    % (n, ACTAS[n], etiqueta_estado(estado_acta(n)), len(temas_acta(n)))
    for n in ACTAS
}

if seccion == "Inicio":
    st.markdown("### Consejo de Investigación")
    st.write(
        "Cargá temas, generá el Orden del Día y abrí las carpetas de archivos. "
        "La planilla de Google es la misma del sistema actual."
    )
    c1, c2, c3 = st.columns(3)
    if c1.button("Ver temas cargados"):
        st.session_state._ir = "Actas"
        st.rerun()
    if c2.button("Descargar Orden del Día"):
        st.session_state._ir = "Orden del Día"
        st.rerun()
    if c3.button("Cargar un tema"):
        st.session_state._ir = "Cargar tema"
        st.rerun()
    acta = st.selectbox("Acta", list(ACTAS), format_func=lambda n: opciones[n], index=list(ACTAS).index(acta) if acta in ACTAS else 0)
    st.session_state.acta = acta
    filas = temas_acta(acta)
    st.subheader("Temas cargados · Acta %s · %s" % (acta, ACTAS[acta]))
    if filas:
        st.dataframe(
            [
                {
                    "Tipo": _norm(r).get("tipo"),
                    "Denominación": _titulo(r),
                    "Unidad": unidad_de(r),
                    "Director": _norm(r).get("director"),
                    "Responsable": _norm(r).get("responsable_de_carga"),
                }
                for r in filas
            ],
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.info("Esta acta todavía no tiene temas.")
    if not info["sheets_ok"]:
        st.warning(
            "Para leer toda la planilla, en Streamlit Cloud → Settings → Secrets "
            "pegá el mismo bloque [gcp_service_account] del sistema anterior."
        )

elif seccion == "Actas":
    acta = st.selectbox("Acta", list(ACTAS), format_func=lambda n: opciones[n], key="sel_acta")
    st.session_state.acta = acta
    st.title("Acta %s · %s" % (acta, ACTAS[acta]))
    st.caption(FECHAS[acta])
    if DRIVE.get(acta):
        st.link_button("Abrir carpeta de esta acta", DRIVE[acta])
    st.link_button("Abrir planilla de temas", SHEET_URL)
    filas = temas_acta(acta)
    st.write("%s temas" % len(filas))
    for r in filas:
        fp = fingerprint(r)
        left, mid, right = st.columns([0.15, 0.7, 0.15])
        with left:
            if st.button("↑", key="up" + fp[:24]):
                mover(acta, fp, -1)
                st.rerun()
            if st.button("↓", key="dn" + fp[:24]):
                mover(acta, fp, 1)
                st.rerun()
        with mid:
            st.markdown("**%s** — %s" % (_norm(r).get("tipo") or "", _titulo(r) or "(sin título)"))
            st.caption("%s · %s" % (unidad_de(r), _norm(r).get("responsable_de_carga") or ""))

elif seccion == "Cargar tema":
    acta = st.selectbox("Acta", list(ACTAS), format_func=lambda n: opciones[n], key="sel_carga")
    st.session_state.acta = acta
    st.title("Cargar tema")
    st.caption("Se guarda en el Acta %s · %s." % (acta, ACTAS[acta]))
    with st.form("form_tema"):
        tipo = st.selectbox("Tipo de actividad", TIPOS)
        titulo = st.text_input("Denominación")
        descripcion = st.text_area("Descripción (máx. 50 palabras)")
        puntaje = st.text_input("Puntaje") if tipo in TIPOS_CON_PUNTAJE else ""
        docente = dni = ""
        director = cat_d = codirector = cat_c = equipo = instituto = catedra = alumnos = ""
        resol_cd = resol_cs = fin = fuente = monto = ""
        if tipo == "Categorización Docente":
            docente = st.text_input("Apellido y nombre del docente")
            dni = st.text_input("DNI")
        if tipo in TIPOS_CON_DIRECTOR:
            director = st.text_input("Director")
            cat_d = st.selectbox("Categoría del director", CATEGORIAS)
            codirector = st.text_input("Codirector")
            cat_c = st.selectbox("Categoría del codirector", CATEGORIAS)
            equipo = st.text_area("Equipo")
            instituto = st.text_input("Instituto")
            catedra = st.text_input("Cátedra")
            alumnos = st.text_input("Alumnos")
            resol_cd = st.text_input("Resolución CD", max_chars=10)
            resol_cs = st.text_input("Resolución CS", max_chars=10)
        if tipo != "Categorización Docente":
            fin = st.selectbox("Tipo de financiamiento", ["", "Interno", "Externo", "Sin financiamiento"])
            fuente = st.text_input("Fuente")
            monto = st.text_input("Monto")
        unidades = st.multiselect("Unidades académicas", UNIDADES)
        responsable = st.text_input("Responsable de carga")
        escribir = st.checkbox("Guardar en la planilla real")
        enviar = st.form_submit_button("Enviar al Consejo")
    if enviar:
        errores = []
        if not titulo.strip():
            errores.append("Falta la denominación.")
        if not responsable.strip():
            errores.append("Falta el responsable de carga.")
        if not unidades:
            errores.append("Elegí al menos una unidad académica.")
        if len(unidades) > MAX_UNIDADES:
            errores.append("Como máximo 5 unidades.")
        if contar_palabras(descripcion) > 50:
            errores.append("La descripción no puede superar las 50 palabras.")
        if tipo == "Proyecto de Cátedra" and not catedra.strip():
            errores.append("En Proyecto de Cátedra la cátedra es obligatoria.")
        if tipo in TIPOS_CON_PUNTAJE:
            _valor, err = parse_puntaje_formulario(puntaje)
            if err:
                errores.append(err)
        if tipo == "Categorización Docente" and not docente.strip():
            errores.append("Falta el docente.")
        if titulo.strip().casefold() in {_titulo(r).casefold() for r in temas_acta(acta)}:
            errores.append("Ya hay un tema con esa denominación en esta acta.")
        if errores:
            for e in errores:
                st.error(e)
        else:
            puntaje_txt = ""
            if tipo in TIPOS_CON_PUNTAJE:
                valor, _err = parse_puntaje_formulario(puntaje)
                if valor:
                    puntaje_txt = puntaje_a_texto_celda(valor)
            fila = [
                acta,
                FECHAS[acta],
                2026,
                tipo,
                titulo.strip(),
                descripcion.strip(),
                director.strip() if tipo in TIPOS_CON_DIRECTOR else "",
                cat_d if tipo in TIPOS_CON_DIRECTOR else "",
                codirector.strip() if tipo in TIPOS_CON_DIRECTOR else "",
                cat_c if tipo in TIPOS_CON_DIRECTOR else "",
                equipo.strip() if tipo in TIPOS_CON_DIRECTOR else "",
                docente.strip() if tipo == "Categorización Docente" else "",
                dni.strip() if tipo == "Categorización Docente" else "",
                "; ".join(unidades),
                resol_cd.strip()[:10] if tipo in TIPOS_CON_DIRECTOR else "",
                resol_cs.strip()[:10] if tipo in TIPOS_CON_DIRECTOR else "",
                instituto.strip() if tipo in TIPOS_CON_DIRECTOR else "",
                catedra.strip() if tipo in TIPOS_CON_DIRECTOR else "",
                fin if tipo != "Categorización Docente" else "",
                fuente.strip() if tipo != "Categorización Docente" else "",
                monto if tipo != "Categorización Docente" else "",
                alumnos.strip() if tipo in TIPOS_CON_DIRECTOR else "",
                puntaje_txt,
                responsable.strip(),
            ]
            claves = [
                "numero_acta", "fecha", "año", "tipo", "titulo", "descripcion",
                "director", "cat_director", "codirector", "cat_codirector", "equipo",
                "apellido_nombre_docente", "dni_docente", "unidad académica",
                "resolucion_cd", "resolucion_cs", "instituto", "catedra",
                "tipo de financiamiento", "fuente de financiamiento",
                "monto del financiamiento", "alumnos", "puntaje", "responsable_de_carga",
            ]
            tema = dict(zip(claves, fila))
            if escribir:
                if not info["sheets_ok"]:
                    st.error("No hay conexión a la planilla. Cargá Secrets en Streamlit Cloud.")
                else:
                    append_tema(fila)
                    _hoja.clear()
                    st.success("Tema agregado a Google Sheets. El sistema anterior no se tocó.")
            else:
                tema["_ensayo"] = True
                guardar_ensayo_tema(tema)
                st.success("Tema guardado solo en esta sesión (ensayo).")

elif seccion == "Orden del Día":
    acta = st.selectbox("Elegir Orden del Día", list(ACTAS), format_func=lambda n: opciones[n], key="sel_od")
    st.session_state.acta = acta
    st.title("Orden del Día")
    filas = temas_acta(acta)
    if not filas:
        st.info("Esta acta todavía no tiene temas.")
    else:
        st.download_button(
            "Descargar Word",
            data=construir_od(acta, filas),
            file_name="Acta_%s.docx" % acta,
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        responsable = st.text_input("Nombre del responsable")
        if responsable:
            propios = [
                r for r in filas
                if str(_norm(r).get("responsable_de_carga") or "").strip().casefold()
                == responsable.strip().casefold()
            ]
            if propios:
                st.download_button(
                    "Descargar informe",
                    data=construir_informe(acta, responsable, propios),
                    file_name="Informe_%s_Acta_%s.docx" % (responsable, acta),
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
        st.subheader("Vista previa · Acta %s" % acta)
        unidad_actual = None
        n = 1
        for r in filas:
            u = unidad_de(r)
            if u != unidad_actual:
                st.markdown("**%s**" % u)
                unidad_actual = u
            st.markdown("%s. %s - %s" % (n, _norm(r).get("tipo") or "", _titulo(r)))
            n += 1

else:
    st.title("Carga de archivos")
    st.caption("Se abre la carpeta de la acta. El archivo se sube ahí, igual que en el sistema actual.")
    cols = st.columns(3)
    i = 0
    for n, mes in ACTAS.items():
        with cols[i % 3]:
            st.subheader("Acta %s · %s" % (n, mes))
            st.caption(FECHAS[n])
            if DRIVE.get(n):
                st.link_button("Abrir carpeta", DRIVE[n])
            else:
                st.write("Esta acta todavía no tiene carpeta de Drive.")
        i += 1
