"""
Tests de API para el módulo de compras.
Verifica permisos, creación, transiciones de estado y recepción parcial.
"""
import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.catalogo.models import TipoEquipo
from apps.compras.models import ItemOrdenCompra, OrdenCompra
from apps.cuentas.models import Usuario
from apps.inventario.models import Unidad


# ──────────────────────────── fixtures ────────────────────────────────────────

@pytest.fixture
def alumno(db):
    return get_user_model().objects.create_user(
        username="alumno-api", password="clave-123", rol=Usuario.Rol.ALUMNO
    )


@pytest.fixture
def panolero(db):
    return get_user_model().objects.create_user(
        username="panolero-api", password="clave-123", rol=Usuario.Rol.PANOLERO
    )


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def tipo_serie(db):
    return TipoEquipo.objects.create(
        nombre="Osciloscopio", tipo_seguimiento=TipoEquipo.TipoSeguimiento.SERIE
    )


@pytest.fixture
def tipo_granel(db):
    return TipoEquipo.objects.create(
        nombre="Tornillo M3",
        tipo_seguimiento=TipoEquipo.TipoSeguimiento.GRANEL,
        stock_granel=4,
    )


# ──────────────────────────── permisos ────────────────────────────────────────

@pytest.mark.django_db
def test_alumno_puede_listar_no_crear(client, alumno):
    OrdenCompra.objects.create(numero="OC-LECTURA", proveedor="Proveedor")
    client.force_authenticate(user=alumno)

    assert client.get("/api/ordenes-compra/").status_code == 200
    assert (
        client.post(
            "/api/ordenes-compra/",
            {"numero": "OC-BLOQ", "proveedor": "X"},
            format="json",
        ).status_code
        == 403
    )


# ──────────────────────────── creación ────────────────────────────────────────

@pytest.mark.django_db
def test_panolero_crea_oc_con_items(client, panolero, tipo_serie):
    client.force_authenticate(user=panolero)

    r = client.post(
        "/api/ordenes-compra/",
        {
            "numero": "OC-2026-001",
            "proveedor": "Proveedor SA",
            "items": [
                {
                    "tipo_equipo_id": tipo_serie.id,
                    "cantidad_solicitada": 2,
                }
            ],
        },
        format="json",
    )

    assert r.status_code == 201
    assert r.data["estado"] == OrdenCompra.Estado.BORRADOR
    assert r.data["creado_por"] == panolero.id
    assert r.data["items"][0]["tipo_equipo"]["nombre"] == "Osciloscopio"
    assert r.data["items"][0]["pendiente"] == 2


# ──────────────────────────── enviar a revisión ───────────────────────────────

@pytest.mark.django_db
def test_panolero_envia_oc_a_revision(client, panolero, tipo_granel):
    oc = OrdenCompra.objects.create(numero="OC-REV", proveedor="Proveedor")
    ItemOrdenCompra.objects.create(
        orden_compra=oc, tipo_equipo=tipo_granel, cantidad_solicitada=5
    )
    client.force_authenticate(user=panolero)

    r = client.post(f"/api/ordenes-compra/{oc.id}/enviar-revision/")

    assert r.status_code == 200
    assert r.data["estado"] == OrdenCompra.Estado.EN_REVISION
    assert r.data["revisado_por"] == panolero.id
    assert r.data["fecha_revision"] is not None


@pytest.mark.django_db
def test_enviar_revision_sin_items_devuelve_400(client, panolero):
    oc = OrdenCompra.objects.create(numero="OC-VACIA", proveedor="Proveedor")
    client.force_authenticate(user=panolero)

    r = client.post(f"/api/ordenes-compra/{oc.id}/enviar-revision/")
    assert r.status_code == 400


# ──────────────────────────── aceptar ────────────────────────────────────────

@pytest.mark.django_db
def test_aceptar_oc_serie_recepcion_total(client, panolero, tipo_serie):
    oc = OrdenCompra.objects.create(
        numero="OC-SERIE", proveedor="P", estado=OrdenCompra.Estado.EN_REVISION
    )
    ItemOrdenCompra.objects.create(
        orden_compra=oc,
        tipo_equipo=tipo_serie,
        cantidad_solicitada=2,
        cantidad_recibida=2,
        codigos_activo=["OSC-001", "OSC-002"],
    )
    client.force_authenticate(user=panolero)

    r = client.post(f"/api/ordenes-compra/{oc.id}/aceptar/")

    assert r.status_code == 200
    assert r.data["estado"] == OrdenCompra.Estado.ACEPTADA
    codigos = list(
        Unidad.objects.values_list(
            "codigo_activo", flat=True).order_by("codigo_activo")
    )
    assert codigos == ["OSC-001", "OSC-002"]


@pytest.mark.django_db
def test_aceptar_oc_serie_recepcion_parcial(client, panolero, tipo_serie):
    oc = OrdenCompra.objects.create(
        numero="OC-PARCIAL", proveedor="P", estado=OrdenCompra.Estado.EN_REVISION
    )
    ItemOrdenCompra.objects.create(
        orden_compra=oc,
        tipo_equipo=tipo_serie,
        cantidad_solicitada=3,
        cantidad_recibida=2,
        codigos_activo=["OSC-001", "OSC-002"],
    )
    client.force_authenticate(user=panolero)

    r = client.post(f"/api/ordenes-compra/{oc.id}/aceptar/")

    assert r.status_code == 200
    assert Unidad.objects.count() == 2
    assert r.data["items"][0]["pendiente"] == 1


@pytest.mark.django_db
def test_aceptar_oc_granel_suma_recibido(client, panolero, tipo_granel):
    oc = OrdenCompra.objects.create(
        numero="OC-GRAN", proveedor="P", estado=OrdenCompra.Estado.EN_REVISION
    )
    ItemOrdenCompra.objects.create(
        orden_compra=oc,
        tipo_equipo=tipo_granel,
        cantidad_solicitada=10,
        cantidad_recibida=6,
    )
    client.force_authenticate(user=panolero)

    r = client.post(f"/api/ordenes-compra/{oc.id}/aceptar/")

    tipo_granel.refresh_from_db()
    assert r.status_code == 200
    assert tipo_granel.stock_granel == 10  # 4 + 6


@pytest.mark.django_db
def test_aceptar_item_no_recibido_no_toca_stock(client, panolero, tipo_granel):
    oc = OrdenCompra.objects.create(
        numero="OC-NOREC", proveedor="P", estado=OrdenCompra.Estado.EN_REVISION
    )
    ItemOrdenCompra.objects.create(
        orden_compra=oc,
        tipo_equipo=tipo_granel,
        cantidad_solicitada=10,
        cantidad_recibida=0,
    )
    client.force_authenticate(user=panolero)

    client.post(f"/api/ordenes-compra/{oc.id}/aceptar/")
    tipo_granel.refresh_from_db()
    assert tipo_granel.stock_granel == 4


@pytest.mark.django_db
def test_aceptar_codigo_duplicado_existente_hace_rollback(
    client, panolero, tipo_serie
):
    Unidad.objects.create(tipo_equipo=tipo_serie, codigo_activo="OSC-001")
    oc = OrdenCompra.objects.create(
        numero="OC-DUP", proveedor="P", estado=OrdenCompra.Estado.EN_REVISION
    )
    ItemOrdenCompra.objects.create(
        orden_compra=oc,
        tipo_equipo=tipo_serie,
        cantidad_solicitada=2,
        cantidad_recibida=2,
        codigos_activo=["OSC-001", "OSC-002"],
    )
    client.force_authenticate(user=panolero)

    r = client.post(f"/api/ordenes-compra/{oc.id}/aceptar/")

    oc.refresh_from_db()
    assert r.status_code == 400
    assert oc.estado == OrdenCompra.Estado.EN_REVISION
    assert Unidad.objects.count() == 1  # solo la preexistente


# ──────────────────────────── rechazar ───────────────────────────────────────

@pytest.mark.django_db
def test_rechazar_oc_registra_observacion(client, panolero):
    oc = OrdenCompra.objects.create(
        numero="OC-RECH", proveedor="P", estado=OrdenCompra.Estado.EN_REVISION
    )
    client.force_authenticate(user=panolero)

    r = client.post(
        f"/api/ordenes-compra/{oc.id}/rechazar/",
        {"observaciones": "Proveedor no cumple especificación."},
        format="json",
    )

    assert r.status_code == 200
    assert r.data["estado"] == OrdenCompra.Estado.RECHAZADA
    assert r.data["observaciones"] == "Proveedor no cumple especificación."
    assert r.data["revisado_por"] == panolero.id


# ──────────────────────────── filtros ────────────────────────────────────────

@pytest.mark.django_db
def test_filtro_items_por_tipo_equipo(client, alumno, tipo_serie, tipo_granel):
    oc = OrdenCompra.objects.create(numero="OC-FILT", proveedor="P")
    item_serie = ItemOrdenCompra.objects.create(
        orden_compra=oc, tipo_equipo=tipo_serie, cantidad_solicitada=1
    )
    ItemOrdenCompra.objects.create(
        orden_compra=oc, tipo_equipo=tipo_granel, cantidad_solicitada=5
    )
    client.force_authenticate(user=alumno)

    r = client.get("/api/items-orden-compra/", {"tipo_equipo": tipo_serie.id})

    assert r.status_code == 200
    assert [i["id"] for i in r.data["results"]] == [item_serie.id]
