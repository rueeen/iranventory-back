from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import Unidad


@admin.register(Unidad)
class UnidadAdmin(SimpleHistoryAdmin):
    list_display = (
        "tipo_equipo",
        "codigo_activo",
        "estado",
        "situacion",
        "ubicacion",
        "requiere_revision",
    )
    list_filter = ("estado", "situacion", "requiere_revision", "ubicacion")
    search_fields = ("codigo_activo", "tipo_equipo__nombre")
