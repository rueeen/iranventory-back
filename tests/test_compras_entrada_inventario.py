"""
Tests de servicio para el módulo de compras.
Cubre el flujo completo: BORRADOR → EN_REVISION → ACEPTADA
con recepción total, parcial y nula de ítems.
"""
import pytest

from apps.catalogo.models import TipoEquipo
from apps.compras.models import ItemOrdenCompra, OrdenCompra
from apps.compras.services import aceptar_orden_compra, enviar_revision
from apps.inventario.models import Unidad


# ──────────────────────────── fixtures ────────────────────────────────────────

@pytest.fixture
def tipo_serie(db):
    return TipoEquipo.objects.create(
        nombre="Osciloscopio",
        tipo_seguimiento=TipoEquipo.TipoSeguimiento.SERIE,
    )


@pytest.fixture
def tipo_granel(db):
    return TipoEquipo.objects.create(
        nombre="Tornillos M3",
        tipo_seguimiento=TipoEquipo.TipoSeguimiento.GRANEL,
        stock_granel=5,
    )


@pytest.fixture
def oc(db):
    return OrdenCompra.objects.create(numero="OC-2026-001", proveedor="Proveedor SA")


# ──────────────────────────── flujo básico ────────────────────────────────────

@pytest.mark.django_db
def test_enviar_revision_cambia_estado(oc, tipo_serie):
    ItemOrdenCompra.objects.create(
        orden_compra=oc, tipo_equipo=tipo_serie, cantidad_solicitada=2
    )
    enviar_revision(oc)
    oc.refresh_from_db()
    assert oc.estado == OrdenCompra.Estado.EN_REVISION


@pytest.mark.django_db
def test_enviar_revision_sin_items_falla(oc):
    from django.core.exceptions import ValidationError
    with pytest.raises(ValidationError, match="al menos un ítem"):
        enviar_revision(oc)


# ──────────────────────────── recepción total ─────────────────────────────────

@pytest.mark.django_db
def test_aceptar_serie_recepcion_total_crea_unidades(oc, tipo_serie):
    ItemOrdenCompra.objects.create(
        orden_compra=oc,
        tipo_equipo=tipo_serie,
        cantidad_solicitada=2,
        cantidad_recibida=2,
        codigos_activo=["OSC-001", "OSC-002"],
    )
    enviar_revision(oc)
    aceptar_orden_compra(oc)

    oc.refresh_from_db()
    assert oc.estado == OrdenCompra.Estado.ACEPTADA
    codigos = list(
        Unidad.objects.filter(tipo_equipo=tipo_serie)
        .values_list("codigo_activo", flat=True)
        .order_by("codigo_activo")
    )
    assert codigos == ["OSC-001", "OSC-002"]


@pytest.mark.django_db
def test_aceptar_granel_recepcion_total_suma_stock(oc, tipo_granel):
    ItemOrdenCompra.objects.create(
        orden_compra=oc,
        tipo_equipo=tipo_granel,
        cantidad_solicitada=7,
        cantidad_recibida=7,
    )
    enviar_revision(oc)
    aceptar_orden_compra(oc)

    tipo_granel.refresh_from_db()
    assert tipo_granel.stock_granel == 12  # 5 + 7


# ──────────────────────────── recepción parcial ───────────────────────────────

@pytest.mark.django_db
def test_aceptar_serie_recepcion_parcial_crea_solo_recibidos(oc, tipo_serie):
    ItemOrdenCompra.objects.create(
        orden_compra=oc,
        tipo_equipo=tipo_serie,
        cantidad_solicitada=3,
        cantidad_recibida=2,
        codigos_activo=["OSC-001", "OSC-002"],
    )
    enviar_revision(oc)
    aceptar_orden_compra(oc)

    assert Unidad.objects.filter(tipo_equipo=tipo_serie).count() == 2


@pytest.mark.django_db
def test_aceptar_granel_recepcion_parcial_suma_solo_recibidos(oc, tipo_granel):
    ItemOrdenCompra.objects.create(
        orden_compra=oc,
        tipo_equipo=tipo_granel,
        cantidad_solicitada=10,
        cantidad_recibida=4,
    )
    enviar_revision(oc)
    aceptar_orden_compra(oc)

    tipo_granel.refresh_from_db()
    assert tipo_granel.stock_granel == 9  # 5 + 4


# ──────────────────────────── recepción nula ──────────────────────────────────

@pytest.mark.django_db
def test_aceptar_item_no_recibido_no_toca_stock(oc, tipo_granel):
    ItemOrdenCompra.objects.create(
        orden_compra=oc,
        tipo_equipo=tipo_granel,
        cantidad_solicitada=10,
        cantidad_recibida=0,
    )
    enviar_revision(oc)
    aceptar_orden_compra(oc)

    tipo_granel.refresh_from_db()
    assert tipo_granel.stock_granel == 5  # sin cambio


@pytest.mark.django_db
def test_aceptar_serie_no_recibida_no_crea_unidades(oc, tipo_serie):
    ItemOrdenCompra.objects.create(
        orden_compra=oc,
        tipo_equipo=tipo_serie,
        cantidad_solicitada=3,
        cantidad_recibida=0,
        codigos_activo=[],
    )
    enviar_revision(oc)
    aceptar_orden_compra(oc)

    assert Unidad.objects.filter(tipo_equipo=tipo_serie).count() == 0


# ──────────────────────────── validaciones ────────────────────────────────────

@pytest.mark.django_db
def test_aceptar_serie_codigos_insuficientes_falla(oc, tipo_serie):
    from django.core.exceptions import ValidationError
    ItemOrdenCompra.objects.create(
        orden_compra=oc,
        tipo_equipo=tipo_serie,
        cantidad_solicitada=3,
        cantidad_recibida=3,
        codigos_activo=["OSC-001", "OSC-002"],  # falta uno
    )
    enviar_revision(oc)
    with pytest.raises(ValidationError, match="exactamente 3"):
        aceptar_orden_compra(oc)


@pytest.mark.django_db
def test_aceptar_serie_codigos_repetidos_falla(oc, tipo_serie):
    from django.core.exceptions import ValidationError
    ItemOrdenCompra.objects.create(
        orden_compra=oc,
        tipo_equipo=tipo_serie,
        cantidad_solicitada=2,
        cantidad_recibida=2,
        codigos_activo=["OSC-001", "OSC-001"],
    )
    enviar_revision(oc)
    with pytest.raises(ValidationError, match="repetidos"):
        aceptar_orden_compra(oc)


@pytest.mark.django_db
def test_cantidad_recibida_supera_solicitada_falla(oc, tipo_granel):
    from django.core.exceptions import ValidationError
    with pytest.raises(ValidationError, match="no puede superar"):
        ItemOrdenCompra.objects.create(
            orden_compra=oc,
            tipo_equipo=tipo_granel,
            cantidad_solicitada=3,
            cantidad_recibida=5,
        )


@pytest.mark.django_db
def test_pendiente_property(oc, tipo_granel):
    item = ItemOrdenCompra(
        orden_compra=oc,
        tipo_equipo=tipo_granel,
        cantidad_solicitada=10,
        cantidad_recibida=3,
    )
    assert item.pendiente == 7
