#!/usr/bin/env python3
"""Prototipo local del Consejo de Investigación. No publica ni toca Streamlit Cloud."""

from __future__ import annotations

import json
import os
import re
import sys
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import aula
from catalogo import (
    ACTAS,
    CORREOS_ORDEN_UNIDADES,
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
    correo_orden_unidades,
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
    guardar_orden_unidades,
    leer_cache_planilla,
    leer_ensayos,
    leer_hoja2,
    leer_orden_unidades,
    reset_conexion,
)
from word_docs import (
    aplicar_orden_od,
    construir_informe,
    construir_od,
    fingerprint,
    parsear_od_docx,
    unidad_de,
    unidades_en_orden,
)

STATIC = ROOT / "static"
ASSETS = ROOT / "assets"
if not ASSETS.is_dir():
    ASSETS = ROOT.parent / "assets"

app = FastAPI(title="Consejo de Investigación — prototipo local")
if ASSETS.is_dir():
    app.mount("/brand", StaticFiles(directory=str(ASSETS)), name="brand")

_orden_manual = {}  # type: Dict[int, List[str]]
_orden_unidades = {}  # type: Dict[int, List[str]]
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


class AulaIn(BaseModel):
    client: str = Field(min_length=8, max_length=80)
    accion: str
    nombre: str = ""
    funcion: str = ""
    asiento: Optional[int] = None
    acta: str = ""
    organo: str = ""
    unidad: str = ""
    meet: str = ""
    titulo: str = ""
    camara: bool = False
    tema: Optional[int] = None
    titulos: List[str] = Field(default_factory=list)
    micro: bool = False
    reemplazar: bool = False
    senal: Optional[Dict[str, str]] = None
    rev: Optional[int] = None


class OrdenIn(BaseModel):
    fingerprints: List[str]


class OrdenUnidadesIn(BaseModel):
    email: str
    unidades: List[str]


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


def _obtener_orden_unidades(numero: int, temas: Optional[List[Dict[str, Any]]] = None) -> List[str]:
    """Orden de bloques de unidad: memoria → planilla → aparición actual."""
    if numero in _orden_unidades and _orden_unidades[numero]:
        return list(_orden_unidades[numero])
    info = estado_conexion()
    if info["sheets_ok"]:
        try:
            guardado = leer_orden_unidades(numero)
            if guardado:
                _orden_unidades[numero] = list(guardado)
                return list(guardado)
        except Exception:
            pass
    base = temas if temas is not None else _temas_acta(numero)
    return unidades_en_orden(aplicar_orden_od(base, _orden_manual.get(numero), None))


def _temas_ordenados(numero: int) -> List[Dict[str, Any]]:
    temas = _temas_acta(numero)
    orden_u = _obtener_orden_unidades(numero, temas)
    ordenados = aplicar_orden_od(temas, _orden_manual.get(numero), orden_u)
    _orden_manual[numero] = [fingerprint(r) for r in ordenados]
    return ordenados


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


def _html_aula(nombre: str) -> HTMLResponse:
    html = (STATIC / nombre).read_text(encoding="utf-8")
    html = (
        html.replace("__ACTA__", "")
        .replace("__SALA__", "")
        .replace("__MEET_PROJECT__", os.environ.get("MEET_CLOUD_PROJECT_NUMBER", ""))
    )
    return HTMLResponse(html, headers={"Cache-Control": "no-store, max-age=0"})


def _origen(request: Request) -> str:
    proto = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip()
    host = (request.headers.get("x-forwarded-host") or request.headers.get("host") or "").split(",")[0].strip()
    if proto and host:
        return proto + "://" + host
    return str(request.base_url).rstrip("/")


@app.get("/aula")
@app.get("/aula/escenario")
def pagina_aula():
    return _html_aula("aula.html")


@app.get("/aula/panel")
def pagina_panel():
    return _html_aula("aula-panel.html")


@app.get("/aula/manifest.json")
def pagina_manifiesto(request: Request):
    return aula.manifest(_origen(request))


_PREFIJO_TEMA = re.compile(
    r"^(?:(?:tema|punto)\s+)?(?:\d{1,2}|[ivxlcdm]{1,6}|[a-z])[\.\)\-]\s+",
    re.IGNORECASE,
)
_SALTO_TEMA = re.compile(
    r"^(?:orden del d[ií]a|acta\b|fecha\b|p[aá]gina\b|page\b|universidad cat[oó]lica)\b",
    re.IGNORECASE,
)


def temas_desde_texto(texto: str) -> List[str]:
    partes = re.split(
        r"\n+|(?<=\S)\s+(?=(?:tema|punto)\s+\d{1,2}[\.\)])|(?<=\S)\s+(?=\d{1,2}[\.\)])",
        texto.replace("\r", "\n"),
        flags=re.IGNORECASE,
    )
    vistos: List[str] = []
    ya = set()
    for parte in partes:
        linea = " ".join(parte.split())
        linea = _PREFIJO_TEMA.sub("", linea).strip(" .-–—")
        clave = linea.casefold()
        if len(linea) < 4 or _SALTO_TEMA.match(linea) or clave in ya:
            continue
        ya.add(clave)
        vistos.append(linea[:180].rstrip())
        if len(vistos) >= 40:
            break
    return vistos


_RE_ITEM_OD = re.compile(r"^(\d+)\.\s+(.+?)\s+[-–—]\s+(.+)$")


def _linea_od(texto: str) -> str:
    return " ".join((texto or "").replace("\u00a0", " ").replace("\u2011", "-").split())


def _titulos_de_items(temas: List[Dict[str, Any]]) -> List[str]:
    titulos: List[str] = []
    ya = set()
    for tema in temas:
        titulo = _linea_od(str(tema.get("titulo") or ""))
        if not titulo:
            continue
        tipo = _linea_od(str(tema.get("tipo") or ""))
        linea = (tipo + " — " + titulo) if tipo else titulo
        clave = linea.casefold()
        if clave in ya:
            continue
        ya.add(clave)
        titulos.append(linea[:180].rstrip())
        if len(titulos) >= 40:
            break
    return titulos


def _titulos_linea_od(lineas: List[str]) -> List[str]:
    temas = []
    for linea in lineas:
        item = _RE_ITEM_OD.match(_linea_od(linea))
        if not item:
            continue
        temas.append({"tipo": item.group(2).strip(), "titulo": item.group(3).strip()})
    return _titulos_de_items(temas)


def _lineas_docx(contenido: bytes) -> List[str]:
    from docx import Document

    documento = Document(BytesIO(contenido))
    lineas: List[str] = []
    for parrafo in documento.paragraphs:
        lineas.extend(parrafo.text.replace("\r", "\n").split("\n"))
    for tabla in documento.tables:
        for fila in tabla.rows:
            vistos = set()
            for celda in fila.cells:
                texto = celda.text.strip()
                if not texto or texto in vistos:
                    continue
                vistos.add(texto)
                lineas.extend(texto.replace("\r", "\n").split("\n"))
    return lineas


def temas_desde_archivo(nombre: str, contenido: bytes) -> List[str]:
    bajo = (nombre or "").lower()
    if bajo.endswith(".doc") and not bajo.endswith(".docx"):
        raise ValueError("Guardá el Word como .docx o como PDF.")
    if len(contenido) > 4_000_000:
        raise ValueError("El archivo pesa más de 4 MB.")
    if bajo.endswith(".docx"):
        from word_docs import parsear_od_docx

        try:
            oficiales = parsear_od_docx(contenido, 0, "")
        except Exception:
            oficiales = []
        titulos = _titulos_de_items(oficiales)
        if not titulos:
            try:
                titulos = _titulos_linea_od(_lineas_docx(contenido))
            except Exception:
                titulos = []
        if titulos:
            return titulos
        temas = temas_desde_texto("\n".join(_lineas_docx(contenido)))
    elif bajo.endswith(".pdf"):
        from pypdf import PdfReader

        lector = PdfReader(BytesIO(contenido))
        if len(lector.pages) > 20:
            raise ValueError("El PDF tiene más de 20 páginas.")
        texto = "\n".join((pagina.extract_text() or "") for pagina in lector.pages)
        titulos = _titulos_linea_od(texto.split("\n"))
        temas = titulos or temas_desde_texto(texto)
    else:
        raise ValueError("Cargá un Word (.docx) o un PDF.")
    if not temas:
        raise ValueError("No encontré temas en ese archivo. Cada tema tiene que ir en un renglón, o usá el Word del orden del día.")
    return temas


@app.get("/api/aula/codigo")
def api_aula_codigo(texto: str = ""):
    try:
        codigo = aula.normalizar_codigo(texto)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"codigo": codigo, "meet_url": aula.enlace_meet(codigo)}


@app.get("/api/aula/{codigo}")
def api_aula_get(codigo: str, acta: str = "", client: str = "", ingreso: int = 0):
    try:
        return aula.obtener(codigo, acta or None, client, bool(ingreso))
    except aula.AulaError as exc:
        raise HTTPException(exc.status, exc.mensaje)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception:
        raise HTTPException(503, "La sala no responde. Reintentá en unos segundos.")


@app.post("/api/aula/{codigo}")
def api_aula_post(codigo: str, body: AulaIn):
    try:
        return aula.aplicar(codigo, body.model_dump())
    except aula.AulaError as exc:
        raise HTTPException(exc.status, exc.mensaje)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception:
        raise HTTPException(503, "La sala no responde. Reintentá en unos segundos.")


@app.post("/api/aula/{codigo}/temas")
async def api_aula_temas(
    codigo: str,
    client: str = Form(""),
    rev: str = Form(""),
    archivo: UploadFile = File(...),
):
    if len(client) < 8:
        raise HTTPException(400, "Falta la identificación de este navegador.")
    try:
        titulos = temas_desde_archivo(archivo.filename or "", await archivo.read())
        cuerpo = {"client": client, "accion": "cargar", "titulos": titulos, "reemplazar": True}
        if rev.strip():
            cuerpo["rev"] = int(rev)
        return aula.aplicar(codigo, cuerpo)
    except aula.AulaError as exc:
        raise HTTPException(exc.status, exc.mensaje)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception:
        raise HTTPException(400, "No pude leer ese archivo. Usá un Word .docx o un PDF.")


@app.post("/api/aula/{codigo}/pantalla")
async def api_aula_pantalla(codigo: str, request: Request, client: str = ""):
    cuerpo = await request.body()
    try:
        aula.guardar_pantalla(codigo, client, cuerpo)
    except aula.AulaError as exc:
        raise HTTPException(exc.status, exc.mensaje)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception:
        raise HTTPException(503, "No pude publicar la pantalla.")
    return Response(status_code=204)


@app.get("/api/aula/{codigo}/pantalla")
def api_aula_pantalla_ver(codigo: str):
    try:
        imagen = aula.leer_pantalla(codigo)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception:
        raise HTTPException(503, "La pantalla no está disponible.")
    if not imagen:
        raise HTTPException(404, "Nadie está compartiendo.")
    return Response(
        content=imagen,
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=1, s-maxage=1, stale-while-revalidate=3"},
    )


@app.post("/api/aula/{codigo}/cara")
async def api_aula_cara(codigo: str, request: Request, client: str = ""):
    cuerpo = await request.body()
    try:
        aula.guardar_cara(codigo, client, cuerpo)
    except aula.AulaError as exc:
        raise HTTPException(exc.status, exc.mensaje)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception:
        raise HTTPException(503, "No pude publicar la cámara.")
    return Response(status_code=204)


@app.get("/api/aula/{codigo}/cara")
def api_aula_cara_ver(codigo: str, client: str = ""):
    try:
        imagen = aula.leer_cara(codigo, client)
    except aula.AulaError as exc:
        raise HTTPException(exc.status, exc.mensaje)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception:
        raise HTTPException(503, "La cámara no está disponible.")
    if not imagen:
        raise HTTPException(404, "Esa cámara no está encendida.")
    return Response(
        content=imagen,
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=2, s-maxage=2, stale-while-revalidate=4"},
    )


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
    temas = _temas_ordenados(numero)
    return {
        "acta": _resumen_acta(numero),
        "temas": [_tema_publico(r, i) for i, r in enumerate(temas)],
        "orden_unidades": _obtener_orden_unidades(numero, temas),
        "puede_ordenar_unidades": True,
        "correos_orden_unidades": sorted(CORREOS_ORDEN_UNIDADES),
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
    temas = _temas_ordenados(numero)
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
    # Solo útil en Mac local. En producción la fuente de verdad es la planilla (append-only).
    if _en_produccion():
        raise HTTPException(
            403,
            "En el sitio público no se importa Word: los temas viven en la planilla y no se reemplazan.",
        )
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


@app.get("/api/actas/{numero}/orden-unidades")
def api_get_orden_unidades(numero: int):
    if numero not in ACTAS:
        raise HTTPException(404, "Acta inexistente")
    temas = _temas_acta(numero)
    unidades = _obtener_orden_unidades(numero, temas)
    # Solo unidades que realmente tienen temas, en el orden guardado + las nuevas al final.
    presentes = unidades_en_orden(temas)
    presentes_cf = {u.casefold(): u for u in presentes}
    orden = []
    vistos = set()
    for u in unidades:
        key = (u or "").casefold()
        if key in presentes_cf and key not in vistos:
            orden.append(presentes_cf[key])
            vistos.add(key)
    for u in presentes:
        key = u.casefold()
        if key not in vistos:
            orden.append(u)
            vistos.add(key)
    return {
        "ok": True,
        "unidades": orden,
        "correos_orden_unidades": sorted(CORREOS_ORDEN_UNIDADES),
    }


@app.post("/api/actas/{numero}/orden-unidades")
def api_post_orden_unidades(numero: int, body: OrdenUnidadesIn):
    if numero not in ACTAS:
        raise HTTPException(404, "Acta inexistente")
    if estado_acta(numero) != "en_curso":
        raise HTTPException(400, "Solo se reordena el Orden del Día del acta en curso.")
    email = (body.email or "").strip().lower()
    if not correo_orden_unidades(email):
        raise HTTPException(
            403,
            "Solo Secretaría (investigacion@, asistente.inv@ o vincutec@) puede cambiar el orden de unidades.",
        )
    temas = _temas_acta(numero)
    presentes = unidades_en_orden(temas)
    if not presentes:
        raise HTTPException(400, "Esta acta todavía no tiene unidades con temas.")
    presentes_cf = {u.casefold(): u for u in presentes}
    pedidas = [(u or "").strip() for u in body.unidades if (u or "").strip()]
    if not pedidas:
        raise HTTPException(400, "Falta la lista de unidades.")
    orden = []
    vistos = set()
    for u in pedidas:
        key = u.casefold()
        if key not in presentes_cf:
            raise HTTPException(400, "La unidad «{}» no tiene temas en esta acta.".format(u))
        if key in vistos:
            continue
        orden.append(presentes_cf[key])
        vistos.add(key)
    for u in presentes:
        key = u.casefold()
        if key not in vistos:
            orden.append(u)
            vistos.add(key)
    _orden_unidades[numero] = orden
    info = estado_conexion()
    if info["sheets_ok"]:
        try:
            guardar_orden_unidades(numero, orden, email)
        except Exception as exc:
            raise HTTPException(
                503,
                "No se pudo guardar el orden de unidades en la planilla. ({})".format(exc),
            ) from exc
    return {"ok": True, "unidades": orden, "guardado_por": email}


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
    if estado_acta(numero) == "cerrada":
        raise HTTPException(400, "Las actas cerradas son solo consulta. No se pueden cargar temas.")
    # Siempre leer la planilla fresca antes de validar (evita duplicar / perder de vista cargas recientes).
    if _en_produccion() or body.escribir_en_sheets:
        info = estado_conexion()
        if not info["sheets_ok"]:
            raise HTTPException(
                503,
                "No se puede cargar: la planilla no está conectada. Los temas ya guardados no se tocan.",
            )
        _cargar_hoja(force=True)
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
    # En el sitio público siempre se escribe en la planilla del Consejo (solo append).
    if _en_produccion() or body.escribir_en_sheets:
        try:
            append_tema(fila)
        except Exception as exc:
            raise HTTPException(
                503,
                "No se pudo guardar el tema en la planilla. No se borró ni modificó nada. "
                "Reintentá en un momento. ({})".format(exc),
            ) from exc
        # Incorporar al caché en memoria aunque falle un refresh completo.
        actuales = list(_cache_hoja.get("rows") or [])
        actuales.append(tema)
        _cache_hoja["rows"] = actuales
        _cache_hoja["fuente"] = "sheets"
        _cache_hoja["error"] = None
        try:
            _cargar_hoja(force=True)
        except Exception:
            pass
        return {"ok": True, "modo": "sheets", "tema": _tema_publico(tema, 0), "guardado": True}
    # Ensayo solo en Mac local de desarrollo; en Vercel nunca llega acá.
    tema["_ensayo"] = True
    guardar_ensayo_tema(tema)
    return {"ok": True, "modo": "ensayo", "tema": _tema_publico(tema, 0)}


@app.get("/api/actas/{numero}/od.docx")
def api_od(numero: int):
    if numero not in ACTAS:
        raise HTTPException(404, "Acta inexistente")
    temas = _temas_ordenados(numero)
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
    data = construir_informe(numero, nombre, aplicar_orden_od(temas, None, _obtener_orden_unidades(numero)))
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
