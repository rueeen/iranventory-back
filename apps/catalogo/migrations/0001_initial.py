# Generated manually for phase 2.

import django.db.models.deletion
import simple_history.models
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Asignatura",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("codigo", models.CharField(max_length=20, unique=True)),
                ("nombre", models.CharField(max_length=160)),
            ],
            options={
                "verbose_name": "asignatura",
                "verbose_name_plural": "asignaturas",
                "ordering": ["codigo"],
            },
        ),
        migrations.CreateModel(
            name="Carrera",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("nombre", models.CharField(max_length=120, unique=True)),
            ],
            options={
                "verbose_name": "carrera",
                "verbose_name_plural": "carreras",
                "ordering": ["nombre"],
            },
        ),
        migrations.CreateModel(
            name="Categoria",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("nombre", models.CharField(max_length=120, unique=True)),
            ],
            options={
                "verbose_name": "categoría",
                "verbose_name_plural": "categorías",
                "ordering": ["nombre"],
            },
        ),
        migrations.CreateModel(
            name="Ubicacion",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("nombre", models.CharField(max_length=120)),
                ("sede", models.CharField(max_length=120)),
            ],
            options={
                "verbose_name": "ubicación",
                "verbose_name_plural": "ubicaciones",
                "ordering": ["sede", "nombre"],
            },
        ),
        migrations.CreateModel(
            name="HistoricalTipoEquipo",
            fields=[
                ("id", models.BigIntegerField(blank=True, db_index=True)),
                ("nombre", models.CharField(max_length=160)),
                ("especificacion", models.TextField(blank=True)),
                (
                    "tipo_seguimiento",
                    models.CharField(
                        choices=[("SERIE", "Por serie"), ("GRANEL", "A granel")],
                        default="SERIE",
                        max_length=10,
                    ),
                ),
                (
                    "valor_uf",
                    models.DecimalField(decimal_places=2, default=0, max_digits=10),
                ),
                ("cantidad_necesaria", models.PositiveIntegerField(default=0)),
                ("stock_granel", models.PositiveIntegerField(default=0)),
                ("observaciones", models.TextField(blank=True)),
                ("history_id", models.AutoField(primary_key=True, serialize=False)),
                ("history_date", models.DateTimeField(db_index=True)),
                ("history_change_reason", models.CharField(max_length=100, null=True)),
                (
                    "history_type",
                    models.CharField(
                        choices=[("+", "Created"), ("~", "Changed"), ("-", "Deleted")],
                        max_length=1,
                    ),
                ),
                (
                    "categoria",
                    models.ForeignKey(
                        blank=True,
                        db_constraint=False,
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="+",
                        to="catalogo.categoria",
                    ),
                ),
                (
                    "history_user",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "ubicacion_default",
                    models.ForeignKey(
                        blank=True,
                        db_constraint=False,
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="+",
                        to="catalogo.ubicacion",
                    ),
                ),
            ],
            options={
                "verbose_name": "historical tipo de equipo",
                "verbose_name_plural": "historical tipos de equipo",
                "ordering": ("-history_date", "-history_id"),
                "get_latest_by": ("history_date", "history_id"),
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
        migrations.CreateModel(
            name="TipoEquipo",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("nombre", models.CharField(max_length=160)),
                ("especificacion", models.TextField(blank=True)),
                (
                    "tipo_seguimiento",
                    models.CharField(
                        choices=[("SERIE", "Por serie"), ("GRANEL", "A granel")],
                        default="SERIE",
                        max_length=10,
                    ),
                ),
                (
                    "valor_uf",
                    models.DecimalField(decimal_places=2, default=0, max_digits=10),
                ),
                ("cantidad_necesaria", models.PositiveIntegerField(default=0)),
                ("stock_granel", models.PositiveIntegerField(default=0)),
                ("observaciones", models.TextField(blank=True)),
                (
                    "asignaturas",
                    models.ManyToManyField(
                        blank=True,
                        related_name="tipos_equipo",
                        to="catalogo.asignatura",
                    ),
                ),
                (
                    "carreras",
                    models.ManyToManyField(
                        blank=True,
                        related_name="tipos_equipo",
                        to="catalogo.carrera",
                    ),
                ),
                (
                    "categoria",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="tipos_equipo",
                        to="catalogo.categoria",
                    ),
                ),
                (
                    "ubicacion_default",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="tipos_equipo_default",
                        to="catalogo.ubicacion",
                    ),
                ),
            ],
            options={
                "verbose_name": "tipo de equipo",
                "verbose_name_plural": "tipos de equipo",
                "ordering": ["nombre"],
            },
        ),
    ]
