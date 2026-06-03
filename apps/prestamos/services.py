from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F

from apps.catalogo.models import TipoEquipo
from apps.inventario.models import Unidad

from .models import DetallePrestamo, Prestamo


@transaction.atomic
def aprobar_prestamo(prestamo: Prestamo, usuario=None) -> Prestamo:
    prestamo = Prestamo.objects.select_for_update().get(pk=prestamo.pk)
    if prestamo.estado != Prestamo.Estado.SOLICITADA:
        raise ValidationError("Solo los préstamos solicitados pueden aprobarse.")
    if not prestamo.detalles.exists():
        raise ValidationError("El préstamo debe tener al menos un detalle.")

    prestamo.estado = Prestamo.Estado.APROBADA
    prestamo.aprobado_por = usuario
    prestamo.save(update_fields=["estado", "aprobado_por"])
    return prestamo


@transaction.atomic
def rechazar_prestamo(prestamo: Prestamo, usuario=None, motivo="") -> Prestamo:
    prestamo = Prestamo.objects.select_for_update().get(pk=prestamo.pk)
    if prestamo.estado != Prestamo.Estado.SOLICITADA:
        raise ValidationError("Solo los préstamos solicitados pueden rechazarse.")

    prestamo.estado = Prestamo.Estado.RECHAZADA
    prestamo.aprobado_por = usuario
    prestamo.motivo_rechazo = motivo or ""
    prestamo.save(update_fields=["estado", "aprobado_por", "motivo_rechazo"])
    return prestamo


@transaction.atomic
def preparar_prestamo(prestamo: Prestamo, usuario=None) -> Prestamo:
    prestamo = Prestamo.objects.select_for_update().get(pk=prestamo.pk)
    if prestamo.estado != Prestamo.Estado.APROBADA:
        raise ValidationError("Solo los préstamos aprobados pueden prepararse.")

    detalles = _detalles_bloqueados(prestamo)
    if not detalles:
        raise ValidationError("El préstamo debe tener al menos un detalle.")

    for detalle in detalles:
        detalle.full_clean()
        if detalle.tipo_equipo.tipo_seguimiento == TipoEquipo.TipoSeguimiento.SERIE:
            unidad = Unidad.objects.select_for_update().get(pk=detalle.unidad_id)
            if (
                unidad.situacion != Unidad.Situacion.DISPONIBLE
                or unidad.estado != Unidad.Estado.BUENO
                or unidad.requiere_revision
            ):
                raise ValidationError(
                    "No se puede preparar el préstamo porque la unidad "
                    f"{unidad} de {detalle.tipo_equipo} no está disponible "
                    f"(situación: {unidad.get_situacion_display()}, "
                    f"estado: {unidad.get_estado_display()}, "
                    f"requiere revisión: {'sí' if unidad.requiere_revision else 'no'})."
                )
        elif detalle.tipo_equipo.stock_granel < detalle.cantidad:
            raise ValidationError(
                "No se puede preparar el préstamo porque no hay stock suficiente "
                f"para {detalle.tipo_equipo}: solicitado {detalle.cantidad}, "
                f"disponible {detalle.tipo_equipo.stock_granel}."
            )

    prestamo.estado = Prestamo.Estado.PREPARADA
    prestamo.preparado_por = usuario
    prestamo.save(update_fields=["estado", "preparado_por"])
    return prestamo


@transaction.atomic
def entregar_prestamo(prestamo: Prestamo, usuario=None) -> Prestamo:
    prestamo = Prestamo.objects.select_for_update().get(pk=prestamo.pk)
    if prestamo.estado != Prestamo.Estado.PREPARADA:
        raise ValidationError("Solo los préstamos preparados pueden entregarse.")

    detalles = _detalles_bloqueados(prestamo)
    for detalle in detalles:
        detalle.full_clean()
        if detalle.tipo_equipo.tipo_seguimiento == TipoEquipo.TipoSeguimiento.SERIE:
            unidad = Unidad.objects.select_for_update().get(pk=detalle.unidad_id)
            if (
                unidad.situacion != Unidad.Situacion.DISPONIBLE
                or unidad.estado != Unidad.Estado.BUENO
                or unidad.requiere_revision
            ):
                raise ValidationError(f"La unidad {unidad} ya no está disponible.")
            unidad.situacion = Unidad.Situacion.PRESTADA
            unidad.save(update_fields=["situacion"])
        else:
            actualizadas = (
                TipoEquipo.objects.select_for_update()
                .filter(
                    pk=detalle.tipo_equipo_id,
                    stock_granel__gte=detalle.cantidad,
                )
                .update(stock_granel=F("stock_granel") - detalle.cantidad)
            )
            if actualizadas != 1:
                raise ValidationError(
                    f"No hay stock granel suficiente para {detalle.tipo_equipo}."
                )

    prestamo.estado = Prestamo.Estado.ENTREGADA
    prestamo.entregado_por = usuario
    prestamo.save(update_fields=["estado", "entregado_por"])
    return prestamo


@transaction.atomic
def iniciar_devolucion(prestamo: Prestamo) -> Prestamo:
    prestamo = Prestamo.objects.select_for_update().get(pk=prestamo.pk)
    if prestamo.estado != Prestamo.Estado.ENTREGADA:
        raise ValidationError(
            "Solo los préstamos entregados pueden entrar a devolución."
        )

    prestamo.estado = Prestamo.Estado.DEVOLUCION
    prestamo.save(update_fields=["estado"])
    return prestamo


@transaction.atomic
def registrar_devolucion(prestamo: Prestamo, detalles: list[dict]) -> Prestamo:
    prestamo = Prestamo.objects.select_for_update().get(pk=prestamo.pk)
    if prestamo.estado != Prestamo.Estado.DEVOLUCION:
        raise ValidationError(
            "Solo se puede registrar devolución en préstamos en estado devolución."
        )

    detalles_por_id = {
        detalle.id: detalle for detalle in _detalles_bloqueados(prestamo)
    }
    for detalle_data in detalles:
        detalle_id = detalle_data["id"]
        detalle = detalles_por_id.get(detalle_id)
        if detalle is None:
            raise ValidationError(
                f"El detalle {detalle_id} no pertenece al préstamo indicado."
            )

        cantidad_devuelta = detalle_data["cantidad_devuelta"]
        cantidad_no_devuelta = detalle_data["cantidad_no_devuelta"]
        condicion = detalle_data.get("condicion", Unidad.Estado.BUENO)
        if cantidad_devuelta + cantidad_no_devuelta > detalle.cantidad:
            raise ValidationError(
                "La suma devuelta y no devuelta no puede superar "
                f"la cantidad prestada del detalle {detalle_id}."
            )

        detalle.cantidad_devuelta = cantidad_devuelta
        detalle.cantidad_no_devuelta = cantidad_no_devuelta
        detalle.condicion_devolucion = condicion
        detalle.full_clean()
        detalle.save(
            update_fields=[
                "cantidad_devuelta",
                "cantidad_no_devuelta",
                "condicion_devolucion",
            ]
        )

    return prestamo


@transaction.atomic
def cerrar_prestamo(prestamo: Prestamo, usuario=None) -> Prestamo:
    prestamo = Prestamo.objects.select_for_update().get(pk=prestamo.pk)
    if prestamo.estado != Prestamo.Estado.DEVOLUCION:
        raise ValidationError("Solo los préstamos en devolución pueden cerrarse.")

    detalles = _detalles_bloqueados(prestamo)
    for detalle in detalles:
        detalle.full_clean()
        if detalle.cantidad_devuelta + detalle.cantidad_no_devuelta != detalle.cantidad:
            raise ValidationError(
                "Cada detalle debe quedar completamente devuelto "
                "o marcado como no devuelto."
            )
        if detalle.tipo_equipo.tipo_seguimiento == TipoEquipo.TipoSeguimiento.SERIE:
            unidad = Unidad.objects.select_for_update().get(pk=detalle.unidad_id)
            if detalle.cantidad_no_devuelta:
                unidad.situacion = Unidad.Situacion.BAJA
            elif detalle.condicion_devolucion == Unidad.Estado.REPARABLE:
                unidad.estado = Unidad.Estado.REPARABLE
                unidad.situacion = Unidad.Situacion.REPARACION
                unidad.requiere_revision = True
            elif detalle.condicion_devolucion == Unidad.Estado.MALO:
                unidad.estado = Unidad.Estado.MALO
                unidad.situacion = Unidad.Situacion.BAJA
                unidad.requiere_revision = True
            else:
                unidad.estado = Unidad.Estado.BUENO
                unidad.situacion = Unidad.Situacion.DISPONIBLE
                unidad.requiere_revision = False
            unidad.save(
                update_fields=["estado", "situacion", "requiere_revision"]
            )
        elif detalle.cantidad_devuelta:
            TipoEquipo.objects.select_for_update().filter(
                pk=detalle.tipo_equipo_id
            ).update(
                stock_granel=F("stock_granel") + detalle.cantidad_devuelta,
            )

    prestamo.estado = Prestamo.Estado.CERRADA
    prestamo.cerrado_por = usuario
    prestamo.save(update_fields=["estado", "cerrado_por"])
    return prestamo


def _detalles_bloqueados(prestamo: Prestamo) -> list[DetallePrestamo]:
    return list(
        DetallePrestamo.objects.select_related("tipo_equipo", "unidad")
        .select_for_update()
        .filter(prestamo=prestamo)
    )
