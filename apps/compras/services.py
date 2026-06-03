from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, Max
from django.utils import timezone

from apps.catalogo.models import TipoEquipo
from apps.inventario.models import Unidad

from .models import ItemOrdenCompra, OrdenCompra

# ──────────────────────────── número correlativo ──────────────────────────────

def _siguiente_numero_oc(year: int) -> str:
    """
    Genera OC-YYYY-NNNN de forma thread-safe.
    Debe llamarse dentro de una transacción con select_for_update activo
    sobre el objeto que se está creando/actualizando.
    """
    prefijo = f"OC-{year}-"
    ultimo = (
        OrdenCompra.objects.filter(numero__startswith=prefijo)
        .aggregate(Max("numero"))["numero__max"]
    )
    if ultimo:
        try:
            n = int(ultimo.rsplit("-", 1)[-1]) + 1
        except ValueError:
            n = 1
    else:
        n = 1
    return f"{prefijo}{n:04d}"


@transaction.atomic
def generar_numero_oc() -> str:
    """
    Reserva el siguiente número correlativo para el año actual.
    Usa select_for_update sobre el último registro del año para evitar
    condiciones de carrera en SQLite (compatible) y PostgreSQL.
    """
    year = timezone.now().year
    prefijo = f"OC-{year}-"
    # Bloquea la fila con el número más alto del año para serializar
    # accesos concurrentes. En SQLite el bloqueo es a nivel de tabla.
    OrdenCompra.objects.filter(numero__startswith=prefijo).select_for_update()
    return _siguiente_numero_oc(year)


# ──────────────────────────── transiciones de estado ─────────────────────────

@transaction.atomic
def enviar_revision(orden_compra: OrdenCompra, usuario=None) -> OrdenCompra:
    orden_compra = OrdenCompra.objects.select_for_update().get(pk=orden_compra.pk)
    if orden_compra.estado != OrdenCompra.Estado.BORRADOR:
        raise ValidationError(
            "Solo las órdenes en borrador pueden enviarse a revisión."
        )
    if not orden_compra.items.exists():
        raise ValidationError(
            "La orden debe tener al menos un ítem antes de enviarse a revisión."
        )

    orden_compra.estado = OrdenCompra.Estado.EN_REVISION
    orden_compra.revisado_por = usuario
    orden_compra.fecha_revision = timezone.now()
    orden_compra.save(
        update_fields=["estado", "revisado_por",
                       "fecha_revision", "updated_at"]
    )
    return orden_compra


@transaction.atomic
def aceptar_orden_compra(orden_compra: OrdenCompra, usuario=None) -> OrdenCompra:
    """
    Acepta la OC e ingresa al inventario solo lo que fue recibido.

    - Ítems con cantidad_recibida == 0 se ignoran (no tocan el stock).
    - Ítems SERIE: se crean Unidades con los codigos_activo proporcionados.
    - Ítems GRANEL: se suma cantidad_recibida al stock_granel.
    """
    orden_compra = OrdenCompra.objects.select_for_update().get(pk=orden_compra.pk)
    if orden_compra.estado != OrdenCompra.Estado.EN_REVISION:
        raise ValidationError("Solo las órdenes en revisión pueden aceptarse.")

    items = _items_bloqueados(orden_compra)
    if not items:
        raise ValidationError("La orden debe tener al menos un ítem.")

    codigos_por_item = _validar_items_para_aceptacion(items)

    for item in items:
        if item.cantidad_recibida == 0:
            continue
        if item.tipo_equipo.tipo_seguimiento == TipoEquipo.TipoSeguimiento.SERIE:
            _crear_unidades(item, codigos_por_item[item.pk])
        else:
            _sumar_stock_granel(item)

    orden_compra.estado = OrdenCompra.Estado.ACEPTADA
    orden_compra.revisado_por = usuario
    orden_compra.fecha_revision = timezone.now()
    orden_compra.save(
        update_fields=["estado", "revisado_por",
                       "fecha_revision", "updated_at"]
    )
    return orden_compra


@transaction.atomic
def rechazar_orden_compra(
    orden_compra: OrdenCompra,
    usuario=None,
    observaciones: str = "",
) -> OrdenCompra:
    orden_compra = OrdenCompra.objects.select_for_update().get(pk=orden_compra.pk)
    if orden_compra.estado != OrdenCompra.Estado.EN_REVISION:
        raise ValidationError(
            "Solo las órdenes en revisión pueden rechazarse.")

    orden_compra.estado = OrdenCompra.Estado.RECHAZADA
    orden_compra.revisado_por = usuario
    orden_compra.fecha_revision = timezone.now()
    update_fields = ["estado", "revisado_por", "fecha_revision", "updated_at"]

    if observaciones:
        orden_compra.observaciones = observaciones
        update_fields.append("observaciones")

    orden_compra.save(update_fields=update_fields)
    return orden_compra


# ──────────────────────────── helpers privados ────────────────────────────────

def _items_bloqueados(orden_compra: OrdenCompra) -> list[ItemOrdenCompra]:
    return list(
        ItemOrdenCompra.objects.select_for_update()
        .select_related("tipo_equipo", "tipo_equipo__ubicacion_default", "ubicacion")
        .filter(orden_compra=orden_compra)
        .order_by("id")
    )


def _validar_items_para_aceptacion(
    items: list[ItemOrdenCompra],
) -> dict[int, list[str]]:
    codigos_por_item: dict[int, list[str]] = {}
    codigos_de_la_orden: set[str] = set()
    codigos_repetidos_entre_items: set[str] = set()

    for item in items:
        item.full_clean()

        if item.cantidad_recibida == 0:
            continue

        if item.tipo_equipo.tipo_seguimiento != TipoEquipo.TipoSeguimiento.SERIE:
            continue

        codigos = [c for c in item.codigos_activo if c]

        if len(codigos) != item.cantidad_recibida:
            raise ValidationError(
                {
                    "codigos_activo": (
                        f"El ítem {item.pk} ({item.tipo_equipo}) requiere exactamente "
                        f"{item.cantidad_recibida} código(s) de activo "
                        f"(uno por unidad recibida)."
                    )
                }
            )

        repetidos_en_item = _repetidos(codigos)
        if repetidos_en_item:
            raise ValidationError(
                {
                    "codigos_activo": (
                        f"El ítem {item.pk} tiene códigos repetidos: "
                        f"{', '.join(sorted(repetidos_en_item))}."
                    )
                }
            )

        for codigo in codigos:
            if codigo in codigos_de_la_orden:
                codigos_repetidos_entre_items.add(codigo)
            codigos_de_la_orden.add(codigo)

        codigos_por_item[item.pk] = codigos

    if codigos_repetidos_entre_items:
        raise ValidationError(
            {
                "codigos_activo": (
                    "Hay códigos repetidos entre ítems de la orden: "
                    f"{', '.join(sorted(codigos_repetidos_entre_items))}."
                )
            }
        )

    if codigos_de_la_orden:
        ya_existen = set(
            Unidad.objects.filter(
                codigo_activo__in=codigos_de_la_orden
            ).values_list("codigo_activo", flat=True)
        )
        if ya_existen:
            raise ValidationError(
                {
                    "codigos_activo": (
                        "Ya existen unidades con estos códigos de activo: "
                        f"{', '.join(sorted(ya_existen))}."
                    )
                }
            )

    return codigos_por_item


def _repetidos(valores: list[str]) -> set[str]:
    vistos: set[str] = set()
    repetidos: set[str] = set()
    for v in valores:
        if v in vistos:
            repetidos.add(v)
        vistos.add(v)
    return repetidos


def _crear_unidades(item: ItemOrdenCompra, codigos: list[str]) -> None:
    ubicacion = item.ubicacion or item.tipo_equipo.ubicacion_default
    Unidad.objects.bulk_create([
        Unidad(
            tipo_equipo=item.tipo_equipo,
            codigo_activo=codigo,
            estado=Unidad.Estado.BUENO,
            situacion=Unidad.Situacion.DISPONIBLE,
            ubicacion=ubicacion,
        )
        for codigo in codigos
    ])


def _sumar_stock_granel(item: ItemOrdenCompra) -> None:
    TipoEquipo.objects.select_for_update().filter(pk=item.tipo_equipo_id).update(
        stock_granel=F("stock_granel") + item.cantidad_recibida,
    )
