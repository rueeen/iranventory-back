from django.db import models
from simple_history.models import HistoricalRecords


class Categoria(models.Model):
    nombre = models.CharField(max_length=120, unique=True)

    class Meta:
        verbose_name = "categoría"
        verbose_name_plural = "categorías"
        ordering = ["nombre"]

    def __str__(self) -> str:
        return self.nombre


class Carrera(models.Model):
    nombre = models.CharField(max_length=120, unique=True)

    class Meta:
        verbose_name = "carrera"
        verbose_name_plural = "carreras"
        ordering = ["nombre"]

    def __str__(self) -> str:
        return self.nombre


class Asignatura(models.Model):
    codigo = models.CharField(max_length=20, unique=True)
    nombre = models.CharField(max_length=160)

    class Meta:
        verbose_name = "asignatura"
        verbose_name_plural = "asignaturas"
        ordering = ["codigo"]

    def __str__(self) -> str:
        return f"{self.codigo} - {self.nombre}"


class Ubicacion(models.Model):
    nombre = models.CharField(max_length=120)
    sede = models.CharField(max_length=120)

    class Meta:
        verbose_name = "ubicación"
        verbose_name_plural = "ubicaciones"
        ordering = ["sede", "nombre"]

    def __str__(self) -> str:
        return f"{self.nombre} ({self.sede})"


class TipoEquipo(models.Model):
    class TipoSeguimiento(models.TextChoices):
        SERIE = "SERIE", "Por serie"
        GRANEL = "GRANEL", "A granel"

    nombre = models.CharField(max_length=160)
    especificacion = models.TextField(blank=True)
    categoria = models.ForeignKey(
        Categoria,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tipos_equipo",
    )
    carreras = models.ManyToManyField(Carrera, blank=True, related_name="tipos_equipo")
    asignaturas = models.ManyToManyField(
        Asignatura,
        blank=True,
        related_name="tipos_equipo",
    )
    ubicacion_default = models.ForeignKey(
        Ubicacion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tipos_equipo_default",
    )
    tipo_seguimiento = models.CharField(
        max_length=10,
        choices=TipoSeguimiento.choices,
        default=TipoSeguimiento.SERIE,
    )
    valor_uf = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    cantidad_necesaria = models.PositiveIntegerField(default=0)
    stock_granel = models.PositiveIntegerField(default=0)
    observaciones = models.TextField(blank=True)
    history = HistoricalRecords(
        verbose_name="historical tipo de equipo",
        verbose_name_plural="historical tipos de equipo",
    )

    class Meta:
        verbose_name = "tipo de equipo"
        verbose_name_plural = "tipos de equipo"
        ordering = ["nombre"]

    def __str__(self) -> str:
        return self.nombre

    @property
    def stock_total(self) -> int:
        if self.tipo_seguimiento == self.TipoSeguimiento.GRANEL:
            return self.stock_granel

        return self.unidades.exclude(situacion="BAJA").count()

    @property
    def stock_disponible(self) -> int:
        if self.tipo_seguimiento == self.TipoSeguimiento.GRANEL:
            return self.stock_granel

        return self.unidades.filter(situacion="DISPONIBLE", estado="BUENO").count()

    @property
    def brecha(self) -> int:
        return max(self.cantidad_necesaria - self.stock_total, 0)
