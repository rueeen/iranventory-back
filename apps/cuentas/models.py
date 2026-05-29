from django.contrib.auth.models import AbstractUser


class Usuario(AbstractUser):
    """Usuario custom base para incorporar roles y RUT en fases posteriores."""

    class Meta:
        verbose_name = "usuario"
        verbose_name_plural = "usuarios"
