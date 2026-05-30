from django.core.exceptions import ValidationError
from django.db import models
from simple_history.models import HistoricalRecords

from apps.catalogo.models import TipoEquipo


class OrdenCompra(models.Model):
    """Orden de compra usada como base para una futura entrada de inventario."""

    class Estado(models.TextChoices):
        BORRADOR = "BORRADOR", "Borrador"
from apps.catalogo.models import TipoEquipo, Ubicacion


class EntradaInventario(models.Model):
    """Registro revisable de ingreso de equipamiento al inventario."""

    class Estado(models.TextChoices):
        REGISTRADA = "REGISTRADA", "Registrada"
        EN_REVISION = "EN_REVISION", "En revisión"
        ACEPTADA = "ACEPTADA", "Aceptada"
        RECHAZADA = "RECHAZADA", "Rechazada"

    numero = models.CharField(max_length=80, unique=True)
    proveedor = models.CharField(max_length=160)
    numero_documento = models.CharField(max_length=80, unique=True)
    proveedor = models.CharField(max_length=160, blank=True)
    fecha_documento = models.DateField(null=True, blank=True)
    estado = models.CharField(
        max_length=12,
        choices=Estado.choices,
        default=Estado.BORRADOR,
    )
    observaciones = models.TextField(blank=True)
    creado_por = models.ForeignKey(
        default=Estado.REGISTRADA,
    )
    observaciones = models.TextField(blank=True)
    revisada_por = models.ForeignKey(
        "cuentas.Usuario",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ordenes_compra_creadas",
    )
    revisado_por = models.ForeignKey(
        related_name="entradas_revisadas",
    )
    fecha_revision = models.DateTimeField(null=True, blank=True)
    aceptada_por = models.ForeignKey(
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
        related_name="entradas_aceptadas",
    )
    fecha_aceptacion = models.DateTimeField(null=True, blank=True)
    history = HistoricalRecords(
        verbose_name="historical entrada de inventario",
        verbose_name_plural="historical entradas de inventario",
    )

    class Meta:
        verbose_name = "entrada de inventario"
        verbose_name_plural = "entradas de inventario"
        ordering = ["-id"]

    def __str__(self) -> str:
        return self.numero_documento

    @property
    def puede_revisarse(self) -> bool:
        return self.estado == self.Estado.REGISTRADA

    @property
    def puede_resolverse(self) -> bool:
        return self.estado == self.Estado.EN_REVISION


class LineaEntradaInventario(models.Model):
    """Detalle de equipos recibidos en una entrada de inventario."""

    entrada = models.ForeignKey(
        EntradaInventario,
        on_delete=models.CASCADE,
        related_name="lineas",
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
        related_name="lineas_entrada",
    )
    cantidad = models.PositiveIntegerField()
    codigos_activo = models.JSONField(default=list, blank=True)
    ubicacion = models.ForeignKey(
        Ubicacion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lineas_entrada",
    )
    observaciones = models.TextField(blank=True)
    history = HistoricalRecords(
        verbose_name="historical línea de entrada de inventario",
        verbose_name_plural="historical líneas de entrada de inventario",
    )

    class Meta:
        verbose_name = "línea de entrada de inventario"
        verbose_name_plural = "líneas de entrada de inventario"
        ordering = ["entrada_id", "id"]

    def __str__(self) -> str:
        return f"{self.entrada} - {self.tipo_equipo} x {self.cantidad}"

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
            raise ValidationError({"cantidad": "La cantidad debe ser mayor a cero."})

        if not isinstance(self.codigos_activo, list):
            raise ValidationError(
                {"codigos_activo": "Los códigos de activo deben enviarse como lista."}
            )

        es_serie = (
            self.tipo_equipo_id
            and self.tipo_equipo.tipo_seguimiento == TipoEquipo.TipoSeguimiento.SERIE
        )
        if es_serie:
            codigos_limpios = [codigo for codigo in self.codigos_activo if codigo]
            if len(codigos_limpios) != self.cantidad:
                raise ValidationError(
                    {
                        "codigos_activo": (
                            "Los equipos por serie requieren un código de activo "
                            "por cada unidad recibida."
                        )
                    }
                )
            if len(set(codigos_limpios)) != len(codigos_limpios):
                raise ValidationError(
                    {"codigos_activo": "No puede repetir códigos de activo."}
                )
        elif self.codigos_activo:
            raise ValidationError(
                {"codigos_activo": "Los equipos a granel no usan códigos de activo."}
            )
