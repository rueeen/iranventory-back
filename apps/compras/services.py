from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.catalogo.models import TipoEquipo
from apps.inventario.models import Unidad

from .models import EntradaInventario, LineaEntradaInventario


@transaction.atomic
def enviar_a_revision(entrada: EntradaInventario, usuario=None) -> EntradaInventario:
    entrada = EntradaInventario.objects.select_for_update().get(pk=entrada.pk)
    if entrada.estado != EntradaInventario.Estado.REGISTRADA:
        raise ValidationError(
            "Solo las entradas registradas pueden enviarse a revisión."
        )

    if not entrada.lineas.exists():
        raise ValidationError(
            "La entrada debe tener al menos una línea para revisarse."
        )

    entrada.estado = EntradaInventario.Estado.EN_REVISION
    entrada.revisada_por = usuario
    entrada.fecha_revision = timezone.now()
    entrada.save(update_fields=["estado", "revisada_por", "fecha_revision"])
    return entrada


@transaction.atomic
def aceptar_entrada(entrada: EntradaInventario, usuario=None) -> EntradaInventario:
    entrada = EntradaInventario.objects.select_for_update().get(pk=entrada.pk)
    if entrada.estado != EntradaInventario.Estado.EN_REVISION:
        raise ValidationError("Solo las entradas en revisión pueden aceptarse.")

    lineas = list(
        LineaEntradaInventario.objects.select_related("tipo_equipo", "ubicacion")
        .select_for_update()
        .filter(entrada=entrada)
    )
    if not lineas:
        raise ValidationError(
            "La entrada debe tener al menos una línea para aceptarse."
        )

    for linea in lineas:
        linea.full_clean()
        if linea.tipo_equipo.tipo_seguimiento == TipoEquipo.TipoSeguimiento.SERIE:
            _crear_unidades(linea)
        else:
            _sumar_stock_granel(linea)

    entrada.estado = EntradaInventario.Estado.ACEPTADA
    entrada.aceptada_por = usuario
    entrada.fecha_aceptacion = timezone.now()
    entrada.save(update_fields=["estado", "aceptada_por", "fecha_aceptacion"])
    return entrada


@transaction.atomic
def rechazar_entrada(entrada: EntradaInventario, usuario=None) -> EntradaInventario:
    entrada = EntradaInventario.objects.select_for_update().get(pk=entrada.pk)
    if entrada.estado != EntradaInventario.Estado.EN_REVISION:
        raise ValidationError("Solo las entradas en revisión pueden rechazarse.")

    entrada.estado = EntradaInventario.Estado.RECHAZADA
    entrada.revisada_por = usuario or entrada.revisada_por
    entrada.fecha_revision = entrada.fecha_revision or timezone.now()
    entrada.save(update_fields=["estado", "revisada_por", "fecha_revision"])
    return entrada


def _crear_unidades(linea: LineaEntradaInventario) -> None:
    unidades = [
        Unidad(
            tipo_equipo=linea.tipo_equipo,
            codigo_activo=codigo,
            ubicacion=linea.ubicacion or linea.tipo_equipo.ubicacion_default,
        )
        for codigo in linea.codigos_activo
    ]
    Unidad.objects.bulk_create(unidades)


def _sumar_stock_granel(linea: LineaEntradaInventario) -> None:
    TipoEquipo.objects.select_for_update().filter(pk=linea.tipo_equipo_id).update(
        stock_granel=F("stock_granel") + linea.cantidad,
    )
