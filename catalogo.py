"""Calendario, tipos y carpetas Drive: los mismos del sistema en Streamlit."""

from __future__ import annotations

from datetime import date
from typing import Dict, Optional

ACTAS: Dict[int, str] = {
    187: "Febrero",
    188: "Marzo",
    189: "Abril",
    190: "Mayo",
    191: "Junio",
    192: "Julio",
    193: "Agosto",
    194: "Septiembre",
    195: "Octubre",
    196: "Noviembre",
    197: "Diciembre",
}

FECHAS: Dict[int, str] = {
    187: "19 de Febrero 2026",
    188: "19 de Marzo 2026",
    189: "16 de Abril 2026",
    190: "21 de Mayo 2026",
    191: "18 de Junio 2026",
    192: "23 de Julio 2026",
    193: "20 de Agosto 2026",
    194: "15 de Septiembre 2026",
    195: "22 de Octubre 2026",
    196: "19 de Noviembre 2026",
    197: "10 de Diciembre 2026",
}

_MES_A_NUM = {
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

TIPOS = [
    "Proyecto de Investigación",
    "Proyecto de Cátedra",
    "Informe Final",
    "Informe de Avance",
    "Jornada de Investigación",
    "Convocatoria a Proyectos de investigación",
    "Creación de Semillero de Investigación",
    "Categorización Docente",
    "Llamado a Concurso de Becas",
    "Líneas prioritarias de investigación",
    "Otra",
]

TIPOS_CON_PUNTAJE = {
    "Proyecto de Investigación",
    "Proyecto de Cátedra",
    "Informe Final",
    "Informe de Avance",
}

TIPOS_CON_DIRECTOR = {
    "Proyecto de Investigación",
    "Proyecto de Cátedra",
    "Informe Final",
    "Informe de Avance",
    "Otra",
}

CATEGORIAS = [
    "Investigador/a Superior I",
    "Investigador/a Principal II",
    "Investigador/a Independiente III",
    "Investigador/a Adjunto/a IV",
    "Investigador/a Asistente V",
    "Becario/a de Iniciación VI",
    "Sin categorización / Externo",
]

UNIDADES = [
    "FDCSSL- Facultad de Derecho y Ciencias Sociales Sede San Luis",
    "FCMSL- Facultad de Ciencias Médicas Sede San Luis",
    "FCVSL- Facultad de Ciencias Veterinarias Sede San Luis",
    "FCEESL- Facultad de Ciencias Económicas y Empresariales Sede San Luis",
    "FBOSCO- Facultad Don Bosco",
    "FCEESJ- Facultad de Ciencias Económicas y Empresariales Sede San Juan",
    "FFyHSJ- Facultad de Filosofía y Humanidades",
    "ISDSM- Instituto Universitario Santa María",
    "ECRyPSJ- Escuela Cultura Religiosa y Pastoral",
    "FDCSSJ- Facultad de Derecho y Ciencias Sociales Sede San Juan",
    "FCMSJ- Facultad de Ciencias Médicas San Juan",
    "FEDSJ- Facultad de Educación",
    "ESEGSJ- Escuela de Seguridad",
    "FCQyTSJ- Facultad de Ciencias Químicas y Tecnológicas",
    "ISB- Instituto San Buenaventura",
    "Secretaría de Investigación",
    "Unidad de Vinculación Tecnológica",
    "OIA- Observatorio de Inteligencia Artificial",
    "Vicerrectora de Formación",
    "Departamento de Educación a Distancia",
]

MAX_UNIDADES = 5

DRIVE = {
    190: "https://drive.google.com/drive/folders/1i6amwbRjPYBqCK0gZ2k5sbcBV6mVM0ki",
    191: "https://drive.google.com/drive/folders/118VKqYfacn5eBH0dYXRvM5uAXv2M4flI",
    192: "https://drive.google.com/drive/folders/1T1GID13Wa5TXmTfibQ0HAMBtNmOvC-DH",
    193: "https://drive.google.com/drive/folders/1VVdUSebRgH2FdivZ6ZceoK30mmqtPYVs",
    194: "https://drive.google.com/drive/folders/1XkVQdpn4zNQhy2pLx0SbfTxfDQQw0eoY",
    195: "https://drive.google.com/drive/folders/1UhA4EHVhHFlfB75bkbsLGYDm4YzmVZI0",
    196: "https://drive.google.com/drive/folders/1zy8FMLNbqRUkv9EaIgpCKebf1kgy1nmv",
    197: "https://drive.google.com/drive/folders/1pRFUHhn1hxpGDvEirgOjlUf2mB2Ml0Em",
}

CVAR_DRIVE = "https://drive.google.com/drive/folders/1kLCX1LIHYpEH8W0ud-5SW39Z_GGGLXmp"
CVAR_CARGADOS = 309

SHEET_ID = "17MiyW17W7oLIwSCKjDXCoA85CwBkYqHYhDKblVN37c8"
SHEET_GID = "1058037844"
SHEET_URL = (
    "https://docs.google.com/spreadsheets/d/"
    + SHEET_ID
    + "/edit?gid="
    + SHEET_GID
    + "#gid="
    + SHEET_GID
)
TAB_HOJA2 = "Hoja 2"
TAB_PUBLICACIONES = "publicaciones_sheet"
LIBRO_NOMBRE = "Datos Consejo Investigación"


def _parse_fecha(texto: str) -> Optional[date]:
    partes = texto.strip().split()
    if len(partes) < 4:
        return None
    try:
        dia = int(partes[0])
        mes = _MES_A_NUM.get(partes[2].casefold())
        anio = int(partes[-1])
        if not mes:
            return None
        return date(anio, mes, dia)
    except ValueError:
        return None


def estado_acta(numero: int, hoy: Optional[date] = None) -> str:
    hoy = hoy or date.today()
    fechas = {n: _parse_fecha(FECHAS[n]) for n in ACTAS}
    fecha = fechas.get(numero)
    if fecha is None:
        return "proxima"
    if fecha < hoy:
        return "cerrada"
    proximas = sorted(f for f in fechas.values() if f is not None and f >= hoy)
    if proximas and fecha == proximas[0]:
        return "en_curso"
    return "proxima"


def etiqueta_estado(codigo: str) -> str:
    return {"cerrada": "Cerrada", "en_curso": "En curso", "proxima": "Próxima"}.get(
        codigo, "Próxima"
    )
