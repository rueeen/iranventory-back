import re
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.db import models
from simple_history.models import HistoricalRecords

from apps.catalogo.models import TipoEquipo, Ubicacion

RUT_CON_PUNTOS_RE = re.compile(r"^\d{1,3}(\.\d{3})*-[\dkK]$")
RUT_SIN_PUNTOS_RE = re.compile(r"^\d{7,8}-[\dkK]$")
CLP_QUANTIZER = Decimal("1")


class Proveedor(models.Model):
    """Proveedor asociado a órdenes de compra."""

    razon_social = models.CharField(max_length=200)
    rut = models.CharField(max_length=20, unique=True)
    direccion = models.CharField(max_length=255, blank=True)
    ciudad = models.CharField(max_length=120, blank=True)
    contacto_nombre = models.CharField(max_length=160, blank=True)
    contacto_telefono = models.CharField(max_length=80, blank=True)
    email = models.EmailField(blank=True)
    activo = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords(
        verbose_name="historical proveedor",
        verbose_name_plural="historical proveedores",
    )

    class Meta:
        verbose_name = "proveedor"
        verbose_name_plural = "proveedores"
        ordering = ["razon_social", "rut"]

    def __str__(self) -> str:
        return f"{self.razon_social} ({self.rut})"

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        if not self.rut:
            return

        rut = self.rut.strip()
        if RUT_SIN_PUNTOS_RE.fullmatch(rut):
            cuerpo, dv = rut.split("-")
            grupos = []
            while cuerpo:
                grupos.insert(0, cuerpo[-3:])
                cuerpo = cuerpo[:-3]
            rut = f"{'.'.join(grupos)}-{dv.upper()}"
        elif RUT_CON_PUNTOS_RE.fullmatch(rut):
            cuerpo, dv = rut.rsplit("-", 1)
            rut = f"{cuerpo}-{dv.upper()}"
        else:
            raise ValidationError(
                {"rut": "Ingrese un RUT chileno válido, con o sin puntos."}
            )

        self.rut = rut


class OrdenCompra(models.Model):
    """Orden de compra con flujo BORRADOR → EN_REVISION → ACEPTADA / RECHAZADA."""

    class Estado(models.TextChoices):
        BORRADOR = "BORRADOR", "Borrador"
        EN_REVISION = "EN_REVISION", "En revisión"
        ACEPTADA = "ACEPTADA", "Aceptada"
        RECHAZADA = "RECHAZADA", "Rechazada"

    ESTADOS_EDITABLES = {Estado.BORRADOR}

    numero = models.CharField(max_length=80, unique=True)
    proveedor = models.ForeignKey(
        Proveedor,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="ordenes_compra",
    )
    numero_inacap = models.CharField(max_length=40, blank=True)
    numero_documento = models.CharField(max_length=80, blank=True)
    fecha_documento = models.DateField(null=True, blank=True)
    fecha_publicacion = models.DateField(null=True, blank=True)
    fecha_emision = models.DateField(null=True, blank=True)
    sede_destino = models.CharField(max_length=120, blank=True)
    direccion_despacho = models.CharField(max_length=255, blank=True)
    recibido_por_nombre = models.CharField(max_length=160, blank=True)
    comprador_nombre = models.CharField(max_length=160, blank=True)
    referencia_pedido = models.CharField(max_length=80, blank=True)
    codigo_inversion = models.CharField(max_length=80, blank=True)
    tasa_iva = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("19"),
    )
    descuentos = models.DecimalField(max_digits=12, decimal_places=2, default=0)
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
    def es_editable(self) -> bool:
        return self.estado in self.ESTADOS_EDITABLES

    @property
    def tiene_items_pendientes(self) -> bool:
        """True si algún ítem tiene cantidad_recibida < cantidad_solicitada."""
        return self.items.filter(
            models.Q(cantidad_recibida__lt=models.F("cantidad_solicitada"))
        ).exists()

    @property
    def subtotal_neto(self) -> Decimal:
        return sum((item.total_linea for item in self.items.all()), Decimal("0"))

    @property
    def monto_afecto(self) -> Decimal:
        return self.subtotal_neto - (self.descuentos or Decimal("0"))

    @property
    def iva(self) -> Decimal:
        tasa_iva = self.tasa_iva or Decimal("0")
        return ((self.monto_afecto * tasa_iva) / Decimal("100")).quantize(
            CLP_QUANTIZER,
            rounding=ROUND_HALF_UP,
        )

    @property
    def total_general(self) -> Decimal:
        return (self.monto_afecto + self.iva).quantize(
            CLP_QUANTIZER,
            rounding=ROUND_HALF_UP,
        )


class ItemOrdenCompra(models.Model):
    """
    Ítem solicitado dentro de una OC.

    - cantidad_solicitada: lo que se pidió al proveedor.
    - cantidad_recibida:   lo que llegó físicamente (0..cantidad_solicitada).
    - codigos_activo:      lista de códigos de activo, solo para equipos SERIE;
                           len debe coincidir con cantidad_recibida al aceptar.
    - total_linea:         usa la cantidad SOLICITADA (pedido/cotizado), no la
                           cantidad recibida.
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
    codigo_material = models.CharField(max_length=40, blank=True)
    unidad_medida = models.CharField(max_length=20, blank=True, default="UNI")
    precio_unitario = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
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

        # Validación anticipada de consistencia SERIE: si ya hay cantidad_recibida
        # y códigos, la cantidad debe coincidir. Permite guardar en borrador con
        # cantidad_recibida=0 y lista vacía sin error.
        es_serie = (
            self.tipo_equipo_id
            and hasattr(self, "tipo_equipo")
            and self.tipo_equipo.tipo_seguimiento == TipoEquipo.TipoSeguimiento.SERIE
        )
        if es_serie and self.cantidad_recibida > 0 and self.codigos_activo:
            codigos_limpios = [c for c in self.codigos_activo if c]
            if len(codigos_limpios) != self.cantidad_recibida:
                raise ValidationError(
                    {
                        "codigos_activo": (
                            f"Se indicaron {self.cantidad_recibida} unidades recibidas "
                            f"pero hay {len(codigos_limpios)} código(s) de activo. "
                            "Deben coincidir."
                        )
                    }
                )

    @property
    def pendiente(self) -> int:
        return self.cantidad_solicitada - self.cantidad_recibida

    @property
    def total_linea(self) -> Decimal:
        """Total neto usando cantidad_solicitada, no cantidad_recibida."""
        return (self.precio_unitario or Decimal("0")) * Decimal(
            self.cantidad_solicitada or 0
        )
