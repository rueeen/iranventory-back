from django.contrib import admin

from .models import ItemOrdenCompra, OrdenCompra, Proveedor


class ItemOrdenCompraInline(admin.TabularInline):
    model = ItemOrdenCompra
    extra = 0
    readonly_fields = ["pendiente", "total_linea"]
    fields = [
        "tipo_equipo",
        "codigo_material",
        "unidad_medida",
        "precio_unitario",
        "cantidad_solicitada",
        "cantidad_recibida",
        "pendiente",
        "total_linea",
        "codigos_activo",
        "ubicacion",
        "observaciones",
    ]


@admin.register(Proveedor)
class ProveedorAdmin(admin.ModelAdmin):
    list_display = ["razon_social", "rut", "ciudad", "activo", "updated_at"]
    list_filter = ["activo", "ciudad"]
    search_fields = ["razon_social", "rut"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(OrdenCompra)
class OrdenCompraAdmin(admin.ModelAdmin):
    list_display = [
        "numero",
        "proveedor",
        "numero_inacap",
        "estado",
        "fecha_documento",
        "total_general",
        "creado_por",
        "created_at",
    ]
    list_filter = ["estado", "fecha_documento", "created_at"]
    search_fields = [
        "numero",
        "proveedor__razon_social",
        "proveedor__rut",
        "numero_documento",
        "numero_inacap",
    ]
    readonly_fields = [
        "creado_por",
        "revisado_por",
        "fecha_revision",
        "subtotal_neto",
        "monto_afecto",
        "iva",
        "total_general",
        "created_at",
        "updated_at",
    ]
    inlines = [ItemOrdenCompraInline]


@admin.register(ItemOrdenCompra)
class ItemOrdenCompraAdmin(admin.ModelAdmin):
    list_display = [
        "orden_compra",
        "tipo_equipo",
        "codigo_material",
        "cantidad_solicitada",
        "cantidad_recibida",
        "pendiente",
        "total_linea",
    ]
    list_filter = ["tipo_equipo__tipo_seguimiento", "orden_compra__estado"]
    search_fields = [
        "orden_compra__numero",
        "codigo_material",
        "tipo_equipo__nombre",
    ]

    def pendiente(self, obj):
        return obj.pendiente

    pendiente.short_description = "Pendiente"
