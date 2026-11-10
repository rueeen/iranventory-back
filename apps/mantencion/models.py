import calendar
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from simple_history.models import HistoricalRecords

from apps.inventario.models import Unidad


def sumar_meses(fecha, meses):
    indice = fecha.year * 12 + fecha.month - 1 + meses
    anio, mes = divmod(indice, 12)
    mes += 1
    dia = min(fecha.day, calendar.monthrange(anio, mes)[1])
    return fecha.replace(year=anio, month=mes, day=dia)


class PlanMantencionQuerySet(models.QuerySet):
    def vencidos(self, hoy=None):
        hoy = hoy or timezone.localdate()
        return self.filter(activo=True).filter(
            models.Q(fecha_proxima_mantencion__lt=hoy)
            | models.Q(fecha_ultima_mantencion__isnull=True)
        )

    def proximos(self, dias=30, hoy=None):
        hoy = hoy or timezone.localdate()
        return self.filter(
            activo=True,
            fecha_proxima_mantencion__range=(hoy, hoy + timedelta(days=dias)),
        )

    def al_dia(self, dias=30, hoy=None):
        hoy = hoy or timezone.localdate()
        return self.filter(
            activo=True, fecha_proxima_mantencion__gt=hoy + timedelta(days=dias)
        )


class PlanMantencion(models.Model):
    class Frecuencia(models.TextChoices):
        MENSUAL = "MENSUAL", "Mensual"
        TRIMESTRAL = "TRIMESTRAL", "Trimestral"
        SEMESTRAL = "SEMESTRAL", "Semestral"
        ANUAL = "ANUAL", "Anual"

    class Prioridad(models.TextChoices):
        BAJA = "BAJA", "Baja"
        MEDIA = "MEDIA", "Media"
        ALTA = "ALTA", "Alta"

    unidad = models.ForeignKey(
        Unidad, on_delete=models.CASCADE, related_name="planes_mantencion"
    )
    actividad = models.CharField(max_length=200)
    frecuencia = models.CharField(
        max_length=10, choices=Frecuencia.choices, default=Frecuencia.ANUAL
    )
    prioridad = models.CharField(
        max_length=5, choices=Prioridad.choices, default=Prioridad.MEDIA
    )
    responsable = models.CharField(max_length=160, blank=True)
    fecha_ultima_mantencion = models.DateField(null=True, blank=True)
    fecha_proxima_mantencion = models.DateField(null=True, editable=False)
    activo = models.BooleanField(default=True)
    observaciones = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    objects = PlanMantencionQuerySet.as_manager()
    history = HistoricalRecords()

    class Meta:
        ordering = [models.F("fecha_proxima_mantencion").asc(nulls_first=True), "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["unidad", "actividad"], name="plan_unidad_actividad_unica"
            )
        ]

    def save(self, *args, **kwargs):
        meses = {"MENSUAL": 1, "TRIMESTRAL": 3, "SEMESTRAL": 6, "ANUAL": 12}
        self.fecha_proxima_mantencion = (
            sumar_meses(self.fecha_ultima_mantencion, meses[self.frecuencia])
            if self.fecha_ultima_mantencion
            else None
        )
        if kwargs.get("update_fields") is not None:
            kwargs["update_fields"] = set(kwargs["update_fields"]) | {
                "fecha_proxima_mantencion",
                "updated_at",
            }
        return super().save(*args, **kwargs)

    @property
    def estado_plan(self) -> str:
        if not self.activo:
            return "INACTIVO"
        hoy = timezone.localdate()
        if not self.fecha_ultima_mantencion or self.fecha_proxima_mantencion < hoy:
            return "VENCIDO"
        if self.fecha_proxima_mantencion <= hoy + timedelta(days=30):
            return "PROXIMO"
        return "AL_DIA"


class RegistroMantencion(models.Model):
    class Tipo(models.TextChoices):
        PREVENTIVO = "PREVENTIVO", "Preventivo"
        CORRECTIVO = "CORRECTIVO", "Correctivo"

    unidad = models.ForeignKey(
        Unidad, on_delete=models.PROTECT, related_name="registros_mantencion"
    )
    plan = models.ForeignKey(
        PlanMantencion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="registros",
    )
    tipo = models.CharField(max_length=10, choices=Tipo.choices)
    fecha_solicitud = models.DateField(null=True, blank=True)
    fecha_realizacion = models.DateField()
    descripcion = models.TextField()
    empresa = models.CharField(max_length=200, blank=True)
    proveedor = models.ForeignKey(
        "compras.Proveedor", on_delete=models.SET_NULL, null=True, blank=True
    )
    orden_compra = models.ForeignKey(
        "compras.OrdenCompra", on_delete=models.SET_NULL, null=True, blank=True
    )
    numero_orden_compra = models.CharField(max_length=80, blank=True)
    costo = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)]
    )
    realizado_por = models.CharField(max_length=160, blank=True)
    estado_resultante = models.CharField(
        max_length=10, choices=Unidad.Estado.choices, blank=True
    )
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ["-fecha_realizacion", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(costo__gte=0), name="costo_no_negativo"
            )
        ]

    def save(self, *args, **kwargs):
        if self.proveedor_id and not self.empresa.strip():
            self.empresa = self.proveedor.razon_social
        if self.orden_compra_id:
            self.numero_orden_compra = self.orden_compra.numero
        self.full_clean()
        return super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        errores = {}
        if self.fecha_realizacion and self.fecha_realizacion > timezone.localdate():
            errores["fecha_realizacion"] = (
                "La fecha de realización no puede ser futura."
            )
        if (
            self.fecha_solicitud
            and self.fecha_realizacion
            and self.fecha_solicitud > self.fecha_realizacion
        ):
            errores["fecha_solicitud"] = (
                "La solicitud no puede ser posterior a la realización."
            )
        if self.plan_id and self.plan.unidad_id != self.unidad_id:
            errores["plan"] = "El plan debe pertenecer a la misma unidad."
        if errores:
            raise ValidationError(errores)
