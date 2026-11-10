from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import PlanMantencion, RegistroMantencion


@admin.register(PlanMantencion)
class PlanMantencionAdmin(SimpleHistoryAdmin):
    list_display = (
        "unidad",
        "actividad",
        "frecuencia",
        "prioridad",
        "fecha_proxima_mantencion",
        "activo",
    )
    list_filter = ("activo", "frecuencia", "prioridad")
    search_fields = ("unidad__codigo_activo", "unidad__codigo_peoplesoft", "actividad")


@admin.register(RegistroMantencion)
class RegistroMantencionAdmin(SimpleHistoryAdmin):
    list_display = ("unidad", "tipo", "fecha_realizacion", "empresa", "costo")
    list_filter = ("tipo", "fecha_realizacion")
    search_fields = ("unidad__codigo_activo", "descripcion", "empresa")
