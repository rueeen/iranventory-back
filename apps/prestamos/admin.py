from django.contrib import admin

from .models import DetallePrestamo, Prestamo


class DetallePrestamoInline(admin.TabularInline):
    model = DetallePrestamo
    extra = 0


@admin.register(Prestamo)
class PrestamoAdmin(admin.ModelAdmin):
    list_display = ["id", "solicitante", "estado", "fecha_solicitud", "fecha_requerida"]
    list_filter = ["estado", "fecha_solicitud"]
    search_fields = ["solicitante__username", "solicitante__rut", "observaciones"]
    inlines = [DetallePrestamoInline]


@admin.register(DetallePrestamo)
class DetallePrestamoAdmin(admin.ModelAdmin):
    list_display = ["prestamo", "tipo_equipo", "unidad", "cantidad"]
    list_filter = ["tipo_equipo__tipo_seguimiento"]
    search_fields = [
        "prestamo__solicitante__username",
        "tipo_equipo__nombre",
        "unidad__codigo_activo",
    ]
