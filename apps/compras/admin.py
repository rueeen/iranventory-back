from django.contrib import admin

from .models import ItemOrdenCompra, OrdenCompra


class ItemOrdenCompraInline(admin.TabularInline):
    model = ItemOrdenCompra
    extra = 0
    readonly_fields = ["pendiente"]
    fields = [
        "tipo_equipo",
        "cantidad_solicitada",
        "cantidad_recibida",
        "pendiente",
        "codigos_activo",
        "ubicacion",
        "observaciones",
    ]


@admin.register(OrdenCompra)
class OrdenCompraAdmin(admin.ModelAdmin):
    list_display = [
        "numero",
        "proveedor",
        "estado",
        "fecha_documento",
        "creado_por",
        "created_at",
    ]
    list_filter = ["estado", "fecha_documento", "created_at"]
    search_fields = ["numero", "proveedor", "numero_documento"]
    readonly_fields = ["creado_por", "revisado_por",
                       "fecha_revision", "created_at", "updated_at"]
    inlines = [ItemOrdenCompraInline]


@admin.register(ItemOrdenCompra)
class ItemOrdenCompraAdmin(admin.ModelAdmin):
    list_display = [
        "orden_compra",
        "tipo_equipo",
        "cantidad_solicitada",
        "cantidad_recibida",
        "pendiente",
    ]
    list_filter = ["tipo_equipo__tipo_seguimiento", "orden_compra__estado"]
    search_fields = ["orden_compra__numero", "tipo_equipo__nombre"]

    def pendiente(self, obj):
        return obj.pendiente
    pendiente.short_description = "Pendiente"
