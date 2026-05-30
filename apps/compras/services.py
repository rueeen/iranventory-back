from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.catalogo.models import TipoEquipo
from apps.inventario.models import Unidad

from .models import ItemOrdenCompra, OrdenCompra


@transaction.atomic
def enviar_revision_orden_compra(orden_compra: OrdenCompra, usuario) -> OrdenCompra:
    orden_compra = OrdenCompra.objects.select_for_update().get(pk=orden_compra.pk)
    if orden_compra.estado != OrdenCompra.Estado.BORRADOR:
        raise ValidationError(
            "Solo las órdenes en borrador pueden enviarse a revisión."
        )

    orden_compra.estado = OrdenCompra.Estado.EN_REVISION
    orden_compra.revisado_por = usuario
    orden_compra.fecha_revision = timezone.now()
    orden_compra.save(
        update_fields=["estado", "revisado_por", "fecha_revision", "updated_at"]
    )
    return orden_compra


@transaction.atomic
def aceptar_orden_compra(orden_compra: OrdenCompra, usuario) -> OrdenCompra:
    orden_compra = OrdenCompra.objects.select_for_update().get(pk=orden_compra.pk)
    if orden_compra.estado != OrdenCompra.Estado.EN_REVISION:
        raise ValidationError("Solo las órdenes en revisión pueden aceptarse.")

    items = _obtener_items_bloqueados(orden_compra)
    if not items:
        raise ValidationError("La orden de compra debe tener al menos un ítem.")

    codigos_por_item = _validar_items_para_aceptacion(items)

    for item in items:
        if item.tipo_equipo.tipo_seguimiento == TipoEquipo.TipoSeguimiento.SERIE:
            _crear_unidades_desde_item(item, codigos_por_item[item.pk])
        else:
            _sumar_stock_granel(item)

    orden_compra.estado = OrdenCompra.Estado.ACEPTADA
    orden_compra.revisado_por = usuario
    orden_compra.fecha_revision = timezone.now()
    orden_compra.save(
        update_fields=["estado", "revisado_por", "fecha_revision", "updated_at"]
    )
    return orden_compra


@transaction.atomic
def rechazar_orden_compra(
    orden_compra: OrdenCompra,
    usuario,
    observacion_rechazo: str = "",
) -> OrdenCompra:
    orden_compra = OrdenCompra.objects.select_for_update().get(pk=orden_compra.pk)
    if orden_compra.estado != OrdenCompra.Estado.EN_REVISION:
        raise ValidationError("Solo las órdenes en revisión pueden rechazarse.")

    orden_compra.estado = OrdenCompra.Estado.RECHAZADA
    orden_compra.revisado_por = usuario
    orden_compra.fecha_revision = timezone.now()
    update_fields = ["estado", "revisado_por", "fecha_revision", "updated_at"]

    if observacion_rechazo:
        orden_compra.observaciones = observacion_rechazo
        update_fields.append("observaciones")

    orden_compra.save(update_fields=update_fields)
    return orden_compra


def _obtener_items_bloqueados(orden_compra: OrdenCompra) -> list[ItemOrdenCompra]:
    return list(
        ItemOrdenCompra.objects.select_for_update()
        .select_related("tipo_equipo", "tipo_equipo__ubicacion_default")
        .filter(orden_compra=orden_compra)
        .order_by("id")
    )


def _validar_items_para_aceptacion(
    items: list[ItemOrdenCompra],
) -> dict[int, list[str]]:
    codigos_por_item: dict[int, list[str]] = {}
    codigos_de_la_orden: set[str] = set()
    codigos_repetidos_en_orden: set[str] = set()

    for item in items:
        item.full_clean()
        if item.tipo_equipo.tipo_seguimiento != TipoEquipo.TipoSeguimiento.SERIE:
            continue

        codigos = _parsear_codigos_activo(item)
        codigos_por_item[item.pk] = codigos

        if len(codigos) != item.cantidad:
            raise ValidationError(
                {
                    "codigos_activo": (
                        f"El ítem {item.pk} debe tener exactamente "
                        f"{item.cantidad} código(s) de activo."
                    )
                }
            )

        codigos_repetidos_item = _obtener_repetidos(codigos)
        if codigos_repetidos_item:
            raise ValidationError(
                {
                    "codigos_activo": (
                        f"El ítem {item.pk} tiene códigos repetidos: "
                        f"{', '.join(sorted(codigos_repetidos_item))}."
                    )
                }
            )

        for codigo in codigos:
            if codigo in codigos_de_la_orden:
                codigos_repetidos_en_orden.add(codigo)
            codigos_de_la_orden.add(codigo)

    if codigos_repetidos_en_orden:
        raise ValidationError(
            {
                "codigos_activo": (
                    "Hay códigos repetidos entre ítems de la orden: "
                    f"{', '.join(sorted(codigos_repetidos_en_orden))}."
                )
            }
        )

    codigos_existentes = set(
        Unidad.objects.filter(codigo_activo__in=codigos_de_la_orden).values_list(
            "codigo_activo",
            flat=True,
        )
    )
    if codigos_existentes:
        raise ValidationError(
            {
                "codigos_activo": (
                    "Ya existen unidades con estos códigos de activo: "
                    f"{', '.join(sorted(codigos_existentes))}."
                )
            }
        )

    return codigos_por_item


def _parsear_codigos_activo(item: ItemOrdenCompra) -> list[str]:
    if not item.codigos_activo.strip():
        raise ValidationError(
            {"codigos_activo": f"El ítem {item.pk} requiere códigos de activo."}
        )

    codigos = [codigo.strip() for codigo in item.codigos_activo.splitlines()]
    if any(not codigo for codigo in codigos):
        raise ValidationError(
            {
                "codigos_activo": (
                    f"El ítem {item.pk} debe registrar un código de activo por línea."
                )
            }
        )
    return codigos


def _obtener_repetidos(codigos: list[str]) -> set[str]:
    vistos: set[str] = set()
    repetidos: set[str] = set()
    for codigo in codigos:
        if codigo in vistos:
            repetidos.add(codigo)
        vistos.add(codigo)
    return repetidos


def _crear_unidades_desde_item(item: ItemOrdenCompra, codigos: list[str]) -> None:
    for codigo in codigos:
        Unidad.objects.create(
            tipo_equipo=item.tipo_equipo,
            codigo_activo=codigo,
            estado=Unidad.Estado.BUENO,
            situacion=Unidad.Situacion.DISPONIBLE,
            ubicacion=item.tipo_equipo.ubicacion_default,
        )


def _sumar_stock_granel(item: ItemOrdenCompra) -> None:
    TipoEquipo.objects.select_for_update().filter(pk=item.tipo_equipo_id).update(
        stock_granel=F("stock_granel") + item.cantidad,
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
