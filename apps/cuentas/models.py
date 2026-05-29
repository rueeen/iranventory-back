from django.contrib.auth.models import AbstractUser
from django.db import models
from simple_history.models import HistoricalRecords


class Usuario(AbstractUser):
    """Usuario custom con roles institucionales y RUT opcional."""

    class Rol(models.TextChoices):
        ALUMNO = "ALUMNO", "Alumno"
        DOCENTE = "DOCENTE", "Docente"
        PANOLERO = "PANOLERO", "Pañolero"
        DIRECTOR = "DIRECTOR", "Director"

    rol = models.CharField(
        max_length=20,
        choices=Rol.choices,
        default=Rol.ALUMNO,
    )
    rut = models.CharField(max_length=12, unique=True, blank=True, null=True)
    history = HistoricalRecords()

    class Meta:
        verbose_name = "usuario"
        verbose_name_plural = "usuarios"
