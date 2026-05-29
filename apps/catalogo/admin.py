from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import Asignatura, Carrera, Categoria, TipoEquipo, Ubicacion


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ("nombre",)
    search_fields = ("nombre",)


@admin.register(Carrera)
class CarreraAdmin(admin.ModelAdmin):
    list_display = ("nombre",)
    search_fields = ("nombre",)


@admin.register(Asignatura)
class AsignaturaAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nombre")
    search_fields = ("codigo", "nombre")


@admin.register(Ubicacion)
class UbicacionAdmin(admin.ModelAdmin):
    list_display = ("nombre", "sede")
    search_fields = ("nombre", "sede")


@admin.register(TipoEquipo)
class TipoEquipoAdmin(SimpleHistoryAdmin):
    list_display = (
        "nombre",
        "categoria",
        "tipo_seguimiento",
        "cantidad_necesaria",
        "stock_total",
        "stock_disponible",
        "brecha",
    )
    list_filter = ("tipo_seguimiento", "categoria", "ubicacion_default")
    search_fields = ("nombre", "especificacion", "observaciones")
    filter_horizontal = ("carreras", "asignaturas")
