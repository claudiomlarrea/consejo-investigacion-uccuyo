"""Sala compartida del aula. No toca la planilla del Consejo.

Con la cuenta de servicio, el estado vive en un archivo de Drive de esa cuenta
(no en la planilla). Sin credenciales, queda en un JSON local del servidor.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

from catalogo import ACTAS, FECHAS

_MESES = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}

# Diez lugares, sin cargo fijo: la función la escribe quien se sienta.
VISUAL = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
ORGANOS = {
    "consejo-superior": "Consejo Superior",
    "consejo-directivo": "Consejo Directivo",
    "consejo-departamento": "Consejo de Departamento",
    "consejo-investigacion": "Consejo de Investigación",
    "consejo-extension": "Consejo de Extensión",
    "facultad": "Facultad",
    "escuela": "Escuela",
    "departamento": "Departamento",
    "secretaria": "Secretaría",
    "otro": "Otra unidad",
}
ARCHIVO = "consejo-aula-salas.json"
_CODIGO = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$")
_MEET = re.compile(r"^[a-z]{3,4}-[a-z]{3,4}-[a-z]{3,4}$")
CUPO = 100
PRESENCIA_SEG = 90
_CACHE_S = 2.5
_FLUSH_S = 8
_FRAME_MAX = 180_000
_CARA_MAX = 48_000
_CARAS = 24
_WRITE = threading.Lock()


def sugerir_acta(hoy: Optional[date] = None) -> int:
    hoy = hoy or date.today()
    fechas = []
    for numero, texto in FECHAS.items():
        partes = str(texto).split()
        if len(partes) < 4:
            continue
        try:
            dia = int(partes[0])
            mes = _MESES[partes[2].lower()]
            anio = int(partes[3])
        except (KeyError, ValueError):
            continue
        fechas.append((date(anio, mes, dia), numero))
    fechas.sort()
    for cuando, numero in fechas:
        if cuando >= hoy:
            return numero
    return fechas[-1][1] if fechas else max(ACTAS)


def normalizar_codigo(raw: str) -> str:
    texto = (raw or "").strip()
    bajo = texto.lower()
    marca = "meet.google.com/"
    if marca in bajo:
        texto = texto[bajo.index(marca) + len(marca) :]
    texto = texto.split("?")[0].split("#")[0].strip("/").split("/")[0].strip().lower()
    if not _CODIGO.fullmatch(texto):
        raise ValueError("El código de sala no es válido.")
    return texto


def enlace_meet(codigo: str) -> Optional[str]:
    if _MEET.fullmatch(codigo):
        return "https://meet.google.com/" + codigo
    return None


def ice_servers() -> List[Dict[str, Any]]:
    """STUN de siempre, más TURN si hay TURN_URLS en el entorno.

    TURN_URLS acepta varias URLs separadas por coma o espacio.
    TURN_USERNAME y TURN_CREDENTIAL se agregan solo si están definidas.
    """
    stun = {"urls": "stun:stun.l.google.com:19302"}
    urls = [parte.strip() for parte in re.split(r"[\s,]+", os.environ.get("TURN_URLS", "")) if parte.strip()]
    if not urls:
        return [stun]
    servidor: Dict[str, Any] = {"urls": urls[0] if len(urls) == 1 else urls}
    usuario = os.environ.get("TURN_USERNAME", "").strip()
    clave = os.environ.get("TURN_CREDENTIAL", "").strip()
    if usuario:
        servidor["username"] = usuario
    if clave:
        servidor["credential"] = clave
    return [stun, servidor]


class AulaError(Exception):
    def __init__(self, status: int, mensaje: str):
        super().__init__(mensaje)
        self.status = status
        self.mensaje = mensaje


def _ahora() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _nueva() -> Dict[str, Any]:
    return {
        "rev": 0,
        "organo": "",
        "unidad": "",
        "acta": "",
        "temas": [],
        "tema": 0,
        "turno": None,
        "cola": [],
        "ocupantes": {},
        "presentes": {},
        "pantalla": None,
        "meet": "",
        "actualizado": _ahora(),
    }


def _asiento_de(sala: Dict[str, Any], client: str) -> Optional[int]:
    for clave, ocupante in sala["ocupantes"].items():
        if ocupante.get("client") == client:
            return int(clave)
    return None


def _adentro(sala: Dict[str, Any], client: str) -> bool:
    return bool(client) and client in _vivos(sala)


def _nombre(sala: Dict[str, Any], asiento: Optional[int]) -> Optional[str]:
    if asiento is None:
        return None
    ocupante = sala["ocupantes"].get(str(asiento))
    if not ocupante:
        return None
    return ocupante.get("nombre")


def _quitar_de_cola(sala: Dict[str, Any], asiento: int) -> None:
    sala["cola"] = [n for n in sala["cola"] if n != asiento]


def _limpiar_nombre(nombre: str) -> str:
    limpio = " ".join((nombre or "").split())
    if not limpio:
        raise AulaError(400, "Escribí tu nombre.")
    if len(limpio) > 40:
        limpio = limpio[:40].rstrip()
    return limpio


def _limpiar_funcion(funcion: str) -> str:
    limpio = " ".join((funcion or "").split())
    if not limpio:
        raise AulaError(400, "Escribí tu función. Por ejemplo: Secretario de Investigación.")
    if len(limpio) > 60:
        limpio = limpio[:60].rstrip()
    return limpio


def _limpiar_acta(valor: str) -> str:
    limpio = " ".join(str(valor or "").split())
    limpio = re.sub(r"(?i)^acta\s*", "", limpio).strip()
    if not limpio or len(limpio) > 24:
        raise AulaError(400, "Escribí el número de acta de tu unidad.")
    return limpio


def _limpiar_unidad(valor: str) -> str:
    limpio = " ".join(str(valor or "").split())
    if not limpio:
        raise AulaError(400, "Escribí la unidad: facultad, escuela, departamento o secretaría.")
    if len(limpio) > 80:
        limpio = limpio[:80].rstrip()
    return limpio


def codigo_meet(raw: str) -> str:
    texto = (raw or "").strip()
    if not texto:
        return ""
    bajo = texto.lower()
    marca = "meet.google.com/"
    if marca in bajo:
        texto = texto[bajo.index(marca) + len(marca) :]
    texto = texto.split("?")[0].split("#")[0].strip("/").split("/")[0].strip().lower()
    if not _MEET.fullmatch(texto):
        raise AulaError(400, "Pegá un enlace de Meet, como https://meet.google.com/abc-defg-hij.")
    return texto


def _ahora_s() -> int:
    return int(time.time())


def _asegurar_forma(sala: Dict[str, Any]) -> None:
    sala.setdefault("presentes", {})
    sala.setdefault("pantalla", None)
    sala.setdefault("organo", "")
    sala.setdefault("unidad", "")
    sala.setdefault("temas", [])
    sala.setdefault("meet", "")
    sala.setdefault("voces", {})
    sala.setdefault("senales", [])
    sala.setdefault("senal_seq", 0)
    sala.setdefault("salidas", {})
    sala.setdefault("cerrada", False)
    if isinstance(sala.get("acta"), int):
        sala["acta"] = str(sala["acta"])
    sala.setdefault("acta", "")
    sala["acta"] = str(sala.get("acta") or "")
    if not isinstance(sala.get("temas"), list):
        sala["temas"] = []
    if sala["presentes"]:
        return
    ahora = _ahora_s()
    for ocupante in sala.get("ocupantes", {}).values():
        cid = str(ocupante.get("client") or "")
        if cid:
            sala["presentes"][cid] = {
                "nombre": ocupante.get("nombre") or "",
                "funcion": ocupante.get("funcion") or "",
                "visto": ahora,
            }


def _vivos(sala: Dict[str, Any], ahora: Optional[int] = None) -> Dict[str, Dict[str, Any]]:
    ahora = _ahora_s() if ahora is None else ahora
    _asegurar_forma(sala)
    vivos = {}
    for cid, persona in sala["presentes"].items():
        if ahora - int(persona.get("visto") or 0) <= PRESENCIA_SEG:
            vivos[cid] = persona
    return vivos


def _purgar(sala: Dict[str, Any]) -> None:
    ahora = _ahora_s()
    vivos = _vivos(sala, ahora)
    sala["presentes"] = vivos
    for clave, ocupante in list(sala["ocupantes"].items()):
        if str(ocupante.get("client") or "") not in vivos:
            asiento = int(clave)
            sala["ocupantes"].pop(clave, None)
            _quitar_de_cola(sala, asiento)
            if sala.get("turno") == asiento:
                sala["turno"] = sala["cola"].pop(0) if sala["cola"] else None
    pantalla = sala.get("pantalla") or None
    if pantalla and str(pantalla.get("client") or "") not in vivos:
        sala["pantalla"] = None
    voces = sala.get("voces") or {}
    if isinstance(voces, dict):
        sala["voces"] = {cid: info for cid, info in voces.items() if cid in vivos}
    salidas = sala.get("salidas") or {}
    if isinstance(salidas, dict):
        sala["salidas"] = {
            cid: visto
            for cid, visto in salidas.items()
            if ahora - int(visto or 0) <= 120
        }


def _rotulo(ocupante: Optional[Dict[str, Any]]) -> Optional[str]:
    if not ocupante:
        return None
    nombre = ocupante.get("nombre") or ""
    funcion = ocupante.get("funcion") or ""
    if nombre and funcion:
        return nombre + " · " + funcion
    return nombre or funcion or None


def _reflejar(sala: Dict[str, Any], client: str) -> None:
    persona = sala["presentes"].get(client) or {}
    for ocupante in sala["ocupantes"].values():
        if ocupante.get("client") == client:
            ocupante["nombre"] = persona.get("nombre") or ocupante.get("nombre") or ""
            ocupante["funcion"] = persona.get("funcion") or ""


def _marcar(sala: Dict[str, Any], client: str, nombre: str, funcion: str = "") -> None:
    _purgar(sala)
    persona = sala["presentes"].get(client)
    if persona is None:
        if len(sala["presentes"]) >= CUPO:
            raise AulaError(403, "La sala está llena (100 personas).")
        persona = {"nombre": nombre, "funcion": funcion, "visto": _ahora_s(), "camara": False}
        sala["presentes"][client] = persona
    persona["visto"] = _ahora_s()
    if nombre:
        persona["nombre"] = nombre
    if funcion:
        persona["funcion"] = funcion
    persona.setdefault("camara", False)
    persona.setdefault("funcion", "")


def _exigir_adentro(sala: Dict[str, Any], client: str) -> None:
    if not _adentro(sala, client):
        raise AulaError(403, "Entrá con tu nombre y tu función para armar la reunión.")


def _puede_armar_od(sala: Dict[str, Any], client: str) -> None:
    """El orden del día se arma antes de comenzar. Con la reunión abierta, hace falta haber entrado."""
    if _adentro(sala, client) or not sala.get("organo"):
        return
    raise AulaError(403, "Entrá con tu nombre y tu función para cambiar el orden del día.")


def _vista(codigo: str, sala: Dict[str, Any], client: str, sync: str) -> Dict[str, Any]:
    _asegurar_forma(sala)
    mio = _asiento_de(sala, client)
    asientos = []
    for n in VISUAL:
        ocupante = sala["ocupantes"].get(str(n))
        cid = str(ocupante.get("client") or "") if ocupante else ""
        cara = bool(cid and (sala["presentes"].get(cid) or {}).get("camara"))
        asientos.append(
            {
                "id": n,
                "nombre": ocupante.get("nombre") if ocupante else None,
                "funcion": (ocupante.get("funcion") or "") if ocupante else "",
                "cara": cara,
                "quien": cid if cara else "",
                "propio": mio == n,
            }
        )
    turno = sala.get("turno")
    vivos = _vivos(sala)
    roster = []
    for cid, persona in sorted(vivos.items(), key=lambda kv: (kv[1].get("nombre") or "").casefold()):
        roster.append(
            {
                "nombre": persona.get("nombre") or "Sin nombre",
                "funcion": persona.get("funcion") or "",
                "cara": bool(persona.get("camara")),
                "client": cid,
                "quien": cid if persona.get("camara") else "",
                "propio": cid == client,
            }
        )
    pantalla = sala.get("pantalla") or None
    if pantalla and str(pantalla.get("client") or "") not in vivos:
        pantalla = None
    yo = vivos.get(client) or {}
    meet = str(sala.get("meet") or "")
    temas = [str(t) for t in sala.get("temas") or [] if str(t).strip()]
    return {
        "codigo": codigo,
        "rev": sala["rev"],
        "sync": sync,
        "cupo": CUPO,
        "presentes": len(vivos),
        "adentro": client in vivos,
        "roster": roster,
        "meet": meet,
        "meet_url": enlace_meet(meet) or enlace_meet(codigo),
        "organo": sala.get("organo") or "",
        "organo_nombre": ORGANOS.get(sala.get("organo") or "", ""),
        "unidad": sala.get("unidad") or "",
        "acta": str(sala.get("acta") or ""),
        "temas": temas,
        "tema": sala["tema"],
        "turno": None
        if turno is None
        else {"id": turno, "nombre": _rotulo(sala["ocupantes"].get(str(turno)))},
        "cola": [{"id": n, "nombre": _rotulo(sala["ocupantes"].get(str(n)))} for n in sala["cola"]],
        "asientos": asientos,
        "conduzco": client in vivos,
        "sentado": mio,
        "yo": {
            "nombre": yo.get("nombre") or "",
            "funcion": yo.get("funcion") or "",
            "cara": bool(yo.get("camara")),
        },
        "pantalla": None
        if not pantalla
        else {
            "activa": True,
            "nombre": pantalla.get("nombre") or "",
            "propia": str(pantalla.get("client") or "") == client,
        },
        "voces": [
            {"client": cid, "nombre": (vivos.get(cid) or {}).get("nombre") or ""}
            for cid in (sala.get("voces") or {})
            if cid in vivos
        ],
        "senales": [
            {
                "id": int(item.get("id") or 0),
                "de": str(item.get("de") or ""),
                "para": str(item.get("para") or ""),
                "tipo": str(item.get("tipo") or ""),
                "cuerpo": str(item.get("cuerpo") or ""),
            }
            for item in (sala.get("senales") or [])
            if isinstance(item, dict) and str(item.get("para") or "") == client
        ],
        "cerrada": bool(sala.get("cerrada")),
        "ice": ice_servers(),
    }


def _normalizar_candidatos(tipo: str, cuerpo: str) -> str:
    if len(cuerpo) > 8000:
        raise AulaError(400, "La señal de audio no es válida.")
    try:
        crudo = json.loads(cuerpo)
    except (TypeError, ValueError):
        raise AulaError(400, "La señal de audio no es válida.")
    items = [crudo] if tipo == "candidate" else crudo
    if not isinstance(items, list) or not items or len(items) > 16:
        raise AulaError(400, "La señal de audio no es válida.")
    limpios = []
    for item in items:
        if not isinstance(item, dict):
            raise AulaError(400, "La señal de audio no es válida.")
        cand = str(item.get("candidate") or "")
        if not cand.startswith("candidate:") or len(cand) > 800:
            raise AulaError(400, "La señal de audio no es válida.")
        limpio: Dict[str, Any] = {"candidate": cand}
        mid = item.get("sdpMid")
        if mid not in (None, ""):
            limpio["sdpMid"] = str(mid)[:32]
        linea = item.get("sdpMLineIndex")
        if linea is not None and str(linea).lstrip("-").isdigit():
            limpio["sdpMLineIndex"] = int(linea)
        limpios.append(limpio)
    return json.dumps(limpios, ensure_ascii=False)


def _cliente(body: Dict[str, Any]) -> str:
    client = str(body.get("client") or "")
    if len(client) < 8 or len(client) > 80:
        raise AulaError(400, "Falta la identificación de este navegador.")
    return client


def _aplicar(sala: Dict[str, Any], body: Dict[str, Any]) -> bool:
    """Devuelve True si el cambio tiene que verse al instante (sube rev)."""
    client = _cliente(body)
    accion = str(body.get("accion") or "")
    _asegurar_forma(sala)
    if accion not in ("pulso", "entrar", "perfil", "pantalla", "cortar", "camara", "voz", "senal"):
        if body.get("rev") is not None and int(body["rev"]) != sala["rev"]:
            raise AulaError(409, "Otra persona acaba de actualizar la sala. Reintentá.")

    if accion == "pulso":
        if client not in _vivos(sala):
            salio = int((sala.get("salidas") or {}).get(client) or 0)
            if _ahora_s() - salio < 30:
                return False
            nombre = _limpiar_nombre(str(body.get("nombre") or "")) if body.get("nombre") else ""
            if not nombre:
                return False
            _marcar(sala, client, nombre)
            return True
        sala["presentes"][client]["visto"] = _ahora_s()
        return False

    if accion in ("entrar", "perfil"):
        if isinstance(sala.get("salidas"), dict):
            sala["salidas"].pop(client, None)
        nombre = _limpiar_nombre(str(body.get("nombre") or ""))
        funcion = _limpiar_funcion(str(body.get("funcion") or ""))
        previo = sala["presentes"].get(client)
        igual = bool(
            previo
            and client in _vivos(sala)
            and previo.get("nombre") == nombre
            and (previo.get("funcion") or "") == funcion
        )
        _marcar(sala, client, nombre, funcion)
        _reflejar(sala, client)
        return not igual

    if accion == "sentarse":
        nombre = _limpiar_nombre(str(body.get("nombre") or ""))
        funcion = _limpiar_funcion(
            str(body.get("funcion") or (sala["presentes"].get(client) or {}).get("funcion") or "")
        )
        try:
            asiento = int(body.get("asiento"))
        except (TypeError, ValueError):
            raise AulaError(400, "Elegí un asiento.")
        if asiento not in VISUAL:
            raise AulaError(400, "Ese asiento no existe.")
        _marcar(sala, client, nombre, funcion)
        actual = sala["ocupantes"].get(str(asiento))
        if actual and actual.get("client") != client:
            raise AulaError(409, "Ese asiento acaba de ocuparse.")
        previo = _asiento_de(sala, client)
        if previo is not None and previo != asiento:
            sala["ocupantes"].pop(str(previo), None)
            _quitar_de_cola(sala, previo)
            if sala.get("turno") == previo:
                sala["turno"] = None
        sala["ocupantes"][str(asiento)] = {
            "nombre": nombre,
            "funcion": funcion,
            "client": client,
            "visto": _ahora_s(),
        }
        return True

    if accion == "salir":
        previo = _asiento_de(sala, client)
        if previo is None:
            return False
        sala["ocupantes"].pop(str(previo), None)
        _quitar_de_cola(sala, previo)
        if sala.get("turno") == previo:
            sala["turno"] = None
            if sala["cola"]:
                sala["turno"] = sala["cola"].pop(0)
        return True

    if accion == "irse":
        previo = _asiento_de(sala, client)
        if previo is not None:
            sala["ocupantes"].pop(str(previo), None)
            _quitar_de_cola(sala, previo)
            if sala.get("turno") == previo:
                sala["turno"] = sala["cola"].pop(0) if sala["cola"] else None
        estaba = client in (sala.get("presentes") or {})
        sala.get("presentes", {}).pop(client, None)
        voces = sala.get("voces") or {}
        if isinstance(voces, dict):
            voces.pop(client, None)
        pantalla = sala.get("pantalla") or {}
        if str(pantalla.get("client") or "") == client:
            sala["pantalla"] = None
        sala.setdefault("salidas", {})[client] = _ahora_s()
        return estaba or previo is not None

    if accion == "camara":
        if client not in _vivos(sala):
            _marcar(
                sala,
                client,
                _limpiar_nombre(str(body.get("nombre") or "")),
                _limpiar_funcion(str(body.get("funcion") or "")),
            )
        prendida = bool(body.get("camara"))
        if prendida:
            encendidas = sum(1 for p in _vivos(sala).values() if p.get("camara"))
            ya = bool((sala["presentes"].get(client) or {}).get("camara"))
            if not ya and encendidas >= _CARAS:
                raise AulaError(403, "Hay demasiadas cámaras encendidas. Podés seguir y compartir la pantalla.")
        sala["presentes"][client]["camara"] = prendida
        sala["presentes"][client]["visto"] = _ahora_s()
        return True

    if accion == "pantalla":
        if client not in _vivos(sala):
            _marcar(
                sala,
                client,
                _limpiar_nombre(str(body.get("nombre") or "")),
                _limpiar_funcion(str(body.get("funcion") or "")),
            )
        nombre = (sala["presentes"].get(client) or {}).get("nombre") or ""
        sala["pantalla"] = {"client": client, "nombre": nombre, "visto": _ahora_s()}
        sala["presentes"][client]["visto"] = _ahora_s()
        return True

    if accion == "cortar":
        pantalla = sala.get("pantalla") or {}
        if str(pantalla.get("client") or "") == client:
            sala["pantalla"] = None
            return True
        return False

    if accion == "palabra":
        asiento = _asiento_de(sala, client)
        if asiento is None:
            raise AulaError(403, "Sentate para pedir la palabra.")
        if sala.get("turno") == asiento or asiento in sala["cola"]:
            return False
        if sala.get("turno") is None:
            sala["turno"] = asiento
            return True
        sala["cola"].append(asiento)
        return True

    if accion == "conceder":
        _exigir_adentro(sala, client)
        try:
            asiento = int(body.get("asiento"))
        except (TypeError, ValueError):
            if not sala["cola"]:
                raise AulaError(400, "Nadie pidió la palabra.")
            asiento = sala["cola"][0]
        if str(asiento) not in sala["ocupantes"]:
            raise AulaError(400, "Ese asiento está libre.")
        _quitar_de_cola(sala, asiento)
        sala["turno"] = asiento
        return True

    if accion == "ceder":
        asiento = _asiento_de(sala, client)
        if sala.get("turno") != asiento and not _adentro(sala, client):
            raise AulaError(403, "Entrá a la reunión para cerrar el turno.")
        sala["turno"] = sala["cola"].pop(0) if sala["cola"] else None
        return True

    if accion == "reunion":
        _exigir_adentro(sala, client)
        organo = str(body.get("organo") or "").strip()
        if organo not in ORGANOS:
            raise AulaError(400, "Elegí el órgano: Consejo Superior, directivo, de extensión, departamento, facultad, escuela o secretaría.")
        sala["organo"] = organo
        sala["unidad"] = _limpiar_unidad(str(body.get("unidad") or ""))
        sala["acta"] = _limpiar_acta(str(body.get("acta") or ""))
        return True

    if accion == "meet":
        _exigir_adentro(sala, client)
        sala["meet"] = codigo_meet(str(body.get("meet") or ""))
        return True

    if accion == "agregar":
        _puede_armar_od(sala, client)
        titulo = " ".join(str(body.get("titulo") or "").split())
        if not titulo:
            raise AulaError(400, "Escribí el tema.")
        if len(sala["temas"]) >= 40:
            raise AulaError(400, "El orden del día ya tiene 40 temas.")
        sala["temas"].append(titulo[:180].rstrip())
        return True

    if accion == "cargar":
        _puede_armar_od(sala, client)
        titulos = body.get("titulos") or []
        if not isinstance(titulos, list):
            raise AulaError(400, "Ese archivo no tiene temas.")
        agregados = 0
        if body.get("reemplazar"):
            sala["temas"] = []
            sala["tema"] = 0
        for titulo in titulos:
            limpio = " ".join(str(titulo).split())
            if not limpio:
                continue
            if len(sala["temas"]) >= 40:
                break
            sala["temas"].append(limpio[:180].rstrip())
            agregados += 1
        if not agregados:
            raise AulaError(400, "Ese archivo no tiene temas para cargar.")
        return True

    if accion == "quitar":
        _puede_armar_od(sala, client)
        try:
            indice = int(body.get("tema"))
        except (TypeError, ValueError):
            raise AulaError(400, "Elegí un tema.")
        if indice < 0 or indice >= len(sala["temas"]):
            raise AulaError(400, "Ese tema no está en el orden del día.")
        sala["temas"].pop(indice)
        if sala["tema"] >= len(sala["temas"]):
            sala["tema"] = max(0, len(sala["temas"]) - 1)
        return True

    if accion == "ir":
        _puede_armar_od(sala, client)
        try:
            tema = int(body.get("tema"))
        except (TypeError, ValueError):
            raise AulaError(400, "Elegí un tema.")
        if not sala["temas"] or tema < 0 or tema >= len(sala["temas"]):
            raise AulaError(400, "Ese tema no está en el orden del día.")
        sala["tema"] = tema
        return True

    if accion == "voz":
        _exigir_adentro(sala, client)
        sala.setdefault("voces", {})
        if body.get("micro"):
            persona = sala["presentes"].get(client) or {}
            sala["voces"][client] = {"nombre": persona.get("nombre") or "", "visto": _ahora_s()}
        else:
            sala["voces"].pop(client, None)
        return True

    if accion == "senal":
        _exigir_adentro(sala, client)
        senal = body.get("senal") or {}
        if not isinstance(senal, dict):
            raise AulaError(400, "La señal de audio no es válida.")
        tipo = str(senal.get("tipo") or "")
        para = str(senal.get("para") or "")
        cuerpo = str(senal.get("cuerpo") or "")
        if tipo not in ("offer", "answer", "candidate", "candidates") or len(para) < 8 or len(para) > 80:
            raise AulaError(400, "La señal de audio no es válida.")
        if tipo in ("offer", "answer"):
            if "v=0" not in cuerpo[:120] or len(cuerpo) > 12000:
                raise AulaError(400, "La señal de audio no es válida.")
        else:
            tipo = "candidates"
            cuerpo = _normalizar_candidatos(str(senal.get("tipo") or ""), cuerpo)
        sala["senal_seq"] = int(sala.get("senal_seq") or 0) + 1
        lista = sala.setdefault("senales", [])
        lista.append({
            "id": sala["senal_seq"],
            "de": client,
            "para": para,
            "tipo": tipo,
            "cuerpo": cuerpo,
        })
        if len(lista) > 80:
            del lista[:-80]
        return True

    if accion == "cerrar":
        _exigir_adentro(sala, client)
        sala["cerrada"] = True
        sala["turno"] = None
        sala["cola"] = []
        return True

    if accion == "reabrir":
        _exigir_adentro(sala, client)
        sala["cerrada"] = False
        return True

    raise AulaError(400, "Acción desconocida.")


class _Almacen:
    def __init__(self) -> None:
        self._cache: Optional[Dict[str, Any]] = None
        self._cache_at = 0.0
        self._modo = ""
        self._file_id: Optional[str] = None
        self._session = None
        self._drive_hasta = 0.0
        self._lecturas = threading.Condition()
        self._leyendo = False
        self._pulsos: Dict[str, Dict[str, int]] = {}
        self._ultimo_flush = 0.0
        self._frames: Dict[str, Tuple[bytes, float, str]] = {}
        self._frame_ids: Dict[str, str] = {}
        self._caras: Dict[str, Tuple[bytes, float]] = {}
        self._cara_ids: Dict[str, str] = {}
        self._cara_subida: Dict[str, float] = {}
        self._degradado = False

    def modo(self) -> str:
        self._elegir()
        if self._degradado and self._modo == "drive":
            return "degradado"
        return self._modo

    def leer(self, forzar: bool = False) -> Dict[str, Any]:
        with self._lecturas:
            fresco = self._cache is not None and time.time() - self._cache_at < _CACHE_S
            if not forzar and fresco:
                return json.loads(json.dumps(self._cache))
            if self._leyendo and not forzar:
                self._lecturas.wait(timeout=6)
                if self._cache is not None:
                    return json.loads(json.dumps(self._cache))
            self._leyendo = True
        try:
            self._elegir()
            if self._modo == "drive":
                data = self._leer_drive()
            elif self._modo == "hoja":
                data = self._leer_hoja()
            else:
                data = self._leer_archivo()
            if not isinstance(data, dict):
                data = {}
            self._degradado = False
        except Exception:
            self._degradado = self._modo == "drive"
            with self._lecturas:
                self._leyendo = False
                self._lecturas.notify_all()
            if self._cache is not None:
                return json.loads(json.dumps(self._cache))
            if self._modo == "drive":
                raise AulaError(503, "La sala compartida no responde. Reintentá en unos segundos.")
            return {}
        with self._lecturas:
            self._cache = data
            self._cache_at = time.time()
            self._leyendo = False
            self._lecturas.notify_all()
            return json.loads(json.dumps(data))

    def escribir(self, data: Dict[str, Any]) -> str:
        self._elegir()
        if len(data) > 40:
            orden = sorted(data.items(), key=lambda kv: (kv[1] or {}).get("actualizado") or "")
            data = dict(orden[-40:])
        if self._modo == "drive":
            ultimo = None
            for _ in range(2):
                try:
                    self._escribir_drive(data)
                    ultimo = None
                    break
                except Exception as exc:
                    ultimo = exc
                    time.sleep(0.3)
            if ultimo is not None:
                self._degradado = True
                if self._cache is None:
                    self._cache = data
                raise AulaError(503, "No pude guardar la sala. La reunión sigue en pie: reintentá.")
        elif self._modo == "hoja":
            try:
                self._escribir_hoja(data)
            except Exception:
                self._degradado = True
                if self._cache is None:
                    self._cache = data
                raise AulaError(503, "No pude guardar la sala. La reunión sigue en pie: reintentá.")
        else:
            self._escribir_archivo(data)
        with self._lecturas:
            self._cache = data
            self._cache_at = time.time()
        self._degradado = False
        return self.modo()

    def anotar_pulso(self, codigo: str, client: str, visto: int) -> None:
        self._pulsos.setdefault(codigo, {})[client] = visto
        with self._lecturas:
            sala = (self._cache or {}).get(codigo)
            if isinstance(sala, dict):
                sala.setdefault("presentes", {}).setdefault(client, {})["visto"] = visto

    def flush_pulsos(self, forzar: bool = False) -> None:
        if not self._pulsos:
            return
        if not forzar and time.time() - self._ultimo_flush < _FLUSH_S:
            return
        pendientes = self._pulsos
        self._pulsos = {}
        self._ultimo_flush = time.time()
        try:
            data = self.leer(forzar=True)
        except AulaError:
            self._pulsos = pendientes
            return
        ahora = _ahora_s()
        for codigo, vistos in pendientes.items():
            sala = data.get(codigo)
            if not isinstance(sala, dict):
                continue
            _asegurar_forma(sala)
            for cid, visto in vistos.items():
                persona = sala["presentes"].get(cid)
                if persona is not None:
                    persona["visto"] = max(int(persona.get("visto") or 0), int(visto))
            _purgar(sala)
            sala["actualizado"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
            data[codigo] = sala
        try:
            self.escribir(data)
        except AulaError:
            for codigo, vistos in pendientes.items():
                self._pulsos.setdefault(codigo, {}).update(vistos)
            return
        _ = ahora

    def guardar_frame(self, codigo: str, client: str, blob: bytes) -> None:
        if not blob.startswith(b"\xff\xd8") or len(blob) > _FRAME_MAX:
            raise AulaError(400, "La pantalla tiene que ser una imagen chica.")
        self._frames[codigo] = (blob, time.time(), client)
        self._elegir()
        if self._modo != "drive":
            return
        try:
            fid = self._frame_ids.get(codigo) or self._frame_id(codigo)
            self._frame_ids[codigo] = fid
            respuesta = self._session.patch(
                "https://www.googleapis.com/upload/drive/v3/files/{}?uploadType=media".format(fid),
                data=blob,
                headers={"Content-Type": "image/jpeg"},
                timeout=6,
            )
            respuesta.raise_for_status()
        except Exception:
            return

    def leer_frame(self, codigo: str) -> Optional[bytes]:
        memoria = self._frames.get(codigo)
        if memoria and time.time() - memoria[1] < 3:
            return memoria[0]
        self._elegir()
        if self._modo != "drive":
            return memoria[0] if memoria else None
        try:
            fid = self._frame_ids.get(codigo) or self._buscar_frame(codigo)
            if not fid:
                return memoria[0] if memoria else None
            self._frame_ids[codigo] = fid
            respuesta = self._session.get(
                "https://www.googleapis.com/drive/v3/files/{}?alt=media".format(fid),
                timeout=6,
            )
            if respuesta.status_code != 200 or not respuesta.content:
                return memoria[0] if memoria else None
            self._frames[codigo] = (respuesta.content, time.time(), "")
            return respuesta.content
        except Exception:
            return memoria[0] if memoria else None

    def guardar_cara(self, codigo: str, client: str, blob: bytes) -> None:
        if not blob.startswith(b"\xff\xd8") or len(blob) > _CARA_MAX:
            raise AulaError(400, "La cámara tiene que ser una imagen chica.")
        clave = codigo + "|" + client
        self._caras[clave] = (blob, time.time())
        self._elegir()
        if self._modo != "drive":
            return
        if time.time() - self._cara_subida.get(clave, 0) < 4:
            return
        self._cara_subida[clave] = time.time()
        try:
            fid = self._cara_ids.get(clave) or self._cara_id(codigo, client)
            self._cara_ids[clave] = fid
            respuesta = self._session.patch(
                "https://www.googleapis.com/upload/drive/v3/files/{}?uploadType=media".format(fid),
                data=blob,
                headers={"Content-Type": "image/jpeg"},
                timeout=6,
            )
            respuesta.raise_for_status()
        except Exception:
            return

    def leer_cara(self, codigo: str, client: str) -> Optional[bytes]:
        clave = codigo + "|" + client
        memoria = self._caras.get(clave)
        if memoria and time.time() - memoria[1] < 8:
            return memoria[0]
        self._elegir()
        if self._modo != "drive":
            return memoria[0] if memoria else None
        try:
            fid = self._cara_ids.get(clave) or self._buscar_cara(codigo, client)
            if not fid:
                return memoria[0] if memoria else None
            self._cara_ids[clave] = fid
            respuesta = self._session.get(
                "https://www.googleapis.com/drive/v3/files/{}?alt=media".format(fid),
                timeout=6,
            )
            if respuesta.status_code != 200 or not respuesta.content:
                return memoria[0] if memoria else None
            self._caras[clave] = (respuesta.content, time.time())
            return respuesta.content
        except Exception:
            return memoria[0] if memoria else None

    def _cara_id(self, codigo: str, client: str) -> str:
        encontrado = self._buscar_cara(codigo, client)
        if encontrado:
            return encontrado
        nombre = "consejo-aula-cara-{}-{}.jpg".format(codigo, client)
        boundary = "cara" + uuid.uuid4().hex
        meta = json.dumps({"name": nombre, "mimeType": "image/jpeg"})
        cuerpo = (
            "--{b}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{meta}\r\n"
            "--{b}\r\nContent-Type: image/jpeg\r\n\r\n"
        ).format(b=boundary, meta=meta).encode("utf-8") + b"\xff\xd8\xff\xd9" + "\r\n--{}--\r\n".format(boundary).encode("utf-8")
        creado = self._session.post(
            "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&fields=id",
            data=cuerpo,
            headers={"Content-Type": "multipart/related; boundary=" + boundary},
            timeout=6,
        )
        creado.raise_for_status()
        return creado.json()["id"]

    def _buscar_cara(self, codigo: str, client: str) -> Optional[str]:
        nombre = "consejo-aula-cara-{}-{}.jpg".format(codigo, client)
        q = quote("name = '{}' and trashed = false".format(nombre))
        respuesta = self._session.get(
            "https://www.googleapis.com/drive/v3/files?q={}&fields=files(id)&pageSize=1".format(q),
            timeout=6,
        )
        respuesta.raise_for_status()
        archivos = respuesta.json().get("files") or []
        if archivos:
            return archivos[0]["id"]
        return None

    def _frame_id(self, codigo: str) -> str:
        encontrado = self._buscar_frame(codigo)
        if encontrado:
            return encontrado
        nombre = "consejo-aula-pantalla-{}.jpg".format(codigo)
        boundary = "frame" + uuid.uuid4().hex
        meta = json.dumps({"name": nombre, "mimeType": "image/jpeg"})
        cuerpo = (
            "--{b}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{meta}\r\n"
            "--{b}\r\nContent-Type: image/jpeg\r\n\r\n"
        ).format(b=boundary, meta=meta).encode("utf-8") + b"\xff\xd8\xff\xd9" + "\r\n--{}--\r\n".format(boundary).encode("utf-8")
        creado = self._session.post(
            "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&fields=id",
            data=cuerpo,
            headers={"Content-Type": "multipart/related; boundary=" + boundary},
            timeout=6,
        )
        creado.raise_for_status()
        return creado.json()["id"]

    def _buscar_frame(self, codigo: str) -> Optional[str]:
        nombre = "consejo-aula-pantalla-{}.jpg".format(codigo)
        q = quote("name = '{}' and trashed = false".format(nombre))
        respuesta = self._session.get(
            "https://www.googleapis.com/drive/v3/files?q={}&fields=files(id)&pageSize=1".format(q),
            timeout=6,
        )
        respuesta.raise_for_status()
        archivos = respuesta.json().get("files") or []
        if archivos:
            return archivos[0]["id"]
        return None

    def _elegir(self) -> None:
        if self._modo == "drive" and self._session is not None:
            return
        if self._modo == "hoja":
            return
        if self._modo == "local" and time.time() < self._drive_hasta:
            return
        sesion = _sesion_drive()
        if sesion is not None:
            self._session = sesion
            try:
                self._file_id = self._buscar_o_crear()
                self._modo = "drive"
                return
            except Exception:
                self._session = None
                self._file_id = None
        if self._hoja_disponible():
            self._modo = "hoja"
            return
        self._modo = "local"
        self._drive_hasta = time.time() + 30

    def _hoja_aula(self, crear: bool = False):
        import gspread
        from catalogo import SHEET_ID
        from sheets_client import conectar
        import sheets_client

        ok, err = conectar()
        if not ok or sheets_client._client is None:
            raise RuntimeError(err or "sin planilla")
        libro = sheets_client._client.open_by_key(SHEET_ID)
        try:
            hoja = libro.worksheet("Aula_salas")
        except gspread.exceptions.WorksheetNotFound:
            if not crear:
                return None
            hoja = libro.add_worksheet(title="Aula_salas", rows=200, cols=3)
            hoja.update("A1:C1", [["codigo", "estado", "actualizado"]], value_input_option="RAW")
        if hoja.title != "Aula_salas":
            raise RuntimeError("La hoja del aula no es la esperada.")
        return hoja

    def _hoja_disponible(self) -> bool:
        try:
            from sheets_client import conectar
            ok, _err = conectar()
            return bool(ok)
        except Exception:
            return False

    def _leer_hoja(self) -> Dict[str, Any]:
        hoja = self._hoja_aula(crear=False)
        if hoja is None:
            return {}
        valores = hoja.get_all_values()
        data: Dict[str, Any] = {}
        for fila in valores[1:]:
            if len(fila) < 2 or not fila[0]:
                continue
            try:
                sala = json.loads(fila[1])
            except (TypeError, ValueError):
                continue
            if isinstance(sala, dict):
                sala.pop("senales", None)
                data[str(fila[0])] = sala
        return data

    def _escribir_hoja(self, data: Dict[str, Any]) -> None:
        hoja = self._hoja_aula(crear=True)
        if hoja is None or hoja.title != "Aula_salas":
            raise AulaError(503, "No pude guardar la sala.")
        cuerpo = [["codigo", "estado", "actualizado"]]
        for codigo, sala in data.items():
            if not isinstance(sala, dict):
                continue
            limpia = json.loads(json.dumps(sala))
            limpia.pop("senales", None)
            texto = json.dumps(limpia, ensure_ascii=False)
            if len(texto) > 45000:
                texto = json.dumps(
                    {
                        "rev": limpia.get("rev") or 0,
                        "organo": limpia.get("organo") or "",
                        "unidad": limpia.get("unidad") or "",
                        "acta": limpia.get("acta") or "",
                        "temas": limpia.get("temas") or [],
                        "tema": limpia.get("tema") or 0,
                        "cerrada": bool(limpia.get("cerrada")),
                        "presentes": limpia.get("presentes") or {},
                        "ocupantes": limpia.get("ocupantes") or {},
                        "turno": limpia.get("turno"),
                        "cola": limpia.get("cola") or [],
                        "meet": limpia.get("meet") or "",
                        "actualizado": limpia.get("actualizado") or "",
                    },
                    ensure_ascii=False,
                )
            cuerpo.append([codigo, texto, str(sala.get("actualizado") or "")])
        hoja.batch_clear(["A1:C200"])
        hoja.update("A1", cuerpo, value_input_option="RAW")

    def _ruta(self):
        from sheets_client import DATA_DIR

        DATA_DIR.mkdir(parents=True, exist_ok=True)
        return DATA_DIR / "aula_salas.json"

    def _leer_archivo(self) -> Dict[str, Any]:
        path = self._ruta()
        if not path.is_file():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def _escribir_archivo(self, data: Dict[str, Any]) -> None:
        path = self._ruta()
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _buscar_o_crear(self) -> str:
        q = quote("name = '{}' and trashed = false".format(ARCHIVO))
        respuesta = self._session.get(
            "https://www.googleapis.com/drive/v3/files?q={}&fields=files(id)&pageSize=1".format(q),
            timeout=8,
        )
        respuesta.raise_for_status()
        archivos = respuesta.json().get("files") or []
        if archivos:
            return archivos[0]["id"]
        boundary = "aula" + uuid.uuid4().hex
        meta = json.dumps({"name": ARCHIVO, "mimeType": "application/json"})
        cuerpo = (
            "--{b}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{meta}\r\n"
            "--{b}\r\nContent-Type: application/json\r\n\r\n{{}}\r\n"
            "--{b}--\r\n"
        ).format(b=boundary, meta=meta).encode("utf-8")
        creado = self._session.post(
            "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&fields=id",
            data=cuerpo,
            headers={"Content-Type": "multipart/related; boundary=" + boundary},
            timeout=8,
        )
        creado.raise_for_status()
        return creado.json()["id"]

    def _leer_drive(self) -> Dict[str, Any]:
        assert self._file_id
        respuesta = self._session.get(
            "https://www.googleapis.com/drive/v3/files/{}?alt=media".format(self._file_id),
            timeout=8,
        )
        if respuesta.status_code == 404:
            self._file_id = self._buscar_o_crear()
            return {}
        respuesta.raise_for_status()
        if not respuesta.text.strip():
            return {}
        data = respuesta.json()
        return data if isinstance(data, dict) else {}

    def _escribir_drive(self, data: Dict[str, Any]) -> None:
        assert self._file_id
        respuesta = self._session.patch(
            "https://www.googleapis.com/upload/drive/v3/files/{}?uploadType=media".format(self._file_id),
            data=json.dumps(data, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            timeout=8,
        )
        respuesta.raise_for_status()


_ALMACEN = _Almacen()


def _sesion_drive():
    try:
        from google.auth.transport.requests import AuthorizedSession
        from google.oauth2.service_account import Credentials

        from sheets_client import _cuenta_servicio
    except Exception:
        return None
    cuenta = _cuenta_servicio()
    if not cuenta:
        return None
    try:
        creds = Credentials.from_service_account_info(
            cuenta, scopes=["https://www.googleapis.com/auth/drive"]
        )
        return AuthorizedSession(creds)
    except Exception:
        return None


def _sala(data: Dict[str, Any], codigo: str, acta: Optional[str] = None) -> Tuple[Dict[str, Any], bool]:
    sala = data.get(codigo)
    if not isinstance(sala, dict) or "ocupantes" not in sala:
        sala = _nueva()
        if acta:
            try:
                sala["acta"] = _limpiar_acta(str(acta))
            except AulaError:
                pass
        data[codigo] = sala
        return sala, True
    _asegurar_forma(sala)
    return sala, False


def obtener(codigo: str, acta: Optional[str] = None, client: str = "") -> Dict[str, Any]:
    codigo = normalizar_codigo(codigo)
    try:
        data = _ALMACEN.leer()
    except AulaError:
        raise
    except Exception:
        data = {}
    sala, creada = _sala(data, codigo, acta)
    if creada:
        with _WRITE:
            data = _ALMACEN.leer(forzar=True)
            sala, creada = _sala(data, codigo, acta)
            if creada:
                modo = _ALMACEN.escribir(data)
            else:
                modo = _ALMACEN.modo()
    else:
        modo = _ALMACEN.modo()
    return _vista(codigo, sala, client, modo)


def aplicar(codigo: str, body: Dict[str, Any]) -> Dict[str, Any]:
    codigo = normalizar_codigo(codigo)
    accion = str(body.get("accion") or "")
    with _WRITE:
        if accion == "pulso":
            data = _ALMACEN.leer()
            sala, _creada = _sala(data, codigo, None)
            visible = _aplicar(sala, body)
            client = str(body.get("client") or "")
            if client in (sala.get("presentes") or {}):
                _ALMACEN.anotar_pulso(codigo, client, int(sala["presentes"][client].get("visto") or _ahora_s()))
            if visible:
                sala["rev"] = int(sala.get("rev") or 0) + 1
                sala["actualizado"] = _ahora()
                data[codigo] = sala
                modo = _ALMACEN.escribir(data)
            else:
                with _ALMACEN._lecturas:
                    if isinstance(_ALMACEN._cache, dict):
                        _ALMACEN._cache[codigo] = sala
                modo = _ALMACEN.modo()
            _ALMACEN.flush_pulsos()
            return _vista(codigo, sala, client, modo)
        data = _ALMACEN.leer(forzar=True)
        sala, _creada = _sala(data, codigo, None)
        visible = _aplicar(sala, body)
        if visible:
            sala["rev"] = int(sala.get("rev") or 0) + 1
            sala["actualizado"] = _ahora()
        data[codigo] = sala
        modo = _ALMACEN.escribir(data) if visible or _creada else _ALMACEN.modo()
        if not visible and not _creada:
            with _ALMACEN._lecturas:
                if isinstance(_ALMACEN._cache, dict):
                    _ALMACEN._cache[codigo] = sala
        return _vista(codigo, sala, str(body.get("client") or ""), modo)


def guardar_pantalla(codigo: str, client: str, blob: bytes) -> None:
    codigo = normalizar_codigo(codigo)
    if len(client) < 8 or len(client) > 80:
        raise AulaError(400, "Falta la identificación de este navegador.")
    data = _ALMACEN.leer()
    pantalla = (data.get(codigo) or {}).get("pantalla") if isinstance(data.get(codigo), dict) else None
    if str((pantalla or {}).get("client") or "") != client:
        data = _ALMACEN.leer(forzar=True)
        sala = data.get(codigo) if isinstance(data.get(codigo), dict) else {}
        pantalla = (sala or {}).get("pantalla") or {}
    if str((pantalla or {}).get("client") or "") != client:
        raise AulaError(403, "Solo quien está compartiendo puede enviar la pantalla.")
    _ALMACEN.guardar_frame(codigo, client, blob)


def leer_pantalla(codigo: str) -> Optional[bytes]:
    codigo = normalizar_codigo(codigo)
    return _ALMACEN.leer_frame(codigo)


def _persona_con_camara(codigo: str, client: str) -> bool:
    if len(client) < 8 or len(client) > 80:
        raise AulaError(400, "Falta la identificación de este navegador.")
    data = _ALMACEN.leer()
    sala = data.get(codigo) if isinstance(data.get(codigo), dict) else None
    persona = ((sala or {}).get("presentes") or {}).get(client) or {}
    if persona.get("camara"):
        return True
    data = _ALMACEN.leer(forzar=True)
    sala = data.get(codigo) if isinstance(data.get(codigo), dict) else None
    persona = ((sala or {}).get("presentes") or {}).get(client) or {}
    return bool(persona.get("camara"))


def guardar_cara(codigo: str, client: str, blob: bytes) -> None:
    codigo = normalizar_codigo(codigo)
    if not _persona_con_camara(codigo, client):
        raise AulaError(403, "Prendé tu cámara antes de enviar la imagen.")
    _ALMACEN.guardar_cara(codigo, client, blob)


def leer_cara(codigo: str, client: str) -> Optional[bytes]:
    codigo = normalizar_codigo(codigo)
    if len(client) < 8 or len(client) > 80:
        raise AulaError(400, "Falta la identificación de este navegador.")
    return _ALMACEN.leer_cara(codigo, client)


def manifest(origen: str) -> Dict[str, Any]:
    logo = origen.rstrip("/") + "/static/logo-uccuyo.png"
    return {
        "addOns": {
            "common": {"name": "Aula UCCuyo", "logoUrl": logo},
            "meet": {
                "web": {
                    "sidePanelUrl": origen.rstrip("/") + "/aula/panel",
                    "mainStageUrl": origen.rstrip("/") + "/aula",
                    "supportsScreenSharing": True,
                    "addOnOrigins": [origen.rstrip("/")],
                    "logoUrl": logo,
                    "darkModeLogoUrl": logo,
                }
            },
        }
    }
