import pytest

from apps.catalogo.models import TipoEquipo
from apps.inventario.models import Unidad


@pytest.mark.django_db
def test_stock_tipo_equipo_por_serie_excluye_unidades_de_baja():
    tipo_equipo = TipoEquipo.objects.create(
        nombre="Osciloscopio",
        tipo_seguimiento=TipoEquipo.TipoSeguimiento.SERIE,
        cantidad_necesaria=4,
    )
    Unidad.objects.create(tipo_equipo=tipo_equipo, codigo_activo="OSC-001")
    Unidad.objects.create(tipo_equipo=tipo_equipo, codigo_activo="OSC-002")
    Unidad.objects.create(
        tipo_equipo=tipo_equipo,
        codigo_activo="OSC-003",
        situacion=Unidad.Situacion.BAJA,
    )

    assert tipo_equipo.stock_total == 2
    assert tipo_equipo.stock_disponible == 2
    assert tipo_equipo.brecha == 2


@pytest.mark.django_db
def test_brecha_usa_stock_total_y_no_sube_por_unidades_prestadas():
    tipo_equipo = TipoEquipo.objects.create(
        nombre="Multímetro",
        tipo_seguimiento=TipoEquipo.TipoSeguimiento.SERIE,
        cantidad_necesaria=4,
    )
    Unidad.objects.create(tipo_equipo=tipo_equipo, codigo_activo="MUL-001")
    Unidad.objects.create(tipo_equipo=tipo_equipo, codigo_activo="MUL-002")
    Unidad.objects.create(
        tipo_equipo=tipo_equipo,
        codigo_activo="MUL-003",
        situacion=Unidad.Situacion.PRESTADA,
    )

    assert tipo_equipo.stock_total == 3
    assert tipo_equipo.stock_disponible == 2
    assert tipo_equipo.brecha == 1


@pytest.mark.django_db
def test_stock_disponible_por_serie_solo_cuenta_unidades_disponibles_y_buenas():
    tipo_equipo = TipoEquipo.objects.create(
        nombre="Fuente de poder",
        tipo_seguimiento=TipoEquipo.TipoSeguimiento.SERIE,
    )
    Unidad.objects.create(tipo_equipo=tipo_equipo, codigo_activo="FDP-001")
    Unidad.objects.create(
        tipo_equipo=tipo_equipo,
        codigo_activo="FDP-002",
        estado=Unidad.Estado.REPARABLE,
    )
    Unidad.objects.create(
        tipo_equipo=tipo_equipo,
        codigo_activo="FDP-003",
        estado=Unidad.Estado.MALO,
    )
    Unidad.objects.create(
        tipo_equipo=tipo_equipo,
        codigo_activo="FDP-004",
        situacion=Unidad.Situacion.REPARACION,
    )

    assert tipo_equipo.stock_disponible == 1
