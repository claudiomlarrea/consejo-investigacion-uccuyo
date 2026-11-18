"""Orden del día del aula: se ve antes de comenzar y sigue después."""

import os
import time
import unittest
import uuid
from io import BytesIO

from docx import Document

import aula
from app import temas_desde_archivo
from word_docs import construir_od


def _local():
    aula._ALMACEN._modo = "local"
    aula._ALMACEN._drive_hasta = time.time() + 3600
    aula._ALMACEN._cache = None
    aula._ALMACEN._cache_at = 0


class AgendaTests(unittest.TestCase):
    def setUp(self):
        _local()

    def test_manifest_abre_el_escenario(self):
        origen = "https://consejo-investigacion-uccuyo.vercel.app"
        web = aula.manifest(origen)["addOns"]["meet"]["web"]
        self.assertEqual(web["sidePanelUrl"], origen + "/aula/panel")
        self.assertEqual(web["mainStageUrl"], origen + "/aula")
        self.assertEqual(web["addOnOrigins"], [origen])
        self.assertTrue(web["supportsScreenSharing"])

    def test_word_oficial_del_consejo(self):
        data = construir_od(196, [{
            "tipo": "Proyecto de Investigación",
            "titulo": "Agua y territorio en Cuyo",
            "unidad académica": "Facultad de Ciencias Económicas",
            "descripcion": "Una descripción breve del proyecto.",
            "director": "Ana Pérez",
        }])
        titulos = temas_desde_archivo("Acta_196 (3).docx", data)
        self.assertEqual(titulos, ["Proyecto de Investigación — Agua y territorio en Cuyo"])

    def test_guion_largo_y_tabla(self):
        doc = Document()
        doc.add_paragraph("1. Informe Final – Cierre del programa")
        buf = BytesIO()
        doc.save(buf)
        self.assertEqual(
            temas_desde_archivo("od.docx", buf.getvalue()),
            ["Informe Final — Cierre del programa"],
        )

        doc = Document()
        tabla = doc.add_table(rows=1, cols=1)
        tabla.cell(0, 0).text = "2. Categorización Docente — Pérez Ana"
        buf = BytesIO()
        doc.save(buf)
        self.assertEqual(
            temas_desde_archivo("tabla.docx", buf.getvalue()),
            ["Categorización Docente — Pérez Ana"],
        )

    def test_lista_simple_sigue_funcionando(self):
        doc = Document()
        doc.add_paragraph("Apertura de la reunión")
        doc.add_paragraph("Informe de la secretaría")
        buf = BytesIO()
        doc.save(buf)
        titulos = temas_desde_archivo("notas.docx", buf.getvalue())
        self.assertEqual(titulos, ["Apertura de la reunión", "Informe de la secretaría"])

    def test_temas_antes_de_entrar_y_sobreviven_al_comienzo(self):
        codigo = "prueba-od-" + uuid.uuid4().hex[:8]
        client = "cliente-prueba-0001"
        vista = aula.aplicar(codigo, {
            "client": client,
            "accion": "agregar",
            "titulo": "Tema escrito a mano",
        })
        self.assertFalse(vista["adentro"])
        self.assertIn("Tema escrito a mano", vista["temas"])
        self.assertEqual(vista["ice"][0]["urls"], "stun:stun.l.google.com:19302")

        archivo = construir_od(196, [{
            "tipo": "Informe de Avance",
            "titulo": "Seguimiento del programa",
            "unidad académica": "Facultad",
        }])
        titulos = temas_desde_archivo("Acta_196.docx", archivo)
        vista = aula.aplicar(codigo, {
            "client": client,
            "accion": "cargar",
            "titulos": titulos,
            "reemplazar": True,
            "rev": vista["rev"],
        })
        self.assertEqual(vista["temas"], ["Informe de Avance — Seguimiento del programa"])

        vista = aula.aplicar(codigo, {
            "client": client,
            "accion": "perfil",
            "nombre": "Ana Pérez",
            "funcion": "Secretaria de Investigación",
        })
        self.assertTrue(vista["adentro"])
        self.assertEqual(vista["temas"], ["Informe de Avance — Seguimiento del programa"])

        vista = aula.aplicar(codigo, {
            "client": client,
            "accion": "reunion",
            "organo": "consejo-investigacion",
            "unidad": "Facultad de Ciencias Económicas",
            "acta": "196",
            "rev": vista["rev"],
        })
        self.assertEqual(vista["organo"], "consejo-investigacion")
        self.assertEqual(vista["temas"], ["Informe de Avance — Seguimiento del programa"])
        self.assertEqual(vista["acta"], "196")

        with self.assertRaises(aula.AulaError) as ctx:
            aula.aplicar(codigo, {
                "client": "otro-cliente-0002",
                "accion": "agregar",
                "titulo": "No debería entrar",
                "rev": vista["rev"],
            })
        self.assertIn("nombre", ctx.exception.mensaje)

    def test_ice_turn_por_entorno(self):
        anterior = {clave: os.environ.get(clave) for clave in ("TURN_URLS", "TURN_USERNAME", "TURN_CREDENTIAL")}
        try:
            os.environ.pop("TURN_URLS", None)
            os.environ.pop("TURN_USERNAME", None)
            os.environ.pop("TURN_CREDENTIAL", None)
            self.assertEqual(len(aula.ice_servers()), 1)

            os.environ["TURN_URLS"] = "turn:turn.ejemplo.edu:3478?transport=udp, turns:turn.ejemplo.edu:5349"
            os.environ["TURN_USERNAME"] = "usuario-de-prueba"
            os.environ["TURN_CREDENTIAL"] = "clave-de-prueba"
            servidores = aula.ice_servers()
            self.assertEqual(servidores[0]["urls"], "stun:stun.l.google.com:19302")
            self.assertEqual(servidores[1]["urls"], [
                "turn:turn.ejemplo.edu:3478?transport=udp",
                "turns:turn.ejemplo.edu:5349",
            ])
            self.assertEqual(servidores[1]["username"], "usuario-de-prueba")
            self.assertEqual(servidores[1]["credential"], "clave-de-prueba")
        finally:
            for clave, valor in anterior.items():
                if valor is None:
                    os.environ.pop(clave, None)
                else:
                    os.environ[clave] = valor

    def test_trickle_y_salida(self):
        codigo = "prueba-audio-" + uuid.uuid4().hex[:8]
        client = "cliente-audio-0001"
        vista = aula.aplicar(codigo, {
            "client": client,
            "accion": "perfil",
            "nombre": "Ana Pérez",
            "funcion": "Secretaria",
        })
        vista = aula.aplicar(codigo, {
            "client": client,
            "accion": "senal",
            "senal": {
                "para": "cliente-audio-0002",
                "tipo": "candidates",
                "cuerpo": '[{"candidate":"candidate:1 1 UDP 1 1.2.3.4 9 typ host","sdpMid":"0","sdpMLineIndex":0}]',
            },
        })
        self.assertEqual(vista["senales"], [])
        otro = aula.obtener(codigo, client="cliente-audio-0002")
        self.assertEqual(otro["senales"][0]["tipo"], "candidates")
        self.assertIn("candidate:1", otro["senales"][0]["cuerpo"])

        vista = aula.aplicar(codigo, {"client": client, "accion": "irse", "rev": vista["rev"]})
        self.assertFalse(vista["adentro"])
        seguido = aula.aplicar(codigo, {
            "client": client,
            "accion": "pulso",
            "nombre": "Ana Pérez",
            "funcion": "Secretaria",
        })
        self.assertFalse(seguido["adentro"])


    def test_acta_opcional_y_recarga_limpia(self):
        codigo = "limpia-" + uuid.uuid4().hex[:8]
        client = "cliente-limpia-0001"
        vista = aula.aplicar(codigo, {
            "client": client,
            "accion": "agregar",
            "titulo": "Tema de un borrador viejo",
        })
        self.assertEqual(vista["temas"], ["Tema de un borrador viejo"])
        self.assertEqual(aula.obtener(codigo, client=client)["temas"], ["Tema de un borrador viejo"])
        limpia = aula.obtener(codigo, client=client, ingreso=True)
        self.assertEqual(limpia["temas"], [])
        self.assertEqual(limpia["organo"], "")

        otro = "cliente-limpia-0002"
        aula.aplicar(codigo, {
            "client": otro,
            "accion": "perfil",
            "nombre": "Beto Ruiz",
            "funcion": "Decano",
        })
        aula.aplicar(codigo, {
            "client": otro,
            "accion": "agregar",
            "titulo": "Tema compartido",
            "rev": aula.obtener(codigo, client=otro)["rev"],
        })
        conservado = aula.obtener(codigo, client=client, ingreso=True)
        self.assertEqual(conservado["temas"], ["Tema compartido"])

        vista = aula.aplicar(codigo, {
            "client": otro,
            "accion": "reunion",
            "organo": "facultad",
            "unidad": "Facultad de Ingeniería",
            "acta": "",
            "rev": conservado["rev"],
        })
        self.assertEqual(vista["acta"], "")
        self.assertEqual(vista["organo"], "facultad")
        self.assertFalse(vista["cerrada"])
        en_curso = aula.obtener(codigo, client=otro, ingreso=True)
        self.assertEqual(en_curso["temas"], ["Tema compartido"])
        self.assertEqual(en_curso["organo"], "facultad")

        cerrada = aula.aplicar(codigo, {
            "client": otro,
            "accion": "cerrar",
            "rev": en_curso["rev"],
        })
        self.assertTrue(cerrada["cerrada"])
        self.assertEqual(aula.obtener(codigo, client=client, ingreso=True)["temas"], ["Tema compartido"])
        aula.aplicar(codigo, {"client": otro, "accion": "irse", "rev": cerrada["rev"]})
        vacia = aula.obtener(codigo, client=client, ingreso=True)
        self.assertEqual(vacia["temas"], [])
        self.assertEqual(vacia["organo"], "")
        self.assertFalse(vacia["cerrada"])

    def test_presencia_vencida_no_conserva_el_borrador(self):
        codigo = "vieja-" + uuid.uuid4().hex[:8]
        viejo = "cliente-viejo-0001"
        aula.aplicar(codigo, {
            "client": viejo,
            "accion": "perfil",
            "nombre": "Viejo",
            "funcion": "Ayudante",
        })
        rev = aula.obtener(codigo, client=viejo)["rev"]
        aula.aplicar(codigo, {
            "client": viejo,
            "accion": "agregar",
            "titulo": "Tema viejo",
            "rev": rev,
        })
        data = aula._ALMACEN.leer(forzar=True)
        data[codigo]["presentes"][viejo]["visto"] = aula._ahora_s() - 80
        aula._ALMACEN.escribir(data)
        aula._ALMACEN._cache = None
        limpio = aula.obtener(codigo, client="cliente-nuevo-0002", ingreso=True)
        self.assertEqual(limpio["temas"], [])
        self.assertEqual(limpio["presentes"], 0)

    def test_la_mano_se_levanta_y_se_baja(self):
        codigo = "mano-" + uuid.uuid4().hex[:8]
        client = "cliente-mano-0001"
        vista = aula.aplicar(codigo, {
            "client": client,
            "accion": "perfil",
            "nombre": "Ana Pérez",
            "funcion": "Secretaria",
        })
        vista = aula.aplicar(codigo, {
            "client": client,
            "accion": "sentarse",
            "asiento": 0,
            "nombre": "Ana Pérez",
            "funcion": "Secretaria",
            "rev": vista["rev"],
        })
        vista = aula.aplicar(codigo, {
            "client": client,
            "accion": "palabra",
            "rev": vista["rev"],
        })
        self.assertEqual([p["id"] for p in vista["cola"]], [0])
        self.assertIsNone(vista["turno"])
        vista = aula.aplicar(codigo, {
            "client": client,
            "accion": "palabra",
            "rev": vista["rev"],
        })
        self.assertEqual(vista["cola"], [])
        vista = aula.aplicar(codigo, {
            "client": client,
            "accion": "palabra",
            "rev": vista["rev"],
        })
        vista = aula.aplicar(codigo, {
            "client": client,
            "accion": "conceder",
            "rev": vista["rev"],
        })
        self.assertEqual(vista["turno"]["id"], 0)
        self.assertEqual(vista["cola"], [])
        vista = aula.aplicar(codigo, {
            "client": client,
            "accion": "agregar",
            "titulo": "Borrador para descartar",
            "rev": vista["rev"],
        })
        vista = aula.aplicar(codigo, {
            "client": client,
            "accion": "descartar",
            "rev": vista["rev"],
        })
        self.assertEqual(vista["temas"], [])
        self.assertEqual(vista["organo"], "")

    def test_dos_personas_entran_juntas(self):
        import threading

        codigo = "conc-" + uuid.uuid4().hex[:8]
        errores = []

        def entrar(n):
            try:
                aula.aplicar(codigo, {
                    "client": "cliente-conc-{:04d}".format(n),
                    "accion": "perfil",
                    "nombre": "Persona {}".format(n),
                    "funcion": "Rol",
                })
            except Exception as exc:
                errores.append(exc)

        hilos = [threading.Thread(target=entrar, args=(n,)) for n in range(3)]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join()
        self.assertEqual(errores, [])
        vista = aula.obtener(codigo, client="cliente-conc-0000")
        self.assertEqual(vista["presentes"], 3)

    def test_reintenta_si_la_escritura_choca(self):
        codigo = "choque-" + uuid.uuid4().hex[:8]
        real = aula._ALMACEN.escribir
        llamadas = {"n": 0}

        def choca_una_vez(data, marca=None):
            llamadas["n"] += 1
            if llamadas["n"] == 1:
                raise aula._Conflicto()
            return real(data, marca)

        aula._ALMACEN.escribir = choca_una_vez
        try:
            vista = aula.aplicar(codigo, {
                "client": "cliente-choque-0001",
                "accion": "perfil",
                "nombre": "Ana Pérez",
                "funcion": "Secretaria",
            })
        finally:
            aula._ALMACEN.escribir = real
        self.assertGreaterEqual(llamadas["n"], 2)
        self.assertTrue(vista["adentro"])
        self.assertEqual(vista["presentes"], 1)

    def test_fusion_no_pisa_a_la_otra_persona(self):
        original = {"presentes": {}, "ocupantes": {}, "temas": [], "rev": 1, "organo": "", "cerrada": False, "cola": [], "turno": None}
        editada = {
            "presentes": {"ana": {"nombre": "Ana", "funcion": "Sec", "visto": 10, "camara": False}},
            "ocupantes": {},
            "temas": [],
            "rev": 2,
            "organo": "",
            "cerrada": False,
            "cola": [],
            "turno": None,
        }
        fresca = {
            "presentes": {"beto": {"nombre": "Beto", "funcion": "Decano", "visto": 12, "camara": True}},
            "ocupantes": {"1": {"nombre": "Beto", "funcion": "Decano", "client": "beto", "visto": 12}},
            "temas": ["Tema de Beto"],
            "rev": 3,
            "organo": "",
            "cerrada": False,
            "cola": [],
            "turno": None,
        }
        sala = aula._fusionar_sala(original, editada, fresca)
        self.assertIn("ana", sala["presentes"])
        self.assertIn("beto", sala["presentes"])
        self.assertEqual(sala["temas"], ["Tema de Beto"])


if __name__ == "__main__":
    unittest.main()
