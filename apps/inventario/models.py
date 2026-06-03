from django.db import models
from simple_history.models import HistoricalRecords

from apps.catalogo.models import TipoEquipo, Ubicacion


class Unidad(models.Model):
    class Estado(models.TextChoices):
        BUENO = "BUENO", "Bueno"
        REPARABLE = "REPARABLE", "Reparable"
        MALO = "MALO", "Malo"

    class Situacion(models.TextChoices):
        DISPONIBLE = "DISPONIBLE", "Disponible"
        RESERVADA = "RESERVADA", "Reservada"
        PRESTADA = "PRESTADA", "Prestada"
        REPARACION = "REPARACION", "En reparación"
        BAJA = "BAJA", "De baja"

    tipo_equipo = models.ForeignKey(
        TipoEquipo,
        on_delete=models.CASCADE,
        related_name="unidades",
    )
    codigo_activo = models.CharField(max_length=40, unique=True, null=True, blank=True)
    estado = models.CharField(
        max_length=10,
        choices=Estado.choices,
        default=Estado.BUENO,
    )
    situacion = models.CharField(
        max_length=12,
        choices=Situacion.choices,
        default=Situacion.DISPONIBLE,
    )
    ubicacion = models.ForeignKey(
        Ubicacion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="unidades",
    )
    requiere_revision = models.BooleanField(default=False)
    history = HistoricalRecords(
        verbose_name="historical unidad",
        verbose_name_plural="historical unidades",
    )

    class Meta:
        verbose_name = "unidad"
        verbose_name_plural = "unidades"
        ordering = ["tipo_equipo__nombre", "codigo_activo", "id"]

    def __str__(self) -> str:
        if self.codigo_activo:
            return f"{self.tipo_equipo} - {self.codigo_activo}"
        return f"{self.tipo_equipo} - unidad {self.pk}"
