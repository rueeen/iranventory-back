import hashlib
import shutil
import subprocess
from copy import copy
from datetime import date, datetime, timedelta
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from zipfile import ZipFile

import pytest
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt
from model_bakery import baker
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Protection, Side
from openpyxl.worksheet.datavalidation import DataValidation
from rest_framework.test import APIClient

from apps.catalogo.models import TipoEquipo
from apps.cuentas.models import Usuario
from apps.documentos.excel import copiar_estilo_fila, extender_validacion
from apps.documentos.pdf import convertir_a_pdf
from apps.documentos.plantillas import ruta_plantilla
from apps.documentos.word import agregar_fila_como, escribir_celda
from apps.inventario.models import Unidad
from apps.mantencion.ficha_docx import generar_ficha_docx
from apps.mantencion.importacion_plan import importar_plan
from apps.mantencion.models import PlanMantencion

pytestmark = pytest.mark.django_db


@pytest.fixture
def unidad():
    return baker.make(
        Unidad,
        tipo_equipo=baker.make(
            TipoEquipo,
            nombre="Equipo ficticio",
            especificacion="Especificación ficticia",
        ),
        codigo_activo="UTC000999999",
        codigo_peoplesoft="180000999999",
    )


@pytest.fixture
def cliente():
    cliente = APIClient()
    cliente.force_authenticate(user=baker.make(Usuario, rol="PANOLERO"))
    return cliente


@pytest.fixture
def ficha():
    return {
        "nombre_equipo": "Equipo ficticio",
        "tipo_equipo": "Categoría ficticia",
        "area": "Área de prueba",
        "sede": "Sede de prueba",
        "fecha_solicitud_mantenimiento": "2025-07-01",
        "marca": "Marca ficticia",
        "modelo": "Modelo 1",
        "ubicacion": "Taller de prueba",
        "serie": "SER-001",
        "codigo_inventario": "UTC000999999",
        "codigo_peoplesoft": "180000999999",
        "codigo_proyecto": "PROY-01",
        "periodo_calibracion": "Anual",
        "registros": [
            {
                "fecha_realizacion": "2025-08-02",
                "tipo": "CORRECTIVO",
                "descripcion": "Reparación ficticia",
                "empresa": "Empresa ficticia",
                "orden_compra": "OC-002",
                "costo": "12345.00",
                "realizado_por": "Colaborador ficticio",
            },
            {
                "fecha_realizacion": "2025-08-01",
                "tipo": "PREVENTIVO",
                "descripcion": "Limpieza ficticia",
                "empresa": "Equipo interno",
                "orden_compra": "",
                "costo": "0.00",
                "realizado_por": "Primer colaborador",
            },
        ],
    }


def test_plan_conserva_plantilla_logo_y_validacion(cliente, unidad):
    ruta = ruta_plantilla("plan_mantencion.xlsx")
    original = ruta.read_bytes()
    for indice in range(45):
        baker.make(
            PlanMantencion,
            unidad=unidad,
            actividad=f"Actividad ficticia {indice}",
            fecha_ultima_mantencion=date(2025, 8, 1),
            prioridad="MEDIA",
        )
    res = cliente.get("/api/planes-mantencion/exportar/")
    assert res.status_code == 200
    with ZipFile(BytesIO(res.content)) as salida, ZipFile(BytesIO(original)) as entrada:
        assert salida.read("xl/media/image1.png") == entrada.read("xl/media/image1.png")
    libro = load_workbook(BytesIO(res.content))
    plantilla = load_workbook(BytesIO(original))
    hoja, base = libro["MANTENCIÓN DE EQUIPOS"], plantilla["MANTENCIÓN DE EQUIPOS"]
    assert hoja["A2"].value == base["A2"].value
    assert list(hoja.merged_cells.ranges) == list(base.merged_cells.ranges)
    for columna in range(1, 9):
        assert hoja.cell(5, columna).value == base.cell(5, columna).value
        assert hoja.cell(5, columna)._style == base.cell(5, columna)._style
    assert [hoja.cell(fila, 11).value for fila in range(6, 9)] == [
        "Baja",
        "Media",
        "Alta",
    ]
    assert hoja["A6"].value == "UTC000999999\n180000999999"
    assert hoja["A6"].alignment.wrap_text
    assert hoja["F6"].value == "Media"
    assert isinstance(hoja["G6"].value, (date, datetime))
    assert hoja["G6"].number_format == "DD/MM/YYYY"
    assert copy(hoja["A46"].border) == copy(hoja["A6"].border)
    assert hoja.row_dimensions[46].height == hoja.row_dimensions[6].height
    assert copy(hoja["H50"].border) == copy(hoja["H6"].border)
    assert "F6:F50" in str(hoja.data_validations.dataValidation[0].sqref)
    assert hoja.data_validations.dataValidation[0].formula1 == "$K$6:$K$8"
    assert hoja.page_setup.fitToWidth == 1
    assert hoja.page_setup.fitToHeight == 0
    assert hoja.sheet_properties.pageSetUpPr.fitToPage
    assert hoja.page_setup.orientation == "landscape"
    assert hoja.print_title_rows == "$5:$5"
    assert "$A$1:$H$50" in hoja.print_area
    for columna in "ABCDEFGHK":
        assert (
            hoja.column_dimensions[columna].width
            == base.column_dimensions[columna].width
        )
    libro.close()
    plantilla.close()
    assert (
        hashlib.sha256(ruta.read_bytes()).digest() == hashlib.sha256(original).digest()
    )
    resultado = importar_plan(BytesIO(res.content), simular=False)
    assert resultado.planes_creados == 0
    assert resultado.planes_actualizados == 45
    assert resultado.advertencias == []


def test_plan_filtrado_y_textos_se_guardan_como_datos(cliente, unidad):
    baker.make(PlanMantencion, unidad=unidad, actividad="=1+1", prioridad="BAJA")
    baker.make(PlanMantencion, unidad=unidad, actividad="No exportar", prioridad="ALTA")
    res = cliente.get("/api/planes-mantencion/exportar/?prioridad=BAJA")
    hoja = load_workbook(BytesIO(res.content)).active
    assert hoja["D6"].value == "=1+1"
    assert hoja["D6"].data_type == "s"
    assert hoja["D7"].value is None
    assert [hoja.cell(f, 11).value for f in range(6, 9)] == ["Baja", "Media", "Alta"]


def test_ficha_mapa_formato_y_firma(ficha):
    ruta = ruta_plantilla("ficha_mantencion.docx")
    original = ruta.read_bytes()
    documento = Document(BytesIO(generar_ficha_docx(ficha)))
    base = Document(BytesIO(original))
    assert documento.tables[0]._tbl.xml == base.tables[0]._tbl.xml
    assert [documento.tables[1].cell(f, 1).text for f in range(4)] == [
        "Equipo ficticio",
        "Categoría ficticia",
        "Área de prueba",
        "01/07/2025",
    ]
    assert [c.text for c in documento.tables[2].rows[0].cells] == [
        "MARCA",
        "Marca ficticia",
        "MODELO",
        "Modelo 1",
    ]
    assert documento.tables[2].cell(1, 1).text == "Taller de prueba"
    assert documento.tables[2].cell(1, 3).text == "SER-001"
    assert documento.tables[3].cell(0, 1).text == "UTC000999999\n180000999999"
    assert documento.tables[3].cell(0, 3).text == "PROY-01"
    assert documento.tables[3].cell(1, 1).text == "Anual"
    tabla = documento.tables[4]
    assert len(tabla.rows) == 10
    for fila in range(3):
        assert tabla.rows[fila]._tr.xml == base.tables[4].rows[fila]._tr.xml
    assert [c.text for c in tabla.rows[3].cells] == [
        "01/08/2025",
        "",
        "Limpieza ficticia",
        "Equipo interno",
        "",
        "",
    ]
    assert [c.text for c in tabla.rows[4].cells] == [
        "",
        "02/08/2025",
        "Reparación ficticia",
        "Empresa ficticia",
        "OC-002",
        "$12.345",
    ]
    assert all(not c.text for fila in tabla.rows[5:] for c in fila.cells)
    parrafos = [p.text for p in documento.paragraphs]
    linea = parrafos.index("___________________________")
    assert parrafos[linea - 1] == "Colaborador ficticio"
    assert documento.paragraphs[linea - 1].alignment == WD_ALIGN_PARAGRAPH.CENTER
    assert parrafos[linea + 1] == "Nombre – Firma Colaborador"
    assert ruta.read_bytes() == original


def test_ficha_extiende_filas(ficha):
    ficha["registros"] = [
        {
            **ficha["registros"][0],
            "fecha_realizacion": str(date(2025, 8, 1) + timedelta(days=i)),
        }
        for i in range(10)
    ]
    documento = Document(BytesIO(generar_ficha_docx(ficha)))
    tabla = documento.tables[4]
    assert len(tabla.rows) == 13
    assert tabla.cell(12, 1).text == "10/08/2025"
    assert tabla.cell(12, 2).text == "Reparación ficticia"
    assert tabla.cell(12, 2)._tc.tcPr.xml == tabla.cell(9, 2)._tc.tcPr.xml


def test_ficha_vacia_y_codigo_unico(ficha):
    ficha["registros"] = []
    ficha["codigo_peoplesoft"] = None
    ficha["fecha_solicitud_mantenimiento"] = None
    documento = Document(BytesIO(generar_ficha_docx(ficha)))
    assert documento.tables[3].cell(0, 1).text == "UTC000999999"
    assert documento.tables[1].cell(3, 1).text == ""
    assert all(not c.text for r in documento.tables[4].rows[3:] for c in r.cells)
    assert "Colaborador ficticio" not in [p.text for p in documento.paragraphs]


def test_escribir_celda_conserva_formato_y_multilinea():
    documento = Document()
    celda = documento.add_table(rows=1, cols=1).cell(0, 0)
    parrafo = celda.paragraphs[0]
    parrafo.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = parrafo.add_run("Antes")
    run.font.name, run.font.size, run.bold = "Arial", Pt(11), True
    celda.add_paragraph("Texto a eliminar")
    escribir_celda(celda, "Uno\nDos")
    assert celda.text == "Uno\nDos"
    for parrafo in celda.paragraphs:
        assert parrafo.alignment == WD_ALIGN_PARAGRAPH.RIGHT
        assert parrafo.runs[0].font.name == "Arial"
        assert parrafo.runs[0].font.size == Pt(11)
        assert parrafo.runs[0].bold
    otra = documento.add_table(rows=1, cols=1).cell(0, 0)
    escribir_celda(otra, "Sin runs originales")
    assert otra.paragraphs[0].runs[0].font.name == "Calibri"
    assert otra.paragraphs[0].runs[0].font.size == Pt(8)


def test_agregar_fila_conserva_original_y_formato():
    documento = Document()
    tabla = documento.add_table(rows=1, cols=2)
    modelo = tabla.rows[0]
    escribir_celda(modelo.cells[0], "Original")
    original = modelo._tr.xml
    nueva = agregar_fila_como(tabla, modelo)
    assert modelo._tr.xml == original
    assert len(tabla.rows) == 2
    assert all(not c.text for c in nueva.cells)
    assert nueva.cells[0]._tc.tcPr.xml == modelo.cells[0]._tc.tcPr.xml


def test_helpers_excel_copian_todos_los_estilos_y_preservan_otros_rangos():
    hoja = Workbook().active
    celda = hoja["F6"]
    celda.font = Font(name="Calibri", bold=True)
    celda.border = Border(bottom=Side(style="thin"))
    celda.fill = PatternFill("solid", fgColor="FF0000")
    celda.alignment = Alignment(wrap_text=True)
    celda.number_format = "0.00"
    celda.protection = Protection(locked=False)
    hoja.row_dimensions[6].height = 32
    copiar_estilo_fila(hoja, 6, 41, range(1, 9))
    assert hoja["F41"]._style == celda._style
    assert hoja.row_dimensions[41].height == 32
    validacion = DataValidation(type="list", formula1="$K$6:$K$8")
    validacion.sqref = "F6:F40 B2:B3"
    hoja.add_data_validation(validacion)
    extender_validacion(hoja, "F6:F40", 50)
    assert set(str(r) for r in validacion.sqref.ranges) == {"F6:F50", "B2:B3"}
    extender_validacion(hoja, "F6:F40", 10)
    assert "F6:F50" in str(validacion.sqref)
    hoja["F41"].font = copy(Font(bold=False))
    assert hoja["F6"].font.bold


def test_endpoint_json_igual_y_word_independiente_de_pdf(cliente, unidad, settings):
    url = f"/api/unidades/{unidad.pk}/ficha-mantencion/"
    settings.DOCUMENTOS_PDF = False
    original = cliente.get(url)
    explicito = cliente.get(url, {"formato": "json"})
    assert original.status_code == explicito.status_code == 200
    assert original.data == explicito.data
    res = cliente.get(url, {"formato": "docx"})
    assert res.status_code == 200
    assert (
        res["Content-Type"]
        == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert "Ficha_Mantencion_UTC000999999.docx" in res["Content-Disposition"]
    assert Document(BytesIO(res.content)).tables[1].cell(0, 1).text == "Equipo ficticio"
    unidad.codigo_activo = None
    unidad.save()
    assert (
        f"Ficha_Mantencion_{unidad.pk}.docx"
        in cliente.get(url, {"formato": "docx"})["Content-Disposition"]
    )
    assert cliente.get(url, {"formato": "otro"}).status_code == 400


def test_pdf_endpoint_y_argumentos_separados(cliente, unidad, settings):
    settings.DOCUMENTOS_PDF = True
    settings.LIBREOFFICE_BIN = "soffice"
    perfiles = []

    def ejecutar(args, **kwargs):
        indice = args.index("--convert-to")
        assert args[indice + 1] == "pdf"
        assert kwargs["timeout"] == settings.LIBREOFFICE_TIMEOUT
        assert kwargs["check"] is False
        assert kwargs["capture_output"] is True
        assert kwargs["env"]["HOME"] == str(Path(args[-1]).parent)
        perfiles.append(next(a for a in args if a.startswith("-env:UserInstallation=")))
        Path(args[-1]).with_suffix(".pdf").write_bytes(b"%PDF-1.4\nFicticio")
        return SimpleNamespace(returncode=0, stderr=b"")

    with (
        patch("apps.documentos.pdf.shutil.which", return_value="/usr/bin/soffice"),
        patch("apps.documentos.pdf.subprocess.run", side_effect=ejecutar),
    ):
        for _ in range(2):
            res = cliente.get(
                f"/api/unidades/{unidad.pk}/ficha-mantencion/?formato=pdf"
            )
            assert res.status_code == 200
            assert res["Content-Type"] == "application/pdf"
            assert res.content.startswith(b"%PDF")
            assert "Ficha_Mantencion_UTC000999999.pdf" in res["Content-Disposition"]
    assert len(set(perfiles)) == 2
    for perfil in perfiles:
        assert not Path(perfil.split("file://", 1)[1]).exists()


@pytest.mark.parametrize(
    "fallo",
    [
        "sin_binario",
        "timeout",
        "error",
        "sin_archivo",
        "desactivado",
        "pdf_invalido",
        "oserror",
    ],
)
def test_pdf_no_disponible_devuelve_503(cliente, unidad, settings, fallo):
    settings.DOCUMENTOS_PDF = fallo != "desactivado"

    def ejecutar(args, **kwargs):
        if fallo == "timeout":
            raise subprocess.TimeoutExpired(args, 1, stderr=b"timeout de prueba")
        if fallo == "oserror":
            raise OSError("no se puede ejecutar")
        if fallo == "pdf_invalido":
            Path(args[-1]).with_suffix(".pdf").write_bytes(b"invalido")
        return SimpleNamespace(
            returncode=1 if fallo == "error" else 0, stderr=b"diagnostico"
        )

    with (
        patch(
            "apps.documentos.pdf.shutil.which",
            return_value=None if fallo == "sin_binario" else "/usr/bin/soffice",
        ),
        patch("apps.documentos.pdf.subprocess.run", side_effect=ejecutar) as proceso,
    ):
        res = cliente.get(f"/api/unidades/{unidad.pk}/ficha-mantencion/?formato=pdf")
        assert res.status_code == 503
        assert res.data == {
            "detail": (
                "La conversión a PDF no está disponible en este servidor. "
                "Descarga la ficha en Word."
            ),
            "code": "pdf_no_disponible",
        }
        if fallo in {"sin_binario", "desactivado"}:
            proceso.assert_not_called()


@pytest.mark.skipif(not shutil.which("soffice"), reason="LibreOffice no está instalado")
def test_pdf_real_ficha(ficha, settings):
    settings.DOCUMENTOS_PDF = True
    settings.LIBREOFFICE_BIN = "soffice"
    contenido = convertir_a_pdf(generar_ficha_docx(ficha))
    assert contenido.startswith(b"%PDF")


@pytest.mark.parametrize("disponible", [True, False])
def test_capacidades(cliente, settings, disponible):
    settings.DOCUMENTOS_PDF = True
    with patch(
        "apps.documentos.pdf.shutil.which",
        return_value="/usr/bin/soffice" if disponible else None,
    ):
        res = cliente.get("/api/documentos/capacidades/")
    assert res.status_code == 200
    assert res.data == {"pdf": disponible}


@pytest.mark.parametrize("rol", ["ALUMNO", "DOCENTE"])
def test_documentos_permisos(unidad, rol):
    cliente = APIClient()
    cliente.force_authenticate(user=baker.make(Usuario, rol=rol))
    assert cliente.get("/api/documentos/capacidades/").status_code == 403
    for formato in ["json", "docx", "pdf"]:
        assert (
            cliente.get(
                f"/api/unidades/{unidad.pk}/ficha-mantencion/?formato={formato}"
            ).status_code
            == 403
        )


def test_ruta_plantilla_error_claro():
    with pytest.raises(FileNotFoundError, match="plantilla institucional"):
        ruta_plantilla("no_existe.xlsx")
    with pytest.raises(FileNotFoundError):
        ruta_plantilla("../plantillas.py")


def test_openapi_documenta_formatos(cliente):
    res = cliente.get("/api/schema/", HTTP_ACCEPT="application/vnd.oai.openapi+json")
    operacion = res.data["paths"]["/api/unidades/{id}/ficha-mantencion/"]["get"]
    parametro = next(p for p in operacion["parameters"] if p["name"] == "formato")
    assert set(parametro["schema"]["enum"]) == {"json", "docx", "pdf"}
    assert "application/pdf" in operacion["responses"]["200"]["content"]
    assert "/api/documentos/capacidades/" in res.data["paths"]
