from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from model_bakery import baker
from rest_framework.test import APIClient

from apps.cuentas.models import Usuario
from apps.prestamos.models import Prestamo

pytestmark = pytest.mark.django_db
ZONA = ZoneInfo("America/Santiago")


@pytest.fixture
def ahora():
    return datetime(2026, 11, 10, 9, tzinfo=ZONA)


@pytest.fixture
def alumno():
    return baker.make(Usuario, rol=Usuario.Rol.ALUMNO)


@pytest.fixture
def panolero():
    return baker.make(Usuario, rol=Usuario.Rol.PANOLERO)


@pytest.fixture
def api_client():
    return APIClient()


def prestamo(usuario, fecha, estado=Prestamo.Estado.ENTREGADA):
    return baker.make(
        Prestamo,
        solicitante=usuario,
        estado=estado,
        fecha_devolucion_comprometida=fecha,
    )


@pytest.mark.parametrize(
    ("estado", "delta", "esperado"),
    [
        (Prestamo.Estado.ENTREGADA, -1, True),
        (Prestamo.Estado.ENTREGADA, 1, False),
        (Prestamo.Estado.ENTREGADA, None, False),
        (Prestamo.Estado.ENTREGADA, 0, False),
        (Prestamo.Estado.DEVOLUCION, -1, False),
        (Prestamo.Estado.CERRADA, -1, False),
        (Prestamo.Estado.APROBADA, -1, False),
    ],
)
def test_regla_atraso(alumno, ahora, estado, delta, esperado):
    fecha = ahora + timedelta(days=delta) if delta is not None else None
    obj = prestamo(alumno, fecha, estado)
    assert obj.esta_atrasado(ahora) is esperado
    assert obj.dias_atraso(ahora) == (1 if esperado else None)
    assert Prestamo.objects.atrasados(ahora).filter(pk=obj.pk).exists() is esperado


@pytest.mark.parametrize(("horas", "dias"), [(1, 1), (15, 1), (73, 3)])
def test_dias_calendario(alumno, ahora, horas, dias):
    obj = prestamo(alumno, ahora - timedelta(hours=horas))
    assert obj.dias_atraso(ahora) == dias


def test_dias_usa_fecha_local_y_no_utc(alumno):
    ahora = datetime(2026, 11, 10, 23, 30, tzinfo=ZONA)
    obj = prestamo(alumno, datetime(2026, 11, 7, 22, tzinfo=ZONA))
    assert obj.dias_atraso(ahora) == 3


def test_vencen_hoy_limites(alumno, ahora):
    vigente = prestamo(alumno, ahora + timedelta(hours=2))
    igual = prestamo(alumno, ahora)
    prestamo(alumno, ahora - timedelta(seconds=1))
    prestamo(alumno, datetime(2026, 11, 11, tzinfo=ZONA))
    prestamo(alumno, ahora + timedelta(hours=2), Prestamo.Estado.DEVOLUCION)
    prestamo(alumno, None)
    assert set(Prestamo.objects.vencen_hoy(ahora)) == {vigente, igual}


@pytest.mark.parametrize("rol", list(Usuario.Rol.values))
def test_api_filtros_resumen_y_visibilidad(api_client, alumno, ahora, rol):
    usuario = baker.make(Usuario, rol=rol)
    propio = prestamo(usuario, ahora - timedelta(days=3))
    otro = prestamo(alumno, ahora - timedelta(days=5))
    futuro = prestamo(usuario, ahora + timedelta(hours=2))
    sin_fecha = prestamo(usuario, None)
    devuelto = prestamo(usuario, ahora - timedelta(days=8), Prestamo.Estado.DEVOLUCION)
    api_client.force_authenticate(user=usuario)
    globales = rol in {Usuario.Rol.PANOLERO, Usuario.Rol.DIRECTOR}
    with patch("django.utils.timezone.now", return_value=ahora):
        lista = api_client.get(
            "/api/prestamos/?atrasado=true&ordering=fecha_devolucion_comprometida"
        )
        assert lista.status_code == 200
        ids = [obj["id"] for obj in lista.data["results"]]
        assert ids == ([otro.pk, propio.pk] if globales else [propio.pk])
        negativos = api_client.get("/api/prestamos/?atrasado=false")
        assert {obj["id"] for obj in negativos.data["results"]} == {
            futuro.pk,
            sin_fecha.pk,
            devuelto.pk,
        }
        filtrado = api_client.get("/api/prestamos/?atrasado=true&estado=DEVOLUCION")
        assert filtrado.data["count"] == 0
        resumen = api_client.get("/api/prestamos/resumen-atrasos/")
        assert resumen.status_code == 200
        assert resumen.data["atrasados"] == (2 if globales else 1)
        assert resumen.data["vencen_hoy"] == 1
        assert resumen.data["mas_antiguo"]["id"] == (otro.pk if globales else propio.pk)
        assert resumen.data["mas_antiguo"]["dias_atraso"] == (5 if globales else 3)
        detalle = api_client.get(f"/api/prestamos/{propio.pk}/")
        assert detalle.status_code == 200
        assert detalle.data["esta_atrasado"] is True
        assert detalle.data["dias_atraso"] == 3
        if not globales:
            assert api_client.get(f"/api/prestamos/{otro.pk}/").status_code == 404


def test_resumen_vacio(api_client, panolero):
    api_client.force_authenticate(user=panolero)
    res = api_client.get("/api/prestamos/resumen-atrasos/")
    assert res.status_code == 200
    assert res.data == {"atrasados": 0, "vencen_hoy": 0, "mas_antiguo": None}


def test_resumen_requiere_autenticacion(api_client):
    assert api_client.get("/api/prestamos/resumen-atrasos/").status_code == 401


def test_campos_calculados_solo_lectura(api_client, alumno):
    api_client.force_authenticate(user=alumno)
    res = api_client.post(
        "/api/prestamos/", {"esta_atrasado": True, "dias_atraso": 10}, format="json"
    )
    assert res.status_code == 201
    assert res.data["esta_atrasado"] is False
    assert res.data["dias_atraso"] is None


def test_schema_resumen(api_client, panolero):
    api_client.force_authenticate(user=panolero)
    res = api_client.get("/api/schema/", HTTP_ACCEPT="application/vnd.oai.openapi+json")
    assert res.status_code == 200
    operacion = res.data["paths"]["/api/prestamos/resumen-atrasos/"]["get"]
    assert operacion["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ResumenAtrasos"
    }
    assert (
        "mas_antiguo"
        in res.data["components"]["schemas"]["ResumenAtrasos"]["properties"]
    )
