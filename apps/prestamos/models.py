from django.core.exceptions import ValidationError
from django.db import models
from simple_history.models import HistoricalRecords

from apps.catalogo.models import TipoEquipo
from apps.inventario.models import Unidad


class Prestamo(models.Model):
    """Solicitud y seguimiento de préstamo de equipamiento."""

    class Estado(models.TextChoices):
        SOLICITADA = "SOLICITADA", "Solicitada"
        APROBADA = "APROBADA", "Aprobada"
        PREPARADA = "PREPARADA", "Preparada"
        ENTREGADA = "ENTREGADA", "Entregada"
        DEVOLUCION = "DEVOLUCION", "En devolución"
        CERRADA = "CERRADA", "Cerrada"
        RECHAZADA = "RECHAZADA", "Rechazada"

    solicitante = models.ForeignKey(
        "cuentas.Usuario",
        on_delete=models.PROTECT,
        related_name="prestamos_solicitados",
    )
    asignatura = models.ForeignKey(
        "catalogo.Asignatura",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="prestamos",
    )
    estado = models.CharField(
        max_length=12,
        choices=Estado.choices,
        default=Estado.SOLICITADA,
    )
    fecha_solicitud = models.DateTimeField(auto_now_add=True)
    fecha_requerida = models.DateTimeField(null=True, blank=True)
    fecha_devolucion_comprometida = models.DateTimeField(null=True, blank=True)
    aprobado_por = models.ForeignKey(
        "cuentas.Usuario",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="prestamos_aprobados",
    )
    preparado_por = models.ForeignKey(
        "cuentas.Usuario",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="prestamos_preparados",
    )
    entregado_por = models.ForeignKey(
        "cuentas.Usuario",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="prestamos_entregados",
    )
    cerrado_por = models.ForeignKey(
        "cuentas.Usuario",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="prestamos_cerrados",
    )
    motivo_rechazo = models.TextField(blank=True)
    observaciones = models.TextField(blank=True)
    history = HistoricalRecords(
        verbose_name="historical préstamo",
        verbose_name_plural="historical préstamos",
    )

    class Meta:
        verbose_name = "préstamo"
        verbose_name_plural = "préstamos"
        ordering = ["-fecha_solicitud", "-id"]

    def __str__(self) -> str:
        return f"Préstamo {self.pk} - {self.solicitante}"


class DetallePrestamo(models.Model):
    """Equipo solicitado o entregado dentro de un préstamo."""

    prestamo = models.ForeignKey(
        Prestamo,
        on_delete=models.CASCADE,
        related_name="detalles",
    )
    tipo_equipo = models.ForeignKey(
        TipoEquipo,
        on_delete=models.PROTECT,
        related_name="detalles_prestamo",
    )
    unidad = models.ForeignKey(
        Unidad,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="detalles_prestamo",
    )
    cantidad = models.PositiveIntegerField(default=1)
    cantidad_devuelta = models.PositiveIntegerField(default=0)
    cantidad_no_devuelta = models.PositiveIntegerField(default=0)
    observaciones = models.TextField(blank=True)
    history = HistoricalRecords(
        verbose_name="historical detalle de préstamo",
        verbose_name_plural="historical detalles de préstamo",
    )

    class Meta:
        verbose_name = "detalle de préstamo"
        verbose_name_plural = "detalles de préstamo"
        ordering = ["prestamo_id", "id"]

    def __str__(self) -> str:
        return f"{self.prestamo} - {self.tipo_equipo} x {self.cantidad}"

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        if self.cantidad < 1:
            raise ValidationError({"cantidad": "La cantidad debe ser mayor a cero."})
        if self.cantidad_devuelta + self.cantidad_no_devuelta > self.cantidad:
            raise ValidationError(
                "La suma devuelta y no devuelta no puede superar la cantidad prestada."
            )

        es_serie = (
            self.tipo_equipo_id
            and self.tipo_equipo.tipo_seguimiento == TipoEquipo.TipoSeguimiento.SERIE
        )
        if es_serie:
            if self.cantidad != 1:
                raise ValidationError(
                    {"cantidad": "Los equipos por serie se prestan de a una unidad."}
                )
            if not self.unidad_id:
                raise ValidationError(
                    {"unidad": "Debe indicar la unidad para equipos por serie."}
                )
            if self.unidad and self.unidad.tipo_equipo_id != self.tipo_equipo_id:
                raise ValidationError(
                    {"unidad": "La unidad debe pertenecer al tipo de equipo indicado."}
                )
        elif self.unidad_id:
            raise ValidationError(
                {"unidad": "Los equipos a granel no usan unidad física."}
            )
