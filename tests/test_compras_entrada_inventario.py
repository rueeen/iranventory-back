import pytest

from apps.catalogo.models import TipoEquipo
from apps.compras.models import EntradaInventario, LineaEntradaInventario
from apps.compras.services import aceptar_entrada, enviar_a_revision
from apps.inventario.models import Unidad


@pytest.mark.django_db
def test_aceptar_entrada_por_serie_crea_unidades_con_codigos():
    tipo_equipo = TipoEquipo.objects.create(
        nombre="Osciloscopio",
        tipo_seguimiento=TipoEquipo.TipoSeguimiento.SERIE,
    )
    entrada = EntradaInventario.objects.create(numero_documento="OC-100")
    LineaEntradaInventario.objects.create(
        entrada=entrada,
        tipo_equipo=tipo_equipo,
        cantidad=2,
        codigos_activo=["OSC-001", "OSC-002"],
    )

    enviar_a_revision(entrada)
    aceptar_entrada(entrada)

    entrada.refresh_from_db()
    assert entrada.estado == EntradaInventario.Estado.ACEPTADA
    assert list(
        Unidad.objects.filter(tipo_equipo=tipo_equipo).values_list(
            "codigo_activo",
            flat=True,
        )
    ) == ["OSC-001", "OSC-002"]


@pytest.mark.django_db
def test_aceptar_entrada_granel_suma_stock_sin_fifo():
    tipo_equipo = TipoEquipo.objects.create(
        nombre="Tornillos M3",
        tipo_seguimiento=TipoEquipo.TipoSeguimiento.GRANEL,
        stock_granel=5,
    )
    entrada = EntradaInventario.objects.create(numero_documento="OC-101")
    LineaEntradaInventario.objects.create(
        entrada=entrada,
        tipo_equipo=tipo_equipo,
        cantidad=7,
    )

    enviar_a_revision(entrada)
    aceptar_entrada(entrada)

    tipo_equipo.refresh_from_db()
    assert tipo_equipo.stock_granel == 12
