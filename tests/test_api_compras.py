"""
Tests de API para el módulo de compras.
Verifica permisos, creación, transiciones de estado y recepción parcial.
"""
import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.catalogo.models import TipoEquipo
from apps.compras.models import ItemOrdenCompra, OrdenCompra, Proveedor
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
def director(db):
    return get_user_model().objects.create_user(
        username="director-api", password="clave-123", rol=Usuario.Rol.DIRECTOR
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
def test_alumno_no_puede_listar_ni_crear_oc(client, alumno):
    OrdenCompra.objects.create(numero="OC-LECTURA")
    client.force_authenticate(user=alumno)

    assert client.get("/api/ordenes-compra/").status_code == 403
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
    oc = OrdenCompra.objects.create(numero="OC-REV")
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
    oc = OrdenCompra.objects.create(numero="OC-VACIA")
    client.force_authenticate(user=panolero)

    r = client.post(f"/api/ordenes-compra/{oc.id}/enviar-revision/")
    assert r.status_code == 400


# ──────────────────────────── aceptar ────────────────────────────────────────

@pytest.mark.django_db
def test_panolero_no_puede_aceptar_oc(client, panolero, tipo_granel):
    oc = OrdenCompra.objects.create(
        numero="OC-PAN-403", estado=OrdenCompra.Estado.EN_REVISION
    )
    ItemOrdenCompra.objects.create(
        orden_compra=oc,
        tipo_equipo=tipo_granel,
        cantidad_solicitada=1,
        cantidad_recibida=1,
    )
    client.force_authenticate(user=panolero)

    r = client.post(f"/api/ordenes-compra/{oc.id}/aceptar/")

    oc.refresh_from_db()
    tipo_granel.refresh_from_db()
    assert r.status_code == 403
    assert oc.estado == OrdenCompra.Estado.EN_REVISION
    assert tipo_granel.stock_granel == 4


@pytest.mark.django_db
def test_aceptar_oc_serie_recepcion_total(client, director, tipo_serie):
    oc = OrdenCompra.objects.create(
        numero="OC-SERIE", estado=OrdenCompra.Estado.EN_REVISION
    )
    ItemOrdenCompra.objects.create(
        orden_compra=oc,
        tipo_equipo=tipo_serie,
        cantidad_solicitada=2,
        cantidad_recibida=2,
        codigos_activo=["OSC-001", "OSC-002"],
    )
    client.force_authenticate(user=director)

    r = client.post(f"/api/ordenes-compra/{oc.id}/aceptar/")

    assert r.status_code == 200
    assert r.data["estado"] == OrdenCompra.Estado.ACEPTADA
    codigos = list(
        Unidad.objects.values_list(
            "codigo_activo", flat=True).order_by("codigo_activo")
    )
    assert codigos == ["OSC-001", "OSC-002"]


@pytest.mark.django_db
def test_aceptar_oc_serie_recepcion_parcial(client, director, tipo_serie):
    oc = OrdenCompra.objects.create(
        numero="OC-PARCIAL", estado=OrdenCompra.Estado.EN_REVISION
    )
    ItemOrdenCompra.objects.create(
        orden_compra=oc,
        tipo_equipo=tipo_serie,
        cantidad_solicitada=3,
        cantidad_recibida=2,
        codigos_activo=["OSC-001", "OSC-002"],
    )
    client.force_authenticate(user=director)

    r = client.post(f"/api/ordenes-compra/{oc.id}/aceptar/")

    assert r.status_code == 200
    assert Unidad.objects.count() == 2
    assert r.data["items"][0]["pendiente"] == 1


@pytest.mark.django_db
def test_aceptar_oc_granel_suma_recibido(client, director, tipo_granel):
    oc = OrdenCompra.objects.create(
        numero="OC-GRAN", estado=OrdenCompra.Estado.EN_REVISION
    )
    ItemOrdenCompra.objects.create(
        orden_compra=oc,
        tipo_equipo=tipo_granel,
        cantidad_solicitada=10,
        cantidad_recibida=6,
    )
    client.force_authenticate(user=director)

    r = client.post(f"/api/ordenes-compra/{oc.id}/aceptar/")

    tipo_granel.refresh_from_db()
    assert r.status_code == 200
    assert tipo_granel.stock_granel == 10  # 4 + 6


@pytest.mark.django_db
def test_aceptar_item_no_recibido_no_toca_stock(client, director, tipo_granel):
    oc = OrdenCompra.objects.create(
        numero="OC-NOREC", estado=OrdenCompra.Estado.EN_REVISION
    )
    ItemOrdenCompra.objects.create(
        orden_compra=oc,
        tipo_equipo=tipo_granel,
        cantidad_solicitada=10,
        cantidad_recibida=0,
    )
    client.force_authenticate(user=director)

    client.post(f"/api/ordenes-compra/{oc.id}/aceptar/")
    tipo_granel.refresh_from_db()
    assert tipo_granel.stock_granel == 4


@pytest.mark.django_db
def test_aceptar_codigo_duplicado_existente_hace_rollback(
    client, director, tipo_serie
):
    Unidad.objects.create(tipo_equipo=tipo_serie, codigo_activo="OSC-001")
    oc = OrdenCompra.objects.create(
        numero="OC-DUP", estado=OrdenCompra.Estado.EN_REVISION
    )
    ItemOrdenCompra.objects.create(
        orden_compra=oc,
        tipo_equipo=tipo_serie,
        cantidad_solicitada=2,
        cantidad_recibida=2,
        codigos_activo=["OSC-001", "OSC-002"],
    )
    client.force_authenticate(user=director)

    r = client.post(f"/api/ordenes-compra/{oc.id}/aceptar/")

    oc.refresh_from_db()
    assert r.status_code == 400
    assert oc.estado == OrdenCompra.Estado.EN_REVISION
    assert Unidad.objects.count() == 1  # solo la preexistente


# ──────────────────────────── rechazar ───────────────────────────────────────

@pytest.mark.django_db
def test_rechazar_oc_registra_observacion(client, director):
    oc = OrdenCompra.objects.create(
        numero="OC-RECH", estado=OrdenCompra.Estado.EN_REVISION
    )
    client.force_authenticate(user=director)

    r = client.post(
        f"/api/ordenes-compra/{oc.id}/rechazar/",
        {"observaciones": "Proveedor no cumple especificación."},
        format="json",
    )

    assert r.status_code == 200
    assert r.data["estado"] == OrdenCompra.Estado.RECHAZADA
    assert r.data["observaciones"] == "Proveedor no cumple especificación."
    assert r.data["revisado_por"] == director.id


# ──────────────────────────── filtros ────────────────────────────────────────

@pytest.mark.django_db
def test_filtro_items_por_tipo_equipo(client, panolero, tipo_serie, tipo_granel):
    oc = OrdenCompra.objects.create(numero="OC-FILT")
    item_serie = ItemOrdenCompra.objects.create(
        orden_compra=oc, tipo_equipo=tipo_serie, cantidad_solicitada=1
    )
    ItemOrdenCompra.objects.create(
        orden_compra=oc, tipo_equipo=tipo_granel, cantidad_solicitada=5
    )
    client.force_authenticate(user=panolero)

    r = client.get("/api/items-orden-compra/", {"tipo_equipo": tipo_serie.id})

    assert r.status_code == 200
    assert [i["id"] for i in r.data["results"]] == [item_serie.id]


@pytest.mark.django_db
def test_alumno_no_puede_listar_items_oc(client, alumno, tipo_serie):
    oc = OrdenCompra.objects.create(numero="OC-ITEM-403")
    ItemOrdenCompra.objects.create(
        orden_compra=oc, tipo_equipo=tipo_serie, cantidad_solicitada=1
    )
    client.force_authenticate(user=alumno)

    r = client.get("/api/items-orden-compra/")

    assert r.status_code == 403


@pytest.fixture
def proveedor(db):
    return Proveedor.objects.create(
        razon_social="Proveedor INACAP SpA",
        rut="76269680-0",
        ciudad="Santiago",
    )


@pytest.mark.django_db
def test_panolero_crea_oc_con_proveedor_id_y_montos(
    client, panolero, tipo_serie, tipo_granel, proveedor
):
    client.force_authenticate(user=panolero)

    r = client.post(
        "/api/ordenes-compra/",
        {
            "proveedor_id": proveedor.id,
            "numero_inacap": "IPN123456",
            "fecha_publicacion": "2026-06-01",
            "fecha_emision": "2026-06-02",
            "sede_destino": "Sede Santiago Sur",
            "direccion_despacho": "Av. Siempre Viva 123",
            "recibido_por_nombre": "Receptor Uno",
            "comprador_nombre": "Comprador Uno",
            "referencia_pedido": "REQ-42",
            "codigo_inversion": "INV-2026",
            "descuentos": "100.50",
            "items": [
                {
                    "tipo_equipo_id": tipo_serie.id,
                    "codigo_material": "MAT-OSC",
                    "unidad_medida": "UNI",
                    "precio_unitario": "1000.25",
                    "cantidad_solicitada": 2,
                },
                {
                    "tipo_equipo_id": tipo_granel.id,
                    "codigo_material": "MAT-TOR",
                    "precio_unitario": "333.33",
                    "cantidad_solicitada": 3,
                },
            ],
        },
        format="json",
    )

    assert r.status_code == 201
    assert r.data["proveedor"]["id"] == proveedor.id
    assert r.data["proveedor"]["rut"] == "76.269.680-0"
    assert r.data["numero_inacap"] == "IPN123456"
    assert r.data["subtotal_neto"] == "3000.49"
    assert r.data["monto_afecto"] == "2899.99"
    assert r.data["iva"] == "551"
    assert r.data["total_general"] == "3451"
    assert r.data["items"][0]["total_linea"] == "2000.50"


@pytest.mark.django_db
def test_crud_basico_proveedor_y_validacion_rut(client, panolero):
    client.force_authenticate(user=panolero)

    creado = client.post(
        "/api/proveedores/",
        {
            "razon_social": "Tecnologías Chile Ltda",
            "rut": "76123456-k",
            "direccion": "Los Alerces 100",
            "ciudad": "Santiago",
            "contacto_nombre": "Ana Pérez",
            "contacto_telefono": "+56 9 1234 5678",
            "email": "ana@example.com",
        },
        format="json",
    )

    assert creado.status_code == 201
    assert creado.data["rut"] == "76.123.456-K"

    listado = client.get("/api/proveedores/", {"search": "76.123"})
    assert listado.status_code == 200
    assert listado.data["results"][0]["id"] == creado.data["id"]

    actualizado = client.patch(
        f"/api/proveedores/{creado.data['id']}/",
        {"activo": False},
        format="json",
    )
    assert actualizado.status_code == 200
    assert actualizado.data["activo"] is False

    invalido = client.post(
        "/api/proveedores/",
        {"razon_social": "Proveedor Inválido", "rut": "no-es-rut"},
        format="json",
    )
    assert invalido.status_code == 400
    assert "rut" in invalido.data
