from django.contrib import admin

from .models import EntradaInventario, LineaEntradaInventario


class LineaEntradaInventarioInline(admin.TabularInline):
    model = LineaEntradaInventario
    extra = 0


@admin.register(EntradaInventario)
class EntradaInventarioAdmin(admin.ModelAdmin):
    list_display = ["numero_documento", "proveedor", "estado", "fecha_documento"]
    list_filter = ["estado", "fecha_documento"]
    search_fields = ["numero_documento", "proveedor"]
    inlines = [LineaEntradaInventarioInline]


@admin.register(LineaEntradaInventario)
class LineaEntradaInventarioAdmin(admin.ModelAdmin):
    list_display = ["entrada", "tipo_equipo", "cantidad", "ubicacion"]
    list_filter = ["tipo_equipo__tipo_seguimiento"]
    search_fields = ["entrada__numero_documento", "tipo_equipo__nombre"]
