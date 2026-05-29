from django.core.exceptions import ValidationError
from django.db import models
from simple_history.models import HistoricalRecords

from apps.catalogo.models import TipoEquipo


class OrdenCompra(models.Model):
    """Orden de compra usada como base para una futura entrada de inventario."""

    class Estado(models.TextChoices):
        BORRADOR = "BORRADOR", "Borrador"
        EN_REVISION = "EN_REVISION", "En revisión"
        ACEPTADA = "ACEPTADA", "Aceptada"
        RECHAZADA = "RECHAZADA", "Rechazada"

    numero = models.CharField(max_length=80, unique=True)
    proveedor = models.CharField(max_length=160)
    fecha_documento = models.DateField(null=True, blank=True)
    estado = models.CharField(
        max_length=12,
        choices=Estado.choices,
        default=Estado.BORRADOR,
    )
    observaciones = models.TextField(blank=True)
    creado_por = models.ForeignKey(
        "cuentas.Usuario",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ordenes_compra_creadas",
    )
    revisado_por = models.ForeignKey(
        "cuentas.Usuario",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ordenes_compra_revisadas",
    )
    fecha_revision = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords(
        verbose_name="historical orden de compra",
        verbose_name_plural="historical órdenes de compra",
    )

    class Meta:
        verbose_name = "orden de compra"
        verbose_name_plural = "órdenes de compra"
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return self.numero


class ItemOrdenCompra(models.Model):
    """Ítem solicitado dentro de una orden de compra."""

    orden_compra = models.ForeignKey(
        OrdenCompra,
        on_delete=models.CASCADE,
        related_name="items",
    )
    tipo_equipo = models.ForeignKey(
        TipoEquipo,
        on_delete=models.PROTECT,
        related_name="items_orden_compra",
    )
    cantidad = models.PositiveIntegerField()
    codigos_activo = models.TextField(blank=True)
    observaciones = models.TextField(blank=True)
    history = HistoricalRecords(
        verbose_name="historical ítem de orden de compra",
        verbose_name_plural="historical ítems de orden de compra",
    )

    class Meta:
        verbose_name = "ítem de orden de compra"
        verbose_name_plural = "ítems de orden de compra"
        ordering = ["orden_compra_id", "id"]

    def __str__(self) -> str:
        return f"{self.orden_compra} - {self.tipo_equipo} x {self.cantidad}"

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        if self.cantidad < 1:
            raise ValidationError({"cantidad": "La cantidad debe ser mayor que 0."})

        if self.tipo_equipo_id and self.codigos_activo:
            self._validar_codigos_activo_por_linea()

    def _validar_codigos_activo_por_linea(self) -> None:
        codigos = self.codigos_activo.splitlines()
        if any(not codigo.strip() for codigo in codigos):
            raise ValidationError(
                {"codigos_activo": "Debe registrar un código de activo por línea."}
            )
