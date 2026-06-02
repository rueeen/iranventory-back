from django.core.exceptions import ValidationError
from django.db import models
from simple_history.models import HistoricalRecords

from apps.catalogo.models import TipoEquipo, Ubicacion


class OrdenCompra(models.Model):
    """Orden de compra con flujo BORRADOR → EN_REVISION → ACEPTADA / RECHAZADA."""

    class Estado(models.TextChoices):
        BORRADOR = "BORRADOR", "Borrador"
        EN_REVISION = "EN_REVISION", "En revisión"
        ACEPTADA = "ACEPTADA", "Aceptada"
        RECHAZADA = "RECHAZADA", "Rechazada"

    numero = models.CharField(max_length=80, unique=True)
    proveedor = models.CharField(max_length=160, blank=True)
    numero_documento = models.CharField(max_length=80, blank=True)
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

    @property
    def puede_enviarse(self) -> bool:
        return self.estado == self.Estado.BORRADOR

    @property
    def puede_resolverse(self) -> bool:
        return self.estado == self.Estado.EN_REVISION

    @property
    def tiene_items_pendientes(self) -> bool:
        """True si algún ítem tiene cantidad_recibida < cantidad_solicitada."""
        return self.items.filter(
            models.Q(cantidad_recibida__lt=models.F("cantidad_solicitada"))
        ).exists()


class ItemOrdenCompra(models.Model):
    """
    Ítem solicitado dentro de una OC.

    - cantidad_solicitada: lo que se pidió al proveedor.
    - cantidad_recibida:   lo que llegó físicamente (0 a cantidad_solicitada).
    - codigos_activo:      lista de códigos de activo, solo para equipos SERIE;
                           len debe coincidir con cantidad_recibida al aceptar.
    """

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
    cantidad_solicitada = models.PositiveIntegerField()
    cantidad_recibida = models.PositiveIntegerField(default=0)
    codigos_activo = models.JSONField(default=list, blank=True)
    ubicacion = models.ForeignKey(
        Ubicacion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="items_orden_compra",
    )
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
        return f"{self.orden_compra} — {self.tipo_equipo} x {self.cantidad_solicitada}"

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        if self.cantidad_solicitada is not None and self.cantidad_solicitada < 1:
            raise ValidationError(
                {"cantidad_solicitada": "La cantidad solicitada debe ser mayor a cero."}
            )
        if (
            self.cantidad_recibida is not None
            and self.cantidad_solicitada is not None
            and self.cantidad_recibida > self.cantidad_solicitada
        ):
            raise ValidationError(
                {
                    "cantidad_recibida": (
                        "La cantidad recibida no puede superar la cantidad solicitada."
                    )
                }
            )
        if not isinstance(self.codigos_activo, list):
            raise ValidationError(
                {"codigos_activo": "Los códigos de activo deben enviarse como lista."}
            )

    @property
    def pendiente(self) -> int:
        return self.cantidad_solicitada - self.cantidad_recibida
