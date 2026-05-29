import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.catalogo.models import TipoEquipo
from apps.cuentas.models import Usuario
from apps.inventario.models import Unidad


@pytest.fixture
def alumno():
    return get_user_model().objects.create_user(
        username="alumno-api",
        password="clave-segura-123",
        rol=Usuario.Rol.ALUMNO,
    )


@pytest.fixture
def panolero():
    return get_user_model().objects.create_user(
        username="panolero-api",
        password="clave-segura-123",
        rol=Usuario.Rol.PANOLERO,
    )


@pytest.fixture
def api_client():
    return APIClient()


@pytest.mark.django_db
def test_alumno_lista_catalogo_pero_no_crea(api_client, alumno):
    TipoEquipo.objects.create(nombre="Osciloscopio")
    api_client.force_authenticate(user=alumno)

    list_response = api_client.get("/api/tipos-equipo/")
    create_response = api_client.post(
        "/api/tipos-equipo/",
        {"nombre": "Fuente DC"},
        format="json",
    )

    assert list_response.status_code == 200
    assert create_response.status_code == 403


@pytest.mark.django_db
def test_panolero_crea_catalogo(api_client, panolero):
    api_client.force_authenticate(user=panolero)

    response = api_client.post(
        "/api/tipos-equipo/",
        {"nombre": "Fuente DC", "cantidad_necesaria": 1},
        format="json",
    )

    assert response.status_code == 201
    assert response.data["nombre"] == "Fuente DC"


@pytest.mark.django_db
def test_filtro_unidad_requiere_revision_devuelve_solo_marcadas(api_client, alumno):
    tipo_equipo = TipoEquipo.objects.create(nombre="Multímetro")
    marcada = Unidad.objects.create(
        tipo_equipo=tipo_equipo,
        codigo_activo="MUL-REV",
        requiere_revision=True,
    )
    Unidad.objects.create(tipo_equipo=tipo_equipo, codigo_activo="MUL-OK")
    api_client.force_authenticate(user=alumno)

    response = api_client.get("/api/unidades/", {"requiere_revision": "true"})

    assert response.status_code == 200
    assert [unidad["id"] for unidad in response.data["results"]] == [marcada.id]


@pytest.mark.django_db
def test_tipo_equipo_expone_stock_disponible_y_brecha(api_client, alumno):
    tipo_equipo = TipoEquipo.objects.create(
        nombre="Osciloscopio",
        tipo_seguimiento=TipoEquipo.TipoSeguimiento.SERIE,
        cantidad_necesaria=4,
    )
    Unidad.objects.create(tipo_equipo=tipo_equipo, codigo_activo="OSC-001")
    Unidad.objects.create(
        tipo_equipo=tipo_equipo,
        codigo_activo="OSC-002",
        situacion=Unidad.Situacion.PRESTADA,
    )
    Unidad.objects.create(
        tipo_equipo=tipo_equipo,
        codigo_activo="OSC-003",
        situacion=Unidad.Situacion.BAJA,
    )
    api_client.force_authenticate(user=alumno)

    response = api_client.get(f"/api/tipos-equipo/{tipo_equipo.id}/")

    assert response.status_code == 200
    assert response.data["stock_total"] == 2
    assert response.data["stock_disponible"] == 1
    assert response.data["brecha"] == 2
