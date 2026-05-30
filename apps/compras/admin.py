from django.contrib import admin

from .models import ItemOrdenCompra, OrdenCompra


class ItemOrdenCompraInline(admin.TabularInline):
    model = ItemOrdenCompra
    extra = 0


@admin.register(OrdenCompra)
class OrdenCompraAdmin(admin.ModelAdmin):
    list_display = ["numero", "proveedor", "estado", "fecha_documento", "created_at"]
    list_filter = ["estado", "fecha_documento", "created_at"]
    search_fields = ["numero", "proveedor"]
    readonly_fields = ["created_at", "updated_at"]
    inlines = [ItemOrdenCompraInline]


@admin.register(ItemOrdenCompra)
class ItemOrdenCompraAdmin(admin.ModelAdmin):
    list_display = ["orden_compra", "tipo_equipo", "cantidad"]
    list_filter = ["tipo_equipo__tipo_seguimiento"]
    search_fields = ["orden_compra__numero", "tipo_equipo__nombre"]
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
