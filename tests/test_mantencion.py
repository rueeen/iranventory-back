from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO
from unittest.mock import patch

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, connection, transaction
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from model_bakery import baker
from openpyxl import load_workbook
from rest_framework.test import APIClient

from apps.catalogo.models import Categoria, TipoEquipo, Ubicacion
from apps.compras.models import OrdenCompra, Proveedor
from apps.cuentas.models import Usuario
from apps.inventario.models import Unidad
from apps.mantencion.importacion_plan import ENCABEZADOS, TITULO, importar_plan
from apps.mantencion.models import PlanMantencion, RegistroMantencion
from apps.mantencion.services import enviar_a_mantencion, registrar_mantencion

pytestmark = pytest.mark.django_db


@pytest.fixture
def unidad():
    tipo = baker.make(TipoEquipo, nombre="Computador", especificacion="Intel i7")
    return baker.make(
        Unidad,
        tipo_equipo=tipo,
        codigo_activo="UTC000437291",
        codigo_peoplesoft="180000003256",
    )


@pytest.fixture
def panolero():
    return baker.make(Usuario, rol=Usuario.Rol.PANOLERO)


@pytest.fixture
def cliente(panolero):
    cliente = APIClient()
    cliente.force_authenticate(user=panolero)
    return cliente


@pytest.fixture
def plan(unidad):
    return baker.make(PlanMantencion, unidad=unidad, actividad="Limpieza")


def datos(unidad, **extra):
    return {
        "unidad": unidad,
        "fecha_realizacion": timezone.localdate(),
        "tipo": RegistroMantencion.Tipo.PREVENTIVO,
        "descripcion": "Limpieza técnica",
        **extra,
    }


@pytest.mark.parametrize(
    ("frecuencia", "ultima", "proxima"),
    [
        ("MENSUAL", date(2025, 1, 31), date(2025, 2, 28)),
        ("MENSUAL", date(2024, 1, 31), date(2024, 2, 29)),
        ("TRIMESTRAL", date(2025, 11, 30), date(2026, 2, 28)),
        ("SEMESTRAL", date(2025, 8, 31), date(2026, 2, 28)),
        ("ANUAL", date(2024, 2, 29), date(2025, 2, 28)),
    ],
)
def test_fechas_frecuencias(unidad, frecuencia, ultima, proxima):
    plan = baker.make(
        PlanMantencion,
        unidad=unidad,
        frecuencia=frecuencia,
        fecha_ultima_mantencion=ultima,
    )
    assert plan.fecha_proxima_mantencion == proxima
    plan.fecha_ultima_mantencion = None
    plan.save(update_fields=["fecha_ultima_mantencion"])
    plan.refresh_from_db()
    assert plan.fecha_proxima_mantencion is None


def test_querysets_estados_y_limites(unidad):
    hoy = date(2026, 11, 10)
    nunca = baker.make(PlanMantencion, unidad=unidad, actividad="Nunca")
    casos = [(None, nunca)]
    for dias in [-1, 0, 30, 31]:
        proxima = hoy + timedelta(days=dias)
        obj = baker.make(
            PlanMantencion,
            unidad=unidad,
            actividad=str(dias),
            frecuencia="ANUAL",
            fecha_ultima_mantencion=proxima.replace(year=2025),
        )
        casos.append((dias, obj))
    inactivo = baker.make(
        PlanMantencion, unidad=unidad, actividad="Inactivo", activo=False
    )
    assert set(PlanMantencion.objects.vencidos(hoy)) == {nunca, casos[1][1]}
    assert set(PlanMantencion.objects.proximos(hoy=hoy)) == {casos[2][1], casos[3][1]}
    assert set(PlanMantencion.objects.al_dia(hoy=hoy)) == {casos[4][1]}
    assert set(PlanMantencion.objects.proximos(dias=0, hoy=hoy)) == {casos[2][1]}
    with patch("django.utils.timezone.localdate", return_value=hoy):
        assert [obj.estado_plan for _, obj in casos] == [
            "VENCIDO",
            "VENCIDO",
            "PROXIMO",
            "PROXIMO",
            "AL_DIA",
        ]
        assert inactivo.estado_plan == "INACTIVO"
    assert list(PlanMantencion.objects.all())[:2] == [nunca, inactivo]


def test_unique_plan(plan):
    with pytest.raises(IntegrityError), transaction.atomic():
        baker.make(PlanMantencion, unidad=plan.unidad, actividad=plan.actividad)


@pytest.mark.parametrize("estado", ["BUENO", "REPARABLE", "MALO"])
def test_registrar_actualiza_plan_unidad_e_historia(unidad, plan, panolero, estado):
    unidad.situacion = Unidad.Situacion.REPARACION
    unidad.save()
    registro = registrar_mantencion(
        datos(unidad, plan=plan, estado_resultante=estado), panolero
    )
    unidad.refresh_from_db()
    plan.refresh_from_db()
    assert registro.registrado_por == panolero
    assert plan.fecha_ultima_mantencion == timezone.localdate()
    assert plan.fecha_proxima_mantencion.year == timezone.localdate().year + 1
    assert unidad.estado == estado
    assert unidad.situacion == ("REPARACION" if estado == "MALO" else "DISPONIBLE")
    assert registro.history.count() == 1
    assert unidad.history.first().history_user == panolero


def test_registro_anterior_no_retrocede_plan(unidad, plan, panolero):
    hoy = timezone.localdate()
    registrar_mantencion(datos(unidad, plan=plan), panolero)
    registrar_mantencion(
        datos(unidad, plan=plan, fecha_realizacion=hoy - timedelta(days=2)), panolero
    )
    plan.refresh_from_db()
    assert plan.fecha_ultima_mantencion == hoy


@pytest.mark.parametrize("error", ["prestada", "futura", "plan", "solicitud", "costo"])
def test_registro_invalido_es_atomico(unidad, plan, panolero, error):
    valores = datos(unidad, plan=plan, estado_resultante="MALO")
    if error == "prestada":
        unidad.situacion = "PRESTADA"
        unidad.save()
    elif error == "futura":
        valores["fecha_realizacion"] += timedelta(days=1)
    elif error == "plan":
        valores["plan"] = baker.make(PlanMantencion)
    elif error == "solicitud":
        valores["fecha_solicitud"] = timezone.localdate() + timedelta(days=1)
    else:
        valores["costo"] = -1
    with pytest.raises(ValidationError):
        registrar_mantencion(valores, panolero)
    assert RegistroMantencion.objects.count() == 0
    plan.refresh_from_db()
    unidad.refresh_from_db()
    assert plan.fecha_ultima_mantencion is None
    assert unidad.estado == "BUENO"


def test_empresa_y_orden_autocompletadas(unidad, panolero):
    proveedor = baker.make(Proveedor, rut="76269680-0", razon_social="Servicio Técnico")
    orden = baker.make(OrdenCompra, numero="OC-99")
    registro = registrar_mantencion(
        datos(unidad, proveedor=proveedor, orden_compra=orden), panolero
    )
    assert registro.empresa == "Servicio Técnico"
    assert registro.numero_orden_compra == "OC-99"
    otro = registrar_mantencion(
        datos(unidad, proveedor=proveedor, empresa="Interna"), panolero
    )
    assert otro.empresa == "Interna"


def test_api_create_registro(cliente, unidad, plan, panolero):
    proveedor = baker.make(Proveedor, rut="76269680-0", razon_social="Técnicos")
    orden = baker.make(OrdenCompra, numero="OC-1")
    res = cliente.post(
        "/api/registros-mantencion/",
        {
            "unidad": unidad.pk,
            "plan": plan.pk,
            "tipo": "PREVENTIVO",
            "fecha_realizacion": str(timezone.localdate()),
            "descripcion": "Prueba",
            "proveedor_id": proveedor.pk,
            "orden_compra_id": orden.pk,
            "estado_resultante": "MALO",
            "registrado_por": 999,
        },
        format="json",
    )
    assert res.status_code == 201, res.data
    assert res.data["registrado_por"] == panolero.pk
    assert res.data["proveedor"] == {"id": proveedor.pk, "nombre": "Técnicos"}
    assert res.data["orden_compra"] == {"id": orden.pk, "numero": "OC-1"}
    unidad.refresh_from_db()
    assert unidad.estado == "MALO"


def test_api_validacion_modelo(cliente, unidad, plan):
    res = cliente.post(
        "/api/registros-mantencion/",
        {
            "unidad": unidad.pk,
            "plan": plan.pk,
            "tipo": "PREVENTIVO",
            "fecha_realizacion": str(timezone.localdate() + timedelta(days=1)),
            "descripcion": "Prueba",
        },
        format="json",
    )
    assert res.status_code == 400
    assert "fecha_realizacion" in res.data
    assert not RegistroMantencion.objects.exists()


def test_borrar_recalcula_plan_sin_cambiar_unidad(cliente, unidad, plan, panolero):
    hoy = timezone.localdate()
    viejo = registrar_mantencion(
        datos(unidad, plan=plan, fecha_realizacion=hoy - timedelta(days=2)), panolero
    )
    nuevo = registrar_mantencion(datos(unidad, plan=plan), panolero)
    assert cliente.delete(f"/api/registros-mantencion/{nuevo.pk}/").status_code == 204
    plan.refresh_from_db()
    assert plan.fecha_ultima_mantencion == viejo.fecha_realizacion
    assert cliente.delete(f"/api/registros-mantencion/{viejo.pk}/").status_code == 204
    plan.refresh_from_db()
    unidad.refresh_from_db()
    assert plan.fecha_ultima_mantencion is None
    assert plan.fecha_proxima_mantencion is None
    assert unidad.estado == "BUENO"


def test_editar_reasigna_plan_y_recalcula_ambos(cliente, unidad, plan, panolero):
    otro = baker.make(PlanMantencion, unidad=unidad, actividad="Revisión")
    registro = registrar_mantencion(datos(unidad, plan=plan), panolero)
    fecha = timezone.localdate() - timedelta(days=4)
    res = cliente.patch(
        f"/api/registros-mantencion/{registro.pk}/",
        {
            "plan": otro.pk,
            "fecha_realizacion": str(fecha),
            "estado_resultante": "MALO",
        },
        format="json",
    )
    assert res.status_code == 200, res.data
    plan.refresh_from_db()
    otro.refresh_from_db()
    unidad.refresh_from_db()
    assert plan.fecha_ultima_mantencion is None
    assert otro.fecha_ultima_mantencion == fecha
    assert unidad.estado == "BUENO"
    assert otro.fecha_proxima_mantencion.year == fecha.year + 1


@pytest.mark.parametrize(
    "situacion", ["DISPONIBLE", "PRESTADA", "RESERVADA", "BAJA", "REPARACION"]
)
def test_enviar_mantencion(cliente, unidad, situacion):
    unidad.situacion = situacion
    unidad.save()
    res = cliente.post(f"/api/unidades/{unidad.pk}/enviar-mantencion/")
    assert res.status_code == (200 if situacion == "DISPONIBLE" else 400)
    unidad.refresh_from_db()
    assert unidad.situacion == (
        "REPARACION" if situacion == "DISPONIBLE" else situacion
    )


@pytest.mark.parametrize("rol", ["ALUMNO", "DOCENTE"])
def test_permisos_restringidos(unidad, plan, rol):
    cliente = APIClient()
    usuario = baker.make(Usuario, rol=rol)
    cliente.force_authenticate(user=usuario)
    for url in [
        "/api/planes-mantencion/",
        f"/api/planes-mantencion/{plan.pk}/",
        "/api/planes-mantencion/resumen/",
        "/api/planes-mantencion/exportar/",
        "/api/registros-mantencion/",
        f"/api/unidades/{unidad.pk}/ficha-mantencion/",
    ]:
        assert cliente.get(url).status_code == 403, url
    for url in [
        "/api/planes-mantencion/",
        "/api/planes-mantencion/importar/",
        "/api/registros-mantencion/",
        f"/api/unidades/{unidad.pk}/enviar-mantencion/",
    ]:
        assert cliente.post(url, {}, format="json").status_code == 403
    assert cliente.get(f"/api/unidades/{unidad.pk}/").status_code == 200
    with pytest.raises(PermissionDenied):
        enviar_a_mantencion(unidad, usuario)


def test_director_puede_leer_y_escribir(unidad):
    cliente = APIClient()
    cliente.force_authenticate(user=baker.make(Usuario, rol="DIRECTOR"))
    res = cliente.post(
        "/api/planes-mantencion/",
        {
            "unidad_id": unidad.pk,
            "actividad": "Revisión",
        },
        format="json",
    )
    assert res.status_code == 201, res.data
    assert res.data["unidad"]["nombre"] == "Computador"
    assert res.data["estado_plan"] == "VENCIDO"
    assert (
        cliente.get(f"/api/unidades/{unidad.pk}/ficha-mantencion/").status_code == 200
    )


def test_resumen_filtros_y_orden(cliente, unidad):
    hoy = timezone.localdate()
    nunca = baker.make(PlanMantencion, unidad=unidad, actividad="Nunca")
    futuro = baker.make(
        PlanMantencion,
        unidad=unidad,
        actividad="Futuro",
        fecha_ultima_mantencion=hoy,
    )
    baker.make(PlanMantencion, unidad=unidad, actividad="Inactivo", activo=False)
    # Mantención mensual ejecutada ayer: vence dentro de 30 días.
    baker.make(
        PlanMantencion,
        unidad=unidad,
        actividad="Próximo",
        frecuencia="MENSUAL",
        fecha_ultima_mantencion=hoy - timedelta(days=1),
    )
    res = cliente.get("/api/planes-mantencion/resumen/")
    assert res.data == {
        "vencidos": 1,
        "proximos_30_dias": 1,
        "al_dia": 1,
        "total_activos": 3,
    }
    filtrado = cliente.get("/api/planes-mantencion/?estado_plan=VENCIDO")
    assert [p["id"] for p in filtrado.data["results"]] == [nunca.pk]
    assert cliente.get("/api/planes-mantencion/?search=180000003256").data["count"] == 4
    assert cliente.get("/api/planes-mantencion/?activo=false").data["count"] == 1
    res = cliente.get(
        "/api/planes-mantencion/?estado_plan=AL_DIA&ordering=-fecha_proxima_mantencion"
    )
    assert res.data["results"][0]["id"] == futuro.pk


def test_exportacion_e_ida_y_vuelta(cliente, unidad, plan):
    res = cliente.get("/api/planes-mantencion/exportar/?estado_plan=VENCIDO")
    assert res.status_code == 200
    assert "Plan_de_Mantencion_" in res["Content-Disposition"]
    libro = load_workbook(BytesIO(res.content))
    hoja = libro["MANTENCIÓN DE EQUIPOS"]
    assert hoja["A2"].value == TITULO
    assert hoja["A2"].font.bold
    assert "A2:H2" in hoja.merged_cells
    assert [" ".join(hoja.cell(5, c).value.split()) for c in range(1, 9)] == ENCABEZADOS
    assert hoja["A6"].value == "UTC000437291\n180000003256"
    assert hoja["A6"].alignment.wrap_text
    assert hoja["F6"].value == "Media"
    assert hoja["G6"].number_format == "DD/MM/YYYY"
    validacion = list(hoja.data_validations.dataValidation)[0]
    assert "F6" in validacion.sqref
    assert validacion.formula1 == "$K$6:$K$8"
    libro.close()
    resultado = importar_plan(BytesIO(res.content), simular=False)
    assert resultado.planes_creados == 0
    assert resultado.planes_actualizados == 1
    assert resultado.advertencias == []
    assert PlanMantencion.objects.count() == 1


def test_ficha_completa_orden_y_settings(cliente, unidad, panolero, settings):
    settings.INVENTARIO_AREA = "Área de prueba"
    settings.INVENTARIO_SEDE = "Sede de prueba"
    unidad.tipo_equipo.categoria = baker.make(Categoria, nombre="Computación")
    unidad.tipo_equipo.save()
    unidad.ubicacion = baker.make(Ubicacion, nombre="LEICA", sede="Arica")
    unidad.marca, unidad.modelo, unidad.numero_serie = "HP", "All-in-one", "SER-1"
    unidad.codigo_proyecto, unidad.periodo_calibracion = "PR-1", "Anual"
    unidad.save()
    hoy = timezone.localdate()
    registrar_mantencion(
        datos(unidad, fecha_solicitud=hoy, costo=Decimal("100.50")), panolero
    )
    registrar_mantencion(
        datos(
            unidad,
            fecha_realizacion=hoy - timedelta(days=2),
            fecha_solicitud=hoy - timedelta(days=3),
        ),
        panolero,
    )
    res = cliente.get(f"/api/unidades/{unidad.pk}/ficha-mantencion/")
    assert res.status_code == 200
    assert res.data == {
        "area": "Área de prueba",
        "sede": "Sede de prueba",
        "nombre_equipo": "Computador",
        "tipo_equipo": "Computación",
        "fecha_solicitud_mantenimiento": str(hoy),
        "marca": "HP",
        "modelo": "All-in-one",
        "ubicacion": "LEICA (Arica)",
        "serie": "SER-1",
        "codigo_inventario": "UTC000437291",
        "codigo_peoplesoft": "180000003256",
        "codigo_proyecto": "PR-1",
        "periodo_calibracion": "Anual",
        "registros": [
            {
                "fecha_realizacion": str(hoy - timedelta(days=2)),
                "descripcion": "Limpieza técnica",
                "empresa": "",
                "orden_compra": "",
                "costo": "0.00",
                "tipo": "PREVENTIVO",
                "realizado_por": "",
            },
            {
                "fecha_realizacion": str(hoy),
                "descripcion": "Limpieza técnica",
                "empresa": "",
                "orden_compra": "",
                "costo": "100.50",
                "tipo": "PREVENTIVO",
                "realizado_por": "",
            },
        ],
    }


def test_unidad_campos_y_codigos_vacios(cliente, unidad):
    res = cliente.patch(
        f"/api/unidades/{unidad.pk}/",
        {
            "codigo_peoplesoft": "",
            "marca": "HP",
            "modelo": "M1",
            "numero_serie": "ABC123",
            "codigo_proyecto": "P1",
            "periodo_calibracion": "Anual",
        },
        format="json",
    )
    assert res.status_code == 200, res.data
    assert res.data["codigo_peoplesoft"] is None
    assert cliente.get("/api/unidades/?search=ABC123").data["count"] == 1
    otro = baker.make(Unidad, codigo_peoplesoft="", codigo_activo="")
    otro.refresh_from_db()
    assert otro.codigo_peoplesoft is None
    assert otro.codigo_activo is None


def test_filtro_fecha_registros(cliente, unidad, panolero):
    hoy = timezone.localdate()
    registrar_mantencion(datos(unidad), panolero)
    registrar_mantencion(
        datos(unidad, fecha_realizacion=hoy - timedelta(days=4)), panolero
    )
    res = cliente.get(
        f"/api/registros-mantencion/?fecha_desde={hoy}&fecha_hasta={hoy}&unidad={unidad.pk}"
    )
    assert res.status_code == 200
    assert res.data["count"] == 1


def test_esquema_endpoints(cliente):
    res = cliente.get("/api/schema/", HTTP_ACCEPT="application/vnd.oai.openapi+json")
    assert res.status_code == 200
    paths = res.data["paths"]
    for ruta in [
        "/api/planes-mantencion/",
        "/api/planes-mantencion/resumen/",
        "/api/planes-mantencion/importar/",
        "/api/planes-mantencion/exportar/",
        "/api/registros-mantencion/",
        "/api/unidades/{id}/ficha-mantencion/",
        "/api/unidades/{id}/enviar-mantencion/",
    ]:
        assert ruta in paths
    schema = paths["/api/unidades/{id}/ficha-mantencion/"]["get"]["responses"]["200"][
        "content"
    ]["application/json"]["schema"]
    assert schema == {"$ref": "#/components/schemas/FichaMantencion"}


def test_registros_incluyen_unidad_detalle(cliente, unidad, panolero):
    registro = registrar_mantencion(datos(unidad), panolero)
    res = cliente.get("/api/registros-mantencion/")
    assert res.status_code == 200
    assert res.data["count"] == 1
    fila = res.data["results"][0]
    assert fila["id"] == registro.pk
    assert fila["unidad"] == unidad.pk
    assert fila["unidad_detalle"] == {
        "id": unidad.pk,
        "codigo_activo": "UTC000437291",
        "codigo_peoplesoft": "180000003256",
        "tipo_equipo_nombre": "Computador",
    }


@pytest.mark.parametrize(
    "busqueda",
    [
        "UTC000437291",
        "180000003256",
        "Computador",
        "Limpieza técnica",
        "Empresa específica",
        "Colaborador específico",
    ],
)
def test_busqueda_registros(cliente, unidad, panolero, busqueda):
    registro = registrar_mantencion(
        datos(
            unidad,
            empresa="Empresa específica",
            realizado_por="Colaborador específico",
        ),
        panolero,
    )
    otra = baker.make(
        Unidad,
        tipo_equipo=baker.make(TipoEquipo, nombre="Osciloscopio"),
        codigo_activo="CFT000156480",
        codigo_peoplesoft="1800001715",
    )
    registrar_mantencion(datos(otra, descripcion="Calibración"), panolero)
    res = cliente.get("/api/registros-mantencion/", {"search": busqueda})
    assert res.status_code == 200
    assert [fila["id"] for fila in res.data["results"]] == [registro.pk]
    combinado = cliente.get(
        "/api/registros-mantencion/",
        {
            "search": busqueda,
            "unidad": otra.pk,
        },
    )
    assert combinado.status_code == 200
    assert combinado.data["count"] == 0


def test_queries_listado_registros_no_crecen_con_unidades(cliente, unidad, panolero):
    registrar_mantencion(datos(unidad), panolero)
    with CaptureQueriesContext(connection) as una:
        res = cliente.get("/api/registros-mantencion/")
        assert res.status_code == 200
        assert len(res.data["results"]) == 1
    for indice in range(4):
        otra = baker.make(
            Unidad,
            tipo_equipo=baker.make(TipoEquipo, nombre=f"Equipo {indice}"),
        )
        registrar_mantencion(datos(otra), panolero)
    with CaptureQueriesContext(connection) as cinco:
        res = cliente.get("/api/registros-mantencion/")
        assert res.status_code == 200
        assert len(res.data["results"]) == 5
        assert len({fila["unidad_detalle"]["id"] for fila in res.data["results"]}) == 5
    assert 0 < len(cinco) <= len(una) <= 2


def test_unidad_sigue_escribible_y_detalle_es_solo_lectura(cliente, unidad):
    otra = baker.make(Unidad, tipo_equipo=baker.make(TipoEquipo, nombre="Otro equipo"))
    res = cliente.post(
        "/api/registros-mantencion/",
        {
            "unidad": unidad.pk,
            "tipo": "PREVENTIVO",
            "fecha_realizacion": str(timezone.localdate()),
            "descripcion": "Revisión",
            "unidad_detalle": {"id": otra.pk, "tipo_equipo_nombre": "Ignorar"},
        },
        format="json",
    )
    assert res.status_code == 201, res.data
    assert res.data["unidad"] == unidad.pk
    assert res.data["unidad_detalle"]["id"] == unidad.pk
    res = cliente.patch(
        f"/api/registros-mantencion/{res.data['id']}/",
        {
            "unidad": otra.pk,
            "unidad_detalle": {"id": unidad.pk},
        },
        format="json",
    )
    assert res.status_code == 200, res.data
    assert res.data["unidad"] == otra.pk
    assert res.data["unidad_detalle"]["tipo_equipo_nombre"] == "Otro equipo"
