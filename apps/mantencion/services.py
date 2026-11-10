from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Max

from apps.cuentas.models import Usuario
from apps.inventario.models import Unidad

from .models import PlanMantencion, RegistroMantencion


@transaction.atomic
def enviar_a_mantencion(unidad, usuario):
    if usuario.rol not in {Usuario.Rol.PANOLERO, Usuario.Rol.DIRECTOR}:
        raise PermissionDenied
    unidad = Unidad.objects.select_for_update().get(pk=unidad.pk)
    if unidad.situacion != Unidad.Situacion.DISPONIBLE:
        raise ValidationError(
            "Solo se puede enviar a mantención una unidad DISPONIBLE; "
            f"la unidad está {unidad.situacion}."
        )
    unidad.situacion = Unidad.Situacion.REPARACION
    unidad._history_user = usuario
    unidad.save(update_fields=["situacion"])
    return unidad


@transaction.atomic
def registrar_mantencion(datos, usuario) -> RegistroMantencion:
    datos = dict(datos)
    unidad = Unidad.objects.select_for_update().get(pk=datos["unidad"].pk)
    if unidad.situacion == Unidad.Situacion.PRESTADA:
        raise ValidationError("No se puede registrar mantención de una unidad prestada")
    datos["unidad"] = unidad
    plan = datos.get("plan")
    if plan:
        plan = PlanMantencion.objects.select_for_update().get(pk=plan.pk)
        datos["plan"] = plan
    registro = RegistroMantencion(**datos, registrado_por=usuario)
    registro._history_user = usuario
    registro.save()
    if plan and (
        not plan.fecha_ultima_mantencion
        or registro.fecha_realizacion > plan.fecha_ultima_mantencion
    ):
        plan.fecha_ultima_mantencion = registro.fecha_realizacion
        plan._history_user = usuario
        plan.save(update_fields=["fecha_ultima_mantencion"])
    if registro.estado_resultante:
        unidad.estado = registro.estado_resultante
        if unidad.situacion == Unidad.Situacion.REPARACION:
            if unidad.estado in {Unidad.Estado.BUENO, Unidad.Estado.REPARABLE}:
                unidad.situacion = Unidad.Situacion.DISPONIBLE
        unidad._history_user = usuario
        unidad.save(update_fields=["estado", "situacion"])
    return registro


def recalcular_plan(plan_id, usuario):
    if plan_id is None:
        return
    plan = PlanMantencion.objects.select_for_update().get(pk=plan_id)
    plan.fecha_ultima_mantencion = plan.registros.aggregate(
        ultima=Max("fecha_realizacion")
    )["ultima"]
    plan._history_user = usuario
    plan.save(update_fields=["fecha_ultima_mantencion"])
