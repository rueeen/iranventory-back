import json
from datetime import date, datetime
from io import BytesIO, StringIO

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from model_bakery import baker
from openpyxl import Workbook
from rest_framework.test import APIClient

from apps.catalogo.models import TipoEquipo
from apps.cuentas.models import Usuario
from apps.inventario.models import Unidad
from apps.mantencion.importacion_plan import ENCABEZADOS, importar_plan
from apps.mantencion.models import PlanMantencion

pytestmark = pytest.mark.django_db


@pytest.fixture
def unidad():
    return baker.make(
        Unidad,
        codigo_activo="UTC000437291",
        codigo_peoplesoft=None,
        tipo_equipo=baker.make(TipoEquipo, nombre="Computador", especificacion=""),
    )


def planilla(filas, *, titulo="MANTENCIÓN DE EQUIPOS", reordenar=False):
    libro = Workbook()
    hoja = libro.active
    hoja.title = titulo
    hoja["A2"] = "PLAN DE MANTENCIÓN EQUIPOS DE LABORATORIO Y TALLER"
    orden = list(reversed(range(8))) if reordenar else list(range(8))
    for c, i in enumerate(orden, start=1):
        hoja.cell(5, c, ENCABEZADOS[i])
    for f, valores in enumerate(filas, start=6):
        for c, i in enumerate(orden, start=1):
            hoja.cell(f, c, valores[i])
    for f, valor in enumerate(["Baja", "Media", "Alta"], start=6):
        hoja.cell(f, 11, valor)
    archivo = BytesIO()
    libro.save(archivo)
    libro.close()
    archivo.seek(0)
    return archivo


def fila(codigos="UTC000437291\n180000003256 ", **extra):
    valores = {
        "codigos": codigos,
        "equipo": "Computador",
        "especificacion": "Intel i7",
        "actividad": "Formateo sistema operativo",
        "frecuencia": "Anual",
        "prioridad": "Baja ",
        "fecha": "01/08/2025",
        "responsable": "Operadores técnicos sede",
    }
    valores.update(extra)
    return list(valores.values())


def test_dos_codigos_y_defaults_aplicados(unidad):
    resultado = importar_plan(planilla([fila()]), simular=False)
    unidad.refresh_from_db()
    plan = PlanMantencion.objects.get()
    assert resultado.planes_creados == 1
    assert resultado.codigos_peoplesoft_completados == 1
    assert resultado.advertencias == []
    assert unidad.codigo_peoplesoft == "180000003256"
    assert unidad.tipo_equipo.especificacion == "Intel i7"
    assert plan.prioridad == "BAJA"
    assert plan.fecha_ultima_mantencion == date(2025, 8, 1)
    assert plan.fecha_proxima_mantencion == date(2026, 8, 1)
    segundo = importar_plan(planilla([fila()]), simular=False)
    assert segundo.planes_creados == 0
    assert segundo.planes_actualizados == 1
    assert segundo.codigos_peoplesoft_completados == 0
    assert PlanMantencion.objects.count() == 1


@pytest.mark.parametrize("simular", [True, False])
def test_crear_faltantes_simulacion(simular):
    resumen = importar_plan(
        planilla(
            [
                fila("IPF000125807", equipo="Equipo uno"),
                fila("CFT000156480\n1800001715", equipo="Equipo dos"),
            ]
        ),
        simular=simular,
        crear_faltantes=True,
    )
    assert (
        resumen.unidades_creadas == resumen.tipos_creados == resumen.planes_creados == 2
    )
    assert resumen.simulado is simular
    assert resumen.advertencias == []
    assert Unidad.objects.count() == (0 if simular else 2)
    assert TipoEquipo.objects.count() == (0 if simular else 2)
    assert PlanMantencion.objects.count() == (0 if simular else 2)
    assert Unidad.history.count() == (0 if simular else 2)
    if not simular:
        assert (
            Unidad.objects.get(codigo_activo="CFT000156480").codigo_peoplesoft
            == "1800001715"
        )
        assert not Unidad.objects.filter(requiere_revision=False).exists()


def test_simular_no_modifica_existentes(unidad):
    resumen = importar_plan(planilla([fila()]))
    unidad.refresh_from_db()
    assert resumen.planes_creados == 1
    assert resumen.codigos_peoplesoft_completados == 1
    assert not PlanMantencion.objects.exists()
    assert unidad.codigo_peoplesoft is None
    assert unidad.tipo_equipo.especificacion == ""


def test_no_encontrados_sin_crear():
    resumen = importar_plan(planilla([fila()]), simular=False)
    assert resumen.no_encontrados == [
        {
            "fila": 6,
            "codigo_activo": "UTC000437291",
            "codigo_peoplesoft": "180000003256",
            "equipo": "Computador",
        }
    ]
    assert not Unidad.objects.exists()
    assert not TipoEquipo.objects.exists()


def test_busca_por_peoplesoft_y_no_sobrescribe_activo(unidad):
    unidad.codigo_peoplesoft = "180000003256"
    unidad.save()
    resultado = importar_plan(planilla([fila("180000003256")]), simular=False)
    assert resultado.planes_creados == 1
    assert PlanMantencion.objects.get().unidad_id == unidad.pk
    unidad.refresh_from_db()
    assert unidad.codigo_activo == "UTC000437291"


def test_no_sobrescribe_peoplesoft_y_especificacion(unidad):
    unidad.codigo_peoplesoft = "180000099999"
    unidad.save()
    unidad.tipo_equipo.especificacion = "Original"
    unidad.tipo_equipo.save()
    resultado = importar_plan(planilla([fila()]), simular=False)
    unidad.refresh_from_db()
    assert unidad.codigo_peoplesoft == "180000099999"
    assert unidad.tipo_equipo.especificacion == "Original"
    assert resultado.codigos_peoplesoft_completados == 0
    assert "Fila 6" in resultado.advertencias[0]


def test_codigo_en_conflicto_no_rompe_transaccion(unidad):
    baker.make(Unidad, codigo_peoplesoft="180000003256")
    resumen = importar_plan(planilla([fila()]), simular=False)
    assert resumen.planes_creados == 1
    assert "otra unidad" in resumen.advertencias[0]
    unidad.refresh_from_db()
    assert unidad.codigo_peoplesoft is None


@pytest.mark.parametrize(
    "fecha", [date(2025, 8, 1), datetime(2025, 8, 1, 15), "01/08/2025"]
)
def test_fecha_formatos(unidad, fecha):
    importar_plan(planilla([fila(fecha=fecha)]), simular=False)
    assert PlanMantencion.objects.get().fecha_ultima_mantencion == date(2025, 8, 1)


def test_valores_desconocidos_advierten(unidad):
    resultado = importar_plan(
        planilla(
            [
                fila(
                    "UTC000437291 ???",
                    frecuencia="Semanal",
                    prioridad="Urgente",
                    fecha="mal",
                )
            ]
        ),
        simular=False,
    )
    plan = PlanMantencion.objects.get()
    assert plan.frecuencia == "ANUAL"
    assert plan.prioridad == "MEDIA"
    assert plan.fecha_ultima_mantencion is None
    assert len(resultado.advertencias) == 4
    assert all("Fila 6" in advertencia for advertencia in resultado.advertencias)


def test_reusa_tipo_nombre_sin_mayusculas(unidad):
    importar_plan(
        planilla([fila("IPF000125807", equipo="COMPUTADOR")]),
        simular=False,
        crear_faltantes=True,
    )
    assert TipoEquipo.objects.count() == 1
    assert (
        Unidad.objects.get(codigo_activo="IPF000125807").tipo_equipo_id
        == unidad.tipo_equipo_id
    )


@pytest.mark.parametrize("titulo", ["Mantencion de equipos", "Otro nombre"])
def test_hoja_columnas_y_filas_vacias(unidad, titulo):
    resultado = importar_plan(
        planilla(
            [
                fila(),
                [None] * 8,
            ],
            titulo=titulo,
            reordenar=True,
        ),
        simular=False,
    )
    assert resultado.planes_creados == 1
    assert resultado.advertencias == []


def test_selecciona_hoja_por_nombre(unidad):
    from openpyxl import load_workbook

    libro = load_workbook(planilla([fila()]))
    libro.create_sheet("Portada", 0)
    archivo = BytesIO()
    libro.save(archivo)
    libro.close()
    archivo.seek(0)
    assert importar_plan(archivo, simular=False).planes_creados == 1


def test_error_fila_revierte_todo(unidad):
    with pytest.raises(ValidationError, match="Fila 7"):
        importar_plan(planilla([fila(), fila(actividad="")]), simular=False)
    assert not PlanMantencion.objects.exists()
    unidad.refresh_from_db()
    assert unidad.codigo_peoplesoft is None
    assert unidad.tipo_equipo.especificacion == ""


def test_encabezado_invalido():
    libro = Workbook()
    archivo = BytesIO()
    libro.save(archivo)
    libro.close()
    archivo.seek(0)
    with pytest.raises(ValidationError, match="encabezado"):
        importar_plan(archivo)


def test_comando_simula_y_aplica(tmp_path, unidad):
    ruta = tmp_path / "plan.xlsx"
    ruta.write_bytes(planilla([fila()]).getvalue())
    salida = StringIO()
    call_command("importar_plan_mantencion", str(ruta), stdout=salida)
    assert json.loads(salida.getvalue())["simulado"] is True
    assert not PlanMantencion.objects.exists()
    salida = StringIO()
    call_command("importar_plan_mantencion", str(ruta), "--aplicar", stdout=salida)
    assert json.loads(salida.getvalue())["simulado"] is False
    assert PlanMantencion.objects.count() == 1


def test_api_multipart_defaults_y_aplicacion(unidad):
    cliente = APIClient()
    cliente.force_authenticate(user=baker.make(Usuario, rol="PANOLERO"))
    for simular in [True, False]:
        archivo = SimpleUploadedFile("plan.xlsx", planilla([fila()]).getvalue())
        formulario = {"archivo": archivo}
        if not simular:
            formulario["simular"] = "false"
        res = cliente.post(
            "/api/planes-mantencion/importar/", formulario, format="multipart"
        )
        assert res.status_code == 200, res.data
        assert res.data["simulado"] is simular
        assert res.data["planes_creados"] == 1
        assert PlanMantencion.objects.count() == (0 if simular else 1)


def test_api_archivo_invalido():
    cliente = APIClient()
    cliente.force_authenticate(user=baker.make(Usuario, rol="DIRECTOR"))
    archivo = SimpleUploadedFile("plan.xlsx", b"esto no es un xlsx")
    res = cliente.post(
        "/api/planes-mantencion/importar/", {"archivo": archivo}, format="multipart"
    )
    assert res.status_code == 400
