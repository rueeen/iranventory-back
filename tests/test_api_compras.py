import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.catalogo.models import TipoEquipo
from apps.compras.models import OrdenCompra
from apps.cuentas.models import Usuario
from apps.inventario.models import Unidad


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
        f"/api/ordenes-compra/{orden_compra.id}/enviar_revision/"
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


@pytest.mark.django_db
def test_aceptar_orden_compra_serie_crea_unidades(api_client, panolero_compras):
    tipo_equipo = TipoEquipo.objects.create(
        nombre="Osciloscopio",
        tipo_seguimiento=TipoEquipo.TipoSeguimiento.SERIE,
    )
    orden_compra = OrdenCompra.objects.create(
        numero="OC-SERIE",
        proveedor="Proveedor",
        estado=OrdenCompra.Estado.EN_REVISION,
    )
    orden_compra.items.create(
        tipo_equipo=tipo_equipo,
        cantidad=2,
        codigos_activo="OSC-001\nOSC-002",
    )
    api_client.force_authenticate(user=panolero_compras)

    response = api_client.post(f"/api/ordenes-compra/{orden_compra.id}/aceptar/")

    assert response.status_code == 200
    assert response.data["estado"] == OrdenCompra.Estado.ACEPTADA
    assert response.data["revisado_por"] == panolero_compras.id
    assert list(
        Unidad.objects.filter(tipo_equipo=tipo_equipo).values_list(
            "codigo_activo",
            "estado",
            "situacion",
        )
    ) == [
        ("OSC-001", Unidad.Estado.BUENO, Unidad.Situacion.DISPONIBLE),
        ("OSC-002", Unidad.Estado.BUENO, Unidad.Situacion.DISPONIBLE),
    ]


@pytest.mark.django_db
def test_aceptar_orden_compra_granel_suma_stock(api_client, panolero_compras):
    tipo_equipo = TipoEquipo.objects.create(
        nombre="Tornillo M3",
        tipo_seguimiento=TipoEquipo.TipoSeguimiento.GRANEL,
        stock_granel=4,
    )
    orden_compra = OrdenCompra.objects.create(
        numero="OC-GRANEL",
        proveedor="Proveedor",
        estado=OrdenCompra.Estado.EN_REVISION,
    )
    orden_compra.items.create(tipo_equipo=tipo_equipo, cantidad=6)
    api_client.force_authenticate(user=panolero_compras)

    response = api_client.post(f"/api/ordenes-compra/{orden_compra.id}/aceptar/")

    tipo_equipo.refresh_from_db()
    assert response.status_code == 200
    assert response.data["estado"] == OrdenCompra.Estado.ACEPTADA
    assert tipo_equipo.stock_granel == 10
    assert Unidad.objects.count() == 0


@pytest.mark.django_db
def test_aceptar_orden_compra_con_codigo_existente_no_modifica_nada(
    api_client,
    panolero_compras,
):
    tipo_equipo = TipoEquipo.objects.create(
        nombre="Multímetro",
        tipo_seguimiento=TipoEquipo.TipoSeguimiento.SERIE,
    )
    Unidad.objects.create(tipo_equipo=tipo_equipo, codigo_activo="MUL-001")
    orden_compra = OrdenCompra.objects.create(
        numero="OC-DUP",
        proveedor="Proveedor",
        estado=OrdenCompra.Estado.EN_REVISION,
    )
    orden_compra.items.create(
        tipo_equipo=tipo_equipo,
        cantidad=2,
        codigos_activo="MUL-001\nMUL-002",
    )
    api_client.force_authenticate(user=panolero_compras)

    response = api_client.post(f"/api/ordenes-compra/{orden_compra.id}/aceptar/")

    orden_compra.refresh_from_db()
    assert response.status_code == 400
    assert orden_compra.estado == OrdenCompra.Estado.EN_REVISION
    assert set(Unidad.objects.values_list("codigo_activo", flat=True)) == {"MUL-001"}


@pytest.mark.django_db
def test_aceptar_orden_compra_invalida_no_modifica_stock_granel(
    api_client,
    panolero_compras,
):
    tipo_granel = TipoEquipo.objects.create(
        nombre="Amarras",
        tipo_seguimiento=TipoEquipo.TipoSeguimiento.GRANEL,
        stock_granel=5,
    )
    tipo_serie = TipoEquipo.objects.create(
        nombre="Fuente DC",
        tipo_seguimiento=TipoEquipo.TipoSeguimiento.SERIE,
    )
    orden_compra = OrdenCompra.objects.create(
        numero="OC-ROLLBACK",
        proveedor="Proveedor",
        estado=OrdenCompra.Estado.EN_REVISION,
    )
    orden_compra.items.create(tipo_equipo=tipo_granel, cantidad=4)
    orden_compra.items.create(
        tipo_equipo=tipo_serie,
        cantidad=2,
        codigos_activo="FDC-001",
    )
    api_client.force_authenticate(user=panolero_compras)

    response = api_client.post(f"/api/ordenes-compra/{orden_compra.id}/aceptar/")

    tipo_granel.refresh_from_db()
    orden_compra.refresh_from_db()
    assert response.status_code == 400
    assert tipo_granel.stock_granel == 5
    assert orden_compra.estado == OrdenCompra.Estado.EN_REVISION
    assert Unidad.objects.count() == 0


@pytest.mark.django_db
def test_rechazar_orden_compra_registra_observacion(api_client, panolero_compras):
    orden_compra = OrdenCompra.objects.create(
        numero="OC-RECH",
        proveedor="Proveedor",
        estado=OrdenCompra.Estado.EN_REVISION,
    )
    api_client.force_authenticate(user=panolero_compras)

    response = api_client.post(
        f"/api/ordenes-compra/{orden_compra.id}/rechazar/",
        {"observaciones": "Proveedor no cumple especificación."},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["estado"] == OrdenCompra.Estado.RECHAZADA
    assert response.data["observaciones"] == "Proveedor no cumple especificación."
    assert response.data["revisado_por"] == panolero_compras.id
