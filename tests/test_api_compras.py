import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.catalogo.models import TipoEquipo
from apps.compras.models import OrdenCompra
from apps.cuentas.models import Usuario


@pytest.fixture
def alumno_compras():
    return get_user_model().objects.create_user(
        username="alumno-compras-api",
        password="clave-segura-123",
        rol=Usuario.Rol.ALUMNO,
    )


@pytest.fixture
def panolero_compras():
    return get_user_model().objects.create_user(
        username="panolero-compras-api",
        password="clave-segura-123",
        rol=Usuario.Rol.PANOLERO,
    )


@pytest.fixture
def api_client():
    return APIClient()


@pytest.mark.django_db
def test_panolero_crea_orden_compra_con_items_anidados(api_client, panolero_compras):
    tipo_equipo = TipoEquipo.objects.create(nombre="PLC compacto")
    api_client.force_authenticate(user=panolero_compras)

    response = api_client.post(
        "/api/ordenes-compra/",
        {
            "numero": "OC-2026-001",
            "proveedor": "Proveedor Técnico",
            "items": [
                {
                    "tipo_equipo_id": tipo_equipo.id,
                    "cantidad": 2,
                    "codigos_activo": "PLC-001\nPLC-002",
                }
            ],
        },
        format="json",
    )

    assert response.status_code == 201
    assert response.data["estado"] == OrdenCompra.Estado.BORRADOR
    assert response.data["creado_por"] == panolero_compras.id
    assert response.data["items"][0]["tipo_equipo"]["nombre"] == "PLC compacto"


@pytest.mark.django_db
def test_alumno_lista_ordenes_compra_pero_no_crea(api_client, alumno_compras):
    OrdenCompra.objects.create(numero="OC-LECTURA", proveedor="Proveedor")
    api_client.force_authenticate(user=alumno_compras)

    list_response = api_client.get("/api/ordenes-compra/")
    create_response = api_client.post(
        "/api/ordenes-compra/",
        {"numero": "OC-BLOQUEADA", "proveedor": "Proveedor"},
        format="json",
    )

    assert list_response.status_code == 200
    assert create_response.status_code == 403


@pytest.mark.django_db
def test_panolero_envia_orden_compra_a_revision(api_client, panolero_compras):
    orden_compra = OrdenCompra.objects.create(numero="OC-REV", proveedor="Proveedor")
    api_client.force_authenticate(user=panolero_compras)

    response = api_client.post(
        f"/api/ordenes-compra/{orden_compra.id}/enviar-a-revision/"
    )

    assert response.status_code == 200
    assert response.data["estado"] == OrdenCompra.Estado.EN_REVISION
    assert response.data["revisado_por"] == panolero_compras.id
    assert response.data["fecha_revision"] is not None


@pytest.mark.django_db
def test_filtro_items_orden_compra_por_tipo_equipo(api_client, alumno_compras):
    tipo_filtrado = TipoEquipo.objects.create(nombre="Sensor inductivo")
    otro_tipo = TipoEquipo.objects.create(nombre="Fuente DC")
    orden_compra = OrdenCompra.objects.create(numero="OC-FILTRO", proveedor="Proveedor")
    item_filtrado = orden_compra.items.create(
        tipo_equipo=tipo_filtrado,
        cantidad=3,
    )
    orden_compra.items.create(tipo_equipo=otro_tipo, cantidad=1)
    api_client.force_authenticate(user=alumno_compras)

    response = api_client.get(
        "/api/items-orden-compra/",
        {"tipo_equipo": tipo_filtrado.id},
    )

    assert response.status_code == 200
    assert [item["id"] for item in response.data["results"]] == [item_filtrado.id]
