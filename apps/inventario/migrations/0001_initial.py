# Generated manually for phase 2.

import django.db.models.deletion
import simple_history.models
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("catalogo", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Unidad",
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
                (
                    "codigo_activo",
                    models.CharField(blank=True, max_length=40, null=True, unique=True),
                ),
                (
                    "estado",
                    models.CharField(
                        choices=[
                            ("BUENO", "Bueno"),
                            ("REPARABLE", "Reparable"),
                            ("MALO", "Malo"),
                        ],
                        default="BUENO",
                        max_length=10,
                    ),
                ),
                (
                    "situacion",
                    models.CharField(
                        choices=[
                            ("DISPONIBLE", "Disponible"),
                            ("PRESTADA", "Prestada"),
                            ("REPARACION", "En reparación"),
                            ("BAJA", "De baja"),
                        ],
                        default="DISPONIBLE",
                        max_length=12,
                    ),
                ),
                ("requiere_revision", models.BooleanField(default=False)),
                (
                    "tipo_equipo",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="unidades",
                        to="catalogo.tipoequipo",
                    ),
                ),
                (
                    "ubicacion",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="unidades",
                        to="catalogo.ubicacion",
                    ),
                ),
            ],
            options={
                "verbose_name": "unidad",
                "verbose_name_plural": "unidades",
                "ordering": ["tipo_equipo__nombre", "codigo_activo", "id"],
            },
        ),
        migrations.CreateModel(
            name="HistoricalUnidad",
            fields=[
                ("id", models.BigIntegerField(blank=True, db_index=True)),
                ("codigo_activo", models.CharField(blank=True, max_length=40, null=True)),
                (
                    "estado",
                    models.CharField(
                        choices=[
                            ("BUENO", "Bueno"),
                            ("REPARABLE", "Reparable"),
                            ("MALO", "Malo"),
                        ],
                        default="BUENO",
                        max_length=10,
                    ),
                ),
                (
                    "situacion",
                    models.CharField(
                        choices=[
                            ("DISPONIBLE", "Disponible"),
                            ("PRESTADA", "Prestada"),
                            ("REPARACION", "En reparación"),
                            ("BAJA", "De baja"),
                        ],
                        default="DISPONIBLE",
                        max_length=12,
                    ),
                ),
                ("requiere_revision", models.BooleanField(default=False)),
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
                    "history_user",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "tipo_equipo",
                    models.ForeignKey(
                        blank=True,
                        db_constraint=False,
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="+",
                        to="catalogo.tipoequipo",
                    ),
                ),
                (
                    "ubicacion",
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
                "verbose_name": "historical unidad",
                "verbose_name_plural": "historical unidades",
                "ordering": ("-history_date", "-history_id"),
                "get_latest_by": ("history_date", "history_id"),
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
    ]
