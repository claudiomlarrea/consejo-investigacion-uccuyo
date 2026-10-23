"""Lee y escribe la misma planilla Datos Consejo Investigación, sin Streamlit."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from catalogo import LIBRO_NOMBRE, SHEET_ID, TAB_HOJA2, TAB_PUBLICACIONES

ROOT = Path(__file__).resolve().parent
PARENT = ROOT.parent
DATA_DIR = ROOT / "data"
ENSAYO_PATH = DATA_DIR / "ensayos.json"
CACHE_PATH = DATA_DIR / "planilla_cache.json"

_SCOPES = (
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
)

_client = None
_error = None
_secret_path = None


def _candidatos_secrets() -> List[Path]:
    env = os.environ.get("CONSEJO_SECRETS")
    extra = [Path(env)] if env else []
    return extra + [
        ROOT / "secrets.toml",
        PARENT / ".streamlit" / "secrets.toml",
        Path.home() / ".consejo-investigacion" / "secrets.toml",
    ]


def _cargar_toml(path: Path) -> Dict[str, Any]:
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib  # type: ignore
    with path.open("rb") as fh:
        return tomllib.load(fh)


def _cuenta_servicio() -> Optional[Dict[str, Any]]:
    global _secret_path
    try:
        import streamlit as st

        cuenta = st.secrets.get("gcp_service_account")
        if cuenta:
            _secret_path = "streamlit.secrets"
            return dict(cuenta)
    except Exception:
        pass
    env_json = os.environ.get("GOOGLE_SA_JSON")
    if env_json:
        try:
            data = json.loads(env_json)
            _secret_path = "GOOGLE_SA_JSON"
            return data
        except json.JSONDecodeError:
            pass
    env_file = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if env_file and Path(env_file).is_file():
        _secret_path = env_file
        with open(env_file, "r", encoding="utf-8") as fh:
            return json.load(fh)
    for path in _candidatos_secrets():
        if path.is_file():
            data = _cargar_toml(path)
            cuenta = data.get("gcp_service_account")
            if cuenta:
                _secret_path = str(path)
                return cuenta
    return None


def reset_conexion() -> None:
    global _client, _error, _secret_path
    _client = None
    _error = None
    _secret_path = None


def guardar_cuenta_servicio(cuenta: Dict[str, Any]) -> Path:
    """Guarda la cuenta de servicio solo en esta Mac. No se publica."""
    if not isinstance(cuenta, dict) or cuenta.get("type") != "service_account":
        raise ValueError("El JSON no es una cuenta de servicio de Google.")
    if not cuenta.get("private_key") or not cuenta.get("client_email"):
        raise ValueError("Faltan private_key o client_email.")
    path = ROOT / "secrets.toml"
    lineas = ["# Solo en esta Mac. El prototipo solo agrega filas; no borra la planilla.\n", "[gcp_service_account]\n"]
    for clave, valor in cuenta.items():
        if clave == "private_key":
            pk = str(valor).replace("\r\n", "\n")
            lineas.append('private_key = """' + pk + '"""\n')
        else:
            texto = str(valor).replace("\\", "\\\\").replace('"', '\\"')
            lineas.append('{} = "{}"\n'.format(clave, texto))
    path.write_text("".join(lineas), encoding="utf-8")
    reset_conexion()
    return path


def conectar() -> Tuple[bool, Optional[str]]:
    global _client, _error
    if _client is not None:
        return True, None
    cuenta = _cuenta_servicio()
    if not cuenta:
        _error = (
            "No hay credenciales. Copiá .streamlit/secrets.toml del sistema actual "
            "a prototipo/secrets.toml, o definí GOOGLE_APPLICATION_CREDENTIALS."
        )
        return False, _error
    try:
        from google.oauth2.service_account import Credentials
        import gspread

        creds = Credentials.from_service_account_info(cuenta, scopes=list(_SCOPES))
        _client = gspread.authorize(creds)
        _error = None
        return True, None
    except Exception as exc:
        _error = str(exc)
        _client = None
        return False, _error


def estado_conexion() -> Dict[str, Any]:
    ok, err = conectar()
    return {
        "sheets_ok": ok,
        "error": err,
        "secret_path": _secret_path,
        "sheet_id": SHEET_ID,
        "libro": LIBRO_NOMBRE,
    }


def _hoja2():
    ok, err = conectar()
    if not ok:
        raise RuntimeError(err)
    return _client.open_by_key(SHEET_ID).worksheet(TAB_HOJA2)


def _publicaciones():
    ok, err = conectar()
    if not ok:
        raise RuntimeError(err)
    return _client.open(LIBRO_NOMBRE).worksheet(TAB_PUBLICACIONES)


def leer_hoja2() -> List[Dict[str, Any]]:
    return _hoja2().get_all_records()


def append_tema(fila: List[Any]) -> None:
    from gspread.utils import InsertDataOption, ValueInputOption

    _hoja2().append_row(
        fila,
        value_input_option=ValueInputOption.user_entered,
        insert_data_option=InsertDataOption.insert_rows,
    )


def append_publicacion(fila: List[Any]) -> None:
    _publicaciones().append_row(fila)


def _ensayo_vacio() -> Dict[str, Any]:
    return {"temas": [], "publicaciones": []}


def leer_ensayos() -> Dict[str, Any]:
    if not ENSAYO_PATH.is_file():
        return _ensayo_vacio()
    try:
        data = json.loads(ENSAYO_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _ensayo_vacio()
    data.setdefault("temas", [])
    data.setdefault("publicaciones", [])
    return data


def leer_cache_planilla() -> List[Dict[str, Any]]:
    if not CACHE_PATH.is_file():
        return []
    try:
        data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(data, list):
        return data
    return list(data.get("temas") or [])


def _num_acta_cache(valor: Any) -> Optional[int]:
    if valor is None or valor == "":
        return None
    try:
        return int(float(str(valor).strip().replace(",", ".")))
    except (TypeError, ValueError):
        return None


def guardar_cache_temas(nuevos: List[Dict[str, Any]], reemplazar_acta: Optional[int] = None) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    actuales = leer_cache_planilla()
    if reemplazar_acta is not None:
        actuales = [r for r in actuales if _num_acta_cache(r.get("numero_acta")) != reemplazar_acta]
    actuales.extend(nuevos)
    CACHE_PATH.write_text(json.dumps(actuales, ensure_ascii=False, indent=2), encoding="utf-8")


def guardar_ensayo_tema(tema: Dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    data = leer_ensayos()
    data["temas"].append(tema)
    ENSAYO_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def guardar_ensayo_publicacion(fila: Dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    data = leer_ensayos()
    data["publicaciones"].append(fila)
    ENSAYO_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
