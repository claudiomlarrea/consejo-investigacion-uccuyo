#!/usr/bin/env python3
"""Prototipo local del Consejo de Investigación. No publica ni toca Streamlit Cloud."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from catalogo import (
    ACTAS,
    CVAR_CARGADOS,
    CVAR_DRIVE,
    DRIVE,
    FECHAS,
    SHEET_URL,
    MAX_UNIDADES,
    TIPOS,
    TIPOS_CON_DIRECTOR,
    TIPOS_CON_PUNTAJE,
    UNIDADES,
    estado_acta,
    etiqueta_estado,
)
from puntaje import contar_palabras, parse_anio, parse_puntaje_formulario, puntaje_a_texto_celda
from sheets_client import (
    append_publicacion,
    append_tema,
    estado_conexion,
    guardar_cache_temas,
    guardar_cuenta_servicio,
    guardar_ensayo_publicacion,
    guardar_ensayo_tema,
    leer_cache_planilla,
    leer_ensayos,
    leer_hoja2,
    reset_conexion,
)
from word_docs import aplicar_orden_manual, construir_informe, construir_od, fingerprint, parsear_od_docx, unidad_de

STATIC = ROOT / "static"
ASSETS = ROOT / "assets"
if not ASSETS.is_dir():
    ASSETS = ROOT.parent / "assets"

app = FastAPI(title="Consejo de Investigación — prototipo local")
if ASSETS.is_dir():
    app.mount("/brand", StaticFiles(directory=str(ASSETS)), name="brand")

_orden_manual = {}  # type: Dict[int, List[str]]
_cache_hoja = {"rows": None, "error": None}  # type: Dict[str, Any]


class TemaIn(BaseModel):
    tipo: str
    titulo: str
    anio: str = "2026"
    descripcion: str = ""
    unidades: List[str] = Field(default_factory=list)
    responsable: str = ""
    puntaje: str = ""
    docente: str = ""
    dni: str = ""
    director: str = ""
    cat_director: str = ""
    codirector: str = ""
    cat_codirector: str = ""
    equipo: str = ""
    instituto: str = ""
    catedra: str = ""
    alumnos: str = ""
    resolucion_cd: str = ""
    resolucion_cs: str = ""
    tipo_financiamiento: str = ""
    fuente: str = ""
    monto: str = ""
    escribir_en_sheets: bool = False


class OrdenIn(BaseModel):
    fingerprints: List[str]


class PublicacionIn(BaseModel):
    clase: str
    campos: Dict[str, Any]
    escribir_en_sheets: bool = False


class ConectarIn(BaseModel):
    json_text: str


def _norm(r: Dict[str, Any]) -> Dict[str, Any]:
    return {str(k).lower().strip(): v for k, v in r.items()}


def _num_acta(valor) -> Optional[int]:
    if valor is None or valor == "":
        return None
    try:
        return int(float(str(valor).strip().replace(",", ".")))
    except (TypeError, ValueError):
        return None


def _titulo_de(r: Dict[str, Any]) -> str:
    row = _norm(r)
    return str(row.get("titulo") or row.get("título") or "").strip()


def _cargar_hoja(force: bool = False) -> List[Dict[str, Any]]:
    if _cache_hoja["rows"] is not None and not force:
        return _cache_hoja["rows"]
    info = estado_conexion()
    if info["sheets_ok"]:
        try:
            _cache_hoja["rows"] = leer_hoja2()
            _cache_hoja["error"] = None
            _cache_hoja["fuente"] = "sheets"
            return _cache_hoja["rows"]
        except Exception as exc:
            _cache_hoja["error"] = str(exc)
    local = leer_cache_planilla()
    _cache_hoja["rows"] = local
    if local:
        _cache_hoja["error"] = None
        _cache_hoja["fuente"] = "cache"
    else:
        _cache_hoja["error"] = _cache_hoja.get("error") or info["error"]
        _cache_hoja["fuente"] = None
    return local


def _temas_acta(numero: int) -> List[Dict[str, Any]]:
    hoja = _cargar_hoja()
    temas = [r for r in hoja if _num_acta(_norm(r).get("numero_acta")) == numero]
    for extra in leer_ensayos()["temas"]:
        if _num_acta(extra.get("numero_acta")) == numero:
            temas.append(extra)
    return temas


def _tema_publico(r: Dict[str, Any], idx: int) -> Dict[str, Any]:
    row = _norm(r)
    return {
        "id": idx,
        "fingerprint": fingerprint(r),
        "ensayo": bool(row.get("_ensayo")),
        "tipo": str(row.get("tipo") or "").strip(),
        "titulo": _titulo_de(r),
        "descripcion": str(row.get("descripcion") or row.get("descripción") or "").strip(),
        "unidad": unidad_de(r),
        "director": str(row.get("director") or "").strip(),
        "responsable": str(row.get("responsable_de_carga") or "").strip(),
        "puntaje": row.get("puntaje"),
        "docente": str(row.get("apellido_nombre_docente") or "").strip(),
        "instituto": str(row.get("instituto") or "").strip(),
        "catedra": str(row.get("catedra") or row.get("cátedra") or "").strip(),
    }


def _resumen_acta(numero: int) -> Dict[str, Any]:
    temas = _temas_acta(numero)
    presentes = set()
    for r in temas:
        for parte in unidad_de(r).split(";"):
            u = parte.strip()
            if u:
                presentes.add(u)
    pendientes = [u for u in UNIDADES if u not in presentes]
    hoja = [r for r in _cargar_hoja() if _num_acta(_norm(r).get("numero_acta")) == numero]
    ensayos = [e for e in leer_ensayos()["temas"] if _num_acta(e.get("numero_acta")) == numero]
    return {
        "numero": numero,
        "mes": ACTAS[numero],
        "fecha": FECHAS[numero],
        "estado": estado_acta(numero),
        "estado_etiqueta": etiqueta_estado(estado_acta(numero)),
        "temas": len(temas),
        "temas_hoja": len(hoja),
        "temas_ensayo": len(ensayos),
        "unidades": len(presentes),
        "unidades_total": len(UNIDADES),
        "pendientes": pendientes,
        "drive_url": DRIVE.get(numero),
        "sheet_url": SHEET_URL,
    }


@app.get("/", response_class=HTMLResponse)
def home():
    index = STATIC / "index.html"
    return HTMLResponse(
        index.read_text(encoding="utf-8"),
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@app.get("/static/{nombre}")
def static_file(nombre: str):
    path = STATIC / nombre
    if not path.is_file():
        raise HTTPException(404, "No encontrado")
    tipos = {
        ".css": "text/css",
        ".js": "application/javascript",
        ".png": "image/png",
        ".svg": "image/svg+xml",
        ".jpg": "image/jpeg",
        ".webp": "image/webp",
    }
    tipo = tipos.get(path.suffix.lower())
    return FileResponse(path, media_type=tipo, headers={"Cache-Control": "no-store, max-age=0"})


@app.get("/api/estado")
def api_estado():
    info = estado_conexion()
    _cargar_hoja()
    info["hoja_error"] = _cache_hoja["error"]
    info["ensayos"] = len(leer_ensayos()["temas"])
    info["cache_temas"] = len(leer_cache_planilla())
    info["fuente"] = _cache_hoja.get("fuente")
    info["sheet_url"] = SHEET_URL
    info["produccion"] = _en_produccion()
    return info


@app.get("/api/catalogo")
def api_catalogo():
    return {
        "tipos": TIPOS,
        "tipos_puntaje": sorted(TIPOS_CON_PUNTAJE),
        "tipos_director": sorted(TIPOS_CON_DIRECTOR),
        "categorias": [
            "Investigador/a Superior I",
            "Investigador/a Principal II",
            "Investigador/a Independiente III",
            "Investigador/a Adjunto/a IV",
            "Investigador/a Asistente V",
            "Becario/a de Iniciación VI",
            "Sin categorización / Externo",
        ],
        "unidades": UNIDADES,
        "max_unidades": MAX_UNIDADES,
        "cvar": {"cargados": CVAR_CARGADOS, "drive": CVAR_DRIVE, "estado": "cerrada"},
    }


@app.get("/api/actas")
def api_actas():
    _cargar_hoja()
    return [_resumen_acta(n) for n in ACTAS]


@app.post("/api/actas/actualizar")
def api_actualizar():
    rows = _cargar_hoja(force=True)
    return {"ok": True, "filas": len(rows), "error": _cache_hoja["error"]}


@app.get("/api/actas/{numero}")
def api_acta(numero: int):
    if numero not in ACTAS:
        raise HTTPException(404, "Acta inexistente")
    temas = aplicar_orden_manual(_temas_acta(numero), _orden_manual.get(numero))
    _orden_manual[numero] = [fingerprint(r) for r in temas]
    return {
        "acta": _resumen_acta(numero),
        "temas": [_tema_publico(r, i) for i, r in enumerate(temas)],
        "responsables": sorted(
            {
                str(_norm(r).get("responsable_de_carga") or "").strip()
                for r in temas
                if str(_norm(r).get("responsable_de_carga") or "").strip()
            }
        ),
        "titulos": [_titulo_de(r) for r in temas],
    }


@app.get("/api/temas")
def api_buscar(q: str = ""):
    texto = q.strip().casefold()
    out = []
    for numero in ACTAS:
        for i, r in enumerate(_temas_acta(numero)):
            t = _tema_publico(r, i)
            t["acta"] = numero
            t["mes"] = ACTAS[numero]
            blob = " ".join(
                [
                    str(numero),
                    ACTAS[numero],
                    t.get("tipo") or "",
                    t.get("titulo") or "",
                    t.get("unidad") or "",
                    t.get("director") or "",
                    t.get("responsable") or "",
                ]
            ).casefold()
            if texto and texto not in blob:
                continue
            out.append(t)
            if len(out) >= 80:
                return out
    return out


@app.get("/api/actas/{numero}/preview")
def api_preview(numero: int):
    if numero not in ACTAS:
        raise HTTPException(404, "Acta inexistente")
    temas = aplicar_orden_manual(_temas_acta(numero), _orden_manual.get(numero))
    items = []
    unidad_actual = None
    n = 1
    for r in temas:
        pub = _tema_publico(r, n)
        unidad = pub["unidad"]
        items.append(
            {
                "unidad_nueva": unidad if unidad != unidad_actual else None,
                "n": n,
                "tipo": pub["tipo"],
                "titulo": pub["titulo"],
                "descripcion": pub["descripcion"],
                "director": pub["director"],
                "responsable": pub["responsable"],
                "unidad": unidad,
            }
        )
        unidad_actual = unidad
        n += 1
    return {"acta": _resumen_acta(numero), "items": items}


@app.post("/api/actas/{numero}/importar-od")
async def api_importar_od(numero: int, archivo: UploadFile = File(...)):
    if numero not in ACTAS:
        raise HTTPException(404, "Acta inexistente")
    nombre = (archivo.filename or "").lower()
    if not nombre.endswith(".docx"):
        raise HTTPException(400, "Subí un Word .docx del Orden del Día.")
    data = await archivo.read()
    temas = parsear_od_docx(data, numero, FECHAS[numero])
    if not temas:
        raise HTTPException(400, "No se detectaron temas en ese Word.")
    guardar_cache_temas(temas, reemplazar_acta=numero)
    _cache_hoja["rows"] = None
    _cargar_hoja(force=True)
    return {"ok": True, "temas": len(temas), "titulos": [t.get("titulo") for t in temas]}


def _en_produccion() -> bool:
    return bool(
        os.environ.get("GOOGLE_SA_JSON")
        or os.environ.get("RENDER")
        or os.environ.get("RAILWAY_ENVIRONMENT")
        or os.environ.get("FLY_APP_NAME")
        or os.environ.get("VERCEL")
        or os.environ.get("VERCEL_ENV")
    )


@app.post("/api/conectar")
def api_conectar(body: ConectarIn):
    if _en_produccion():
        raise HTTPException(403, "En producción las credenciales van en el servidor, no en la página.")
    try:
        cuenta = json.loads(body.json_text)
    except Exception:
        raise HTTPException(400, "El texto no es un JSON válido.")
    try:
        guardar_cuenta_servicio(cuenta)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    reset_conexion()
    _cargar_hoja(force=True)
    info = estado_conexion()
    if not info["sheets_ok"]:
        raise HTTPException(503, info["error"] or "No se pudo abrir la planilla.")
    return {
        "ok": True,
        "filas": len(_cache_hoja["rows"] or []),
        "email": cuenta.get("client_email"),
    }


@app.post("/api/actas/{numero}/orden")
def api_orden(numero: int, body: OrdenIn):
    if numero not in ACTAS:
        raise HTTPException(404, "Acta inexistente")
    if estado_acta(numero) != "en_curso":
        raise HTTPException(400, "Solo se reordenan los temas del acta en curso.")
    _orden_manual[numero] = body.fingerprints
    return {"ok": True}


def _validar(numero: int, body: TemaIn) -> List[str]:
    errores = []
    if body.tipo not in TIPOS:
        errores.append("Elegí un tipo de actividad.")
    anio = parse_anio(body.anio)
    if anio is None:
        errores.append("El año debe tener 4 dígitos.")
    if not body.titulo.strip():
        errores.append("Falta la denominación del tema.")
    if not body.responsable.strip():
        errores.append("Falta el responsable de carga.")
    unidades = [u for u in body.unidades if u in UNIDADES]
    if not unidades:
        errores.append("Elegí al menos una unidad académica.")
    if len(unidades) > MAX_UNIDADES:
        errores.append("Como máximo 5 unidades académicas.")
    if contar_palabras(body.descripcion) > 50:
        errores.append("La descripción no puede superar las 50 palabras.")
    if contar_palabras(body.equipo) > 50:
        errores.append("El equipo no puede superar las 50 palabras.")
    if body.tipo == "Proyecto de Cátedra" and not body.catedra.strip():
        errores.append("En Proyecto de Cátedra la cátedra es obligatoria.")
    if body.tipo in TIPOS_CON_PUNTAJE:
        _valor, err = parse_puntaje_formulario(body.puntaje)
        if err:
            errores.append(err)
    if body.tipo == "Categorización Docente" and not body.docente.strip():
        errores.append("Falta el apellido y nombre del docente.")
    titulos = {_titulo_de(r).casefold() for r in _temas_acta(numero)}
    if body.titulo.strip().casefold() in titulos:
        errores.append("Ya hay un tema con esa denominación en esta acta.")
    return errores


def _fila_sheet(numero: int, body: TemaIn) -> List[Any]:
    anio = parse_anio(body.anio) or 2026
    unidades = "; ".join([u for u in body.unidades if u in UNIDADES])
    puntaje_txt = ""
    if body.tipo in TIPOS_CON_PUNTAJE:
        valor, _err = parse_puntaje_formulario(body.puntaje)
        if valor:
            puntaje_txt = puntaje_a_texto_celda(valor)
    cat_d = body.cat_director if body.cat_director not in ("", "Seleccionar") else ""
    cat_c = body.cat_codirector if body.cat_codirector not in ("", "Seleccionar") else ""
    fin = body.tipo_financiamiento if body.tipo_financiamiento not in ("", "Seleccionar...") else ""
    return [
        numero,
        FECHAS[numero],
        anio,
        body.tipo,
        body.titulo.strip(),
        body.descripcion.strip(),
        body.director.strip() if body.tipo in TIPOS_CON_DIRECTOR else "",
        cat_d if body.tipo in TIPOS_CON_DIRECTOR else "",
        body.codirector.strip() if body.tipo in TIPOS_CON_DIRECTOR else "",
        cat_c if body.tipo in TIPOS_CON_DIRECTOR else "",
        body.equipo.strip() if body.tipo in TIPOS_CON_DIRECTOR else "",
        body.docente.strip() if body.tipo == "Categorización Docente" else "",
        body.dni.strip() if body.tipo == "Categorización Docente" else "",
        unidades,
        body.resolucion_cd.strip()[:10] if body.tipo in TIPOS_CON_DIRECTOR else "",
        body.resolucion_cs.strip()[:10] if body.tipo in TIPOS_CON_DIRECTOR else "",
        body.instituto.strip() if body.tipo in TIPOS_CON_DIRECTOR else "",
        body.catedra.strip() if body.tipo in TIPOS_CON_DIRECTOR else "",
        fin if body.tipo != "Categorización Docente" else "",
        body.fuente.strip() if body.tipo != "Categorización Docente" else "",
        body.monto if body.tipo != "Categorización Docente" else "",
        body.alumnos.strip() if body.tipo in TIPOS_CON_DIRECTOR else "",
        puntaje_txt,
        body.responsable.strip(),
    ]


@app.post("/api/actas/{numero}/temas")
def api_cargar(numero: int, body: TemaIn):
    if numero not in ACTAS:
        raise HTTPException(404, "Acta inexistente")
    errores = _validar(numero, body)
    if errores:
        raise HTTPException(400, {"errores": errores})
    fila = _fila_sheet(numero, body)
    claves = [
        "numero_acta",
        "fecha",
        "año",
        "tipo",
        "titulo",
        "descripcion",
        "director",
        "cat_director",
        "codirector",
        "cat_codirector",
        "equipo",
        "apellido_nombre_docente",
        "dni_docente",
        "unidad académica",
        "resolucion_cd",
        "resolucion_cs",
        "instituto",
        "catedra",
        "tipo de financiamiento",
        "fuente de financiamiento",
        "monto del financiamiento",
        "alumnos",
        "puntaje",
        "responsable_de_carga",
    ]
    tema = dict(zip(claves, fila))
    if body.escribir_en_sheets:
        info = estado_conexion()
        if not info["sheets_ok"]:
            raise HTTPException(503, info["error"])
        append_tema(fila)
        _cargar_hoja(force=True)
        return {"ok": True, "modo": "sheets", "tema": _tema_publico(tema, 0)}
    tema["_ensayo"] = True
    guardar_ensayo_tema(tema)
    return {"ok": True, "modo": "ensayo", "tema": _tema_publico(tema, 0)}


@app.get("/api/actas/{numero}/od.docx")
def api_od(numero: int):
    if numero not in ACTAS:
        raise HTTPException(404, "Acta inexistente")
    temas = aplicar_orden_manual(_temas_acta(numero), _orden_manual.get(numero))
    if not temas:
        raise HTTPException(400, "Esta acta todavía no tiene temas.")
    data = construir_od(numero, temas)
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": 'attachment; filename="Acta_{}.docx"'.format(numero)},
    )


@app.get("/api/actas/{numero}/informe.docx")
def api_informe(numero: int, responsable: str = Query(...)):
    if numero not in ACTAS:
        raise HTTPException(404, "Acta inexistente")
    nombre = responsable.strip()
    if not nombre:
        raise HTTPException(400, "Ingresá el responsable de carga.")
    temas = [
        r
        for r in _temas_acta(numero)
        if str(_norm(r).get("responsable_de_carga") or "").strip().lower() == nombre.lower()
    ]
    if not temas:
        raise HTTPException(404, "No hay temas de ese responsable en esta acta.")
    data = construir_informe(numero, nombre, aplicar_orden_manual(temas, None))
    seguro = "".join(c if c.isalnum() or c in "._-" else "_" for c in nombre)
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": 'attachment; filename="Informe_{}_Acta_{}.docx"'.format(
                seguro, numero
            )
        },
    )


def _fila_publicacion(body: PublicacionIn) -> List[Any]:
    c = body.campos
    clase = body.clase
    if clase == "revista":
        indexacion = c.get("indexacion") or ""
        if indexacion == "Otra":
            indexacion = c.get("indexacion_otra") or "Otra"
        return [
            "Revista",
            c.get("titulo") or "",
            c.get("autores") or "",
            c.get("revista") or "",
            c.get("doi") or "",
            c.get("anio") or 2026,
            c.get("unidad") or "",
            indexacion,
        ]
    if clase == "libro":
        tipo = c.get("tipo") or "Libro"
        return [
            tipo,
            c.get("titulo") or "",
            c.get("autores") or "",
            "",
            "",
            c.get("anio") or 2026,
            c.get("unidad") or "",
            "",
            c.get("editorial") or "",
            c.get("isbn") or "",
            tipo,
            "",
            "",
            "",
            "",
            "",
            "",
            "",
        ]
    if clase == "repositorio":
        repo = c.get("repositorio") or ""
        if repo == "Otro":
            repo = c.get("repositorio_otro") or "Otro"
        return [
            "Repositorio",
            c.get("titulo") or "",
            c.get("autores") or "",
            "",
            "",
            c.get("anio") or 2026,
            c.get("unidad") or "",
            "",
            "",
            "",
            c.get("tipo") or "",
            c.get("link") or "",
            "",
            "",
            "",
            "",
            repo,
        ]
    if clase == "evento":
        return [
            "Evento",
            c.get("trabajo") or "",
            "",
            "",
            "",
            str(c.get("fecha") or "")[:4],
            c.get("unidad") or "",
            "",
            "",
            "",
            c.get("tipo") or "",
            "",
            c.get("evento") or "",
            c.get("lugar") or "",
            c.get("fecha") or "",
            "",
            "",
        ]
    if clase == "diario":
        return [
            "Diario",
            c.get("titulo") or "",
            c.get("autores") or "",
            c.get("medio") or "",
            "",
            str(c.get("fecha") or "")[:4],
            c.get("unidad") or "",
            "",
            "",
            "",
            "Artículo periodístico",
            c.get("link") or "",
            "",
            "",
            c.get("fecha") or "",
            c.get("resumen") or "",
            "",
        ]
    raise HTTPException(400, "Tipo de publicación desconocido.")


@app.post("/api/publicaciones")
def api_publicacion(body: PublicacionIn):
    fila = _fila_publicacion(body)
    if body.escribir_en_sheets:
        info = estado_conexion()
        if not info["sheets_ok"]:
            raise HTTPException(503, info["error"])
        append_publicacion(fila)
        return {"ok": True, "modo": "sheets"}
    guardar_ensayo_publicacion({"clase": body.clase, "campos": body.campos})
    return {"ok": True, "modo": "ensayo"}


@app.get("/api/publicaciones/ensayos")
def api_pub_ensayos():
    return leer_ensayos()["publicaciones"]


if __name__ == "__main__":
    import uvicorn

    puerto = int(os.environ.get("PORT", "8780"))
    host = os.environ.get("HOST", "127.0.0.1")
    print("Consejo de Investigación")
    print("Abrí http://{}:{}".format(host, puerto))
    uvicorn.run("app:app", host=host, port=puerto, reload=host == "127.0.0.1")
