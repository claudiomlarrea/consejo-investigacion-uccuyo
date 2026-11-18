"""Sala compartida del aula. No toca la planilla del Consejo.

Con la cuenta de servicio, el estado vive en un archivo de Drive de esa cuenta
(no en la planilla). Sin credenciales, queda en un JSON local del servidor.
"""

from __future__ import annotations

import json
import re
import threading
import time
import uuid
from datetime import date, datetime, timezone
from typing import Any, Dict, Optional, Tuple
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

# Arco de izquierda a derecha: consejeros, presidencia, secretaría, consejeros.
VISUAL = [2, 3, 4, 5, 0, 1, 6, 7, 8, 9]
ROLES = {
    0: ("presidencia", "Presidencia"),
    1: ("secretaria", "Secretaría"),
}
ARCHIVO = "consejo-aula-salas.json"
_CODIGO = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$")
_MEET = re.compile(r"^[a-z]{3,4}-[a-z]{3,4}-[a-z]{3,4}$")
_LOCK = threading.Lock()


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


class AulaError(Exception):
    def __init__(self, status: int, mensaje: str):
        super().__init__(mensaje)
        self.status = status
        self.mensaje = mensaje


def _ahora() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _nueva(acta: int) -> Dict[str, Any]:
    if acta not in ACTAS:
        acta = sugerir_acta()
    return {
        "rev": 0,
        "acta": acta,
        "tema": 0,
        "turno": None,
        "cola": [],
        "ocupantes": {},
        "actualizado": _ahora(),
    }


def _asiento_de(sala: Dict[str, Any], client: str) -> Optional[int]:
    for clave, ocupante in sala["ocupantes"].items():
        if ocupante.get("client") == client:
            return int(clave)
    return None


def _hay_mesa(sala: Dict[str, Any]) -> bool:
    return "0" in sala["ocupantes"] or "1" in sala["ocupantes"]


def _conduce(sala: Dict[str, Any], client: str) -> bool:
    if not _hay_mesa(sala):
        return True
    return _asiento_de(sala, client) in (0, 1)


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
        raise AulaError(400, "Escribí tu nombre para sentarte.")
    if len(limpio) > 40:
        limpio = limpio[:40].rstrip()
    return limpio


def _vista(codigo: str, sala: Dict[str, Any], client: str, sync: str) -> Dict[str, Any]:
    mio = _asiento_de(sala, client)
    asientos = []
    for n in VISUAL:
        rol, etiqueta = ROLES.get(n, ("consejero", "Consejero"))
        ocupante = sala["ocupantes"].get(str(n))
        asientos.append(
            {
                "id": n,
                "rol": rol,
                "etiqueta": etiqueta,
                "nombre": ocupante.get("nombre") if ocupante else None,
                "propio": mio == n,
            }
        )
    turno = sala.get("turno")
    return {
        "codigo": codigo,
        "rev": sala["rev"],
        "sync": sync,
        "meet_url": enlace_meet(codigo),
        "acta": sala["acta"],
        "mes": ACTAS.get(sala["acta"]),
        "fecha": FECHAS.get(sala["acta"]),
        "tema": sala["tema"],
        "turno": None
        if turno is None
        else {"id": turno, "nombre": _nombre(sala, turno)},
        "cola": [{"id": n, "nombre": _nombre(sala, n)} for n in sala["cola"]],
        "asientos": asientos,
        "conduzco": _conduce(sala, client) if client else not _hay_mesa(sala),
        "sentado": mio,
    }


def _aplicar(sala: Dict[str, Any], body: Dict[str, Any]) -> None:
    client = str(body.get("client") or "")
    if len(client) < 8 or len(client) > 80:
        raise AulaError(400, "Falta la identificación de este navegador.")
    accion = str(body.get("accion") or "")
    if body.get("rev") is not None and int(body["rev"]) != sala["rev"]:
        raise AulaError(409, "Otro consejero acaba de actualizar la sala.")

    if accion == "sentarse":
        nombre = _limpiar_nombre(str(body.get("nombre") or ""))
        try:
            asiento = int(body.get("asiento"))
        except (TypeError, ValueError):
            raise AulaError(400, "Elegí un asiento.")
        if asiento not in VISUAL:
            raise AulaError(400, "Ese asiento no existe.")
        actual = sala["ocupantes"].get(str(asiento))
        if actual and actual.get("client") != client:
            raise AulaError(409, "Ese asiento acaba de ocuparse.")
        previo = _asiento_de(sala, client)
        if previo is not None and previo != asiento:
            sala["ocupantes"].pop(str(previo), None)
            _quitar_de_cola(sala, previo)
            if sala.get("turno") == previo:
                sala["turno"] = None
        sala["ocupantes"][str(asiento)] = {"nombre": nombre, "client": client}
        return

    if accion == "salir":
        previo = _asiento_de(sala, client)
        if previo is None:
            return
        sala["ocupantes"].pop(str(previo), None)
        _quitar_de_cola(sala, previo)
        if sala.get("turno") == previo:
            sala["turno"] = None
            if sala["cola"]:
                sala["turno"] = sala["cola"].pop(0)
        return

    if accion == "palabra":
        asiento = _asiento_de(sala, client)
        if asiento is None:
            raise AulaError(403, "Sentate para pedir la palabra.")
        if sala.get("turno") == asiento or asiento in sala["cola"]:
            return
        if not _hay_mesa(sala) and sala.get("turno") is None:
            sala["turno"] = asiento
            return
        sala["cola"].append(asiento)
        return

    if accion == "conceder":
        if not _conduce(sala, client):
            raise AulaError(403, "La presidencia o la secretaría dan la palabra.")
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
        return

    if accion == "ceder":
        asiento = _asiento_de(sala, client)
        if sala.get("turno") != asiento and not _conduce(sala, client):
            raise AulaError(403, "Solo quien habla, o la mesa, puede cerrar el turno.")
        sala["turno"] = sala["cola"].pop(0) if sala["cola"] else None
        return

    if accion == "acta":
        if not _conduce(sala, client):
            raise AulaError(403, "La mesa conduce el orden del día.")
        try:
            acta = int(body.get("acta"))
        except (TypeError, ValueError):
            raise AulaError(400, "Elegí un acta.")
        if acta not in ACTAS:
            raise AulaError(400, "Esa acta no existe.")
        if acta != sala["acta"]:
            sala["acta"] = acta
            sala["tema"] = 0
        return

    if accion == "ir":
        if not _conduce(sala, client):
            raise AulaError(403, "La mesa conduce el orden del día.")
        try:
            tema = int(body.get("tema"))
        except (TypeError, ValueError):
            raise AulaError(400, "Elegí un tema.")
        if tema < 0 or tema > 200:
            raise AulaError(400, "Ese tema no está en el orden del día.")
        sala["tema"] = tema
        return

    raise AulaError(400, "Acción desconocida.")


class _Almacen:
    def __init__(self) -> None:
        self._cache: Optional[Dict[str, Any]] = None
        self._cache_at = 0.0
        self._modo = ""
        self._file_id: Optional[str] = None
        self._session = None
        self._drive_hasta = 0.0

    def modo(self) -> str:
        self._elegir()
        return self._modo

    def leer(self, forzar: bool = False) -> Dict[str, Any]:
        ahora = time.time()
        if not forzar and self._cache is not None and ahora - self._cache_at < 1.0:
            return json.loads(json.dumps(self._cache))
        self._elegir()
        if self._modo == "drive":
            data = self._leer_drive()
        else:
            data = self._leer_archivo()
        if not isinstance(data, dict):
            data = {}
        self._cache = data
        self._cache_at = ahora
        return json.loads(json.dumps(data))

    def escribir(self, data: Dict[str, Any]) -> str:
        self._elegir()
        if len(data) > 40:
            orden = sorted(data.items(), key=lambda kv: (kv[1] or {}).get("actualizado") or "")
            data = dict(orden[-40:])
        if self._modo == "drive":
            try:
                self._escribir_drive(data)
            except Exception:
                self._modo = "local"
                self._drive_hasta = time.time() + 60
                self._escribir_archivo(data)
        else:
            self._escribir_archivo(data)
        self._cache = data
        self._cache_at = time.time()
        return self._modo

    def _elegir(self) -> None:
        if self._modo == "local" and time.time() < self._drive_hasta:
            return
        if self._modo == "drive" and self._session is not None:
            return
        sesion = _sesion_drive()
        if sesion is None:
            self._modo = "local"
            return
        self._session = sesion
        try:
            self._file_id = self._buscar_o_crear()
            self._modo = "drive"
        except Exception:
            self._modo = "local"
            self._drive_hasta = time.time() + 60

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


def _sala(data: Dict[str, Any], codigo: str, acta: Optional[int]) -> Tuple[Dict[str, Any], bool]:
    sala = data.get(codigo)
    if not isinstance(sala, dict) or "ocupantes" not in sala:
        sala = _nueva(acta or sugerir_acta())
        data[codigo] = sala
        return sala, True
    return sala, False


def obtener(codigo: str, acta: Optional[int] = None, client: str = "") -> Dict[str, Any]:
    codigo = normalizar_codigo(codigo)
    with _LOCK:
        data = _ALMACEN.leer()
        sala, creada = _sala(data, codigo, acta)
        modo = _ALMACEN.escribir(data) if creada else _ALMACEN.modo()
        return _vista(codigo, sala, client, modo)


def aplicar(codigo: str, body: Dict[str, Any]) -> Dict[str, Any]:
    codigo = normalizar_codigo(codigo)
    with _LOCK:
        data = _ALMACEN.leer(forzar=True)
        sala, _creada = _sala(data, codigo, None)
        _aplicar(sala, body)
        sala["rev"] = int(sala.get("rev") or 0) + 1
        sala["actualizado"] = _ahora()
        data[codigo] = sala
        modo = _ALMACEN.escribir(data)
        return _vista(codigo, sala, str(body.get("client") or ""), modo)


def manifest(origen: str) -> Dict[str, Any]:
    logo = origen.rstrip("/") + "/static/logo-uccuyo.png"
    return {
        "addOns": {
            "common": {"name": "Aula del Consejo", "logoUrl": logo},
            "meet": {
                "web": {
                    "sidePanelUrl": origen.rstrip("/") + "/aula/panel",
                    "supportsScreenSharing": False,
                    "addOnOrigins": [origen.rstrip("/")],
                    "logoUrl": logo,
                    "darkModeLogoUrl": logo,
                }
            },
        }
    }
