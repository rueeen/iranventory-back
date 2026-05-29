from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Usuario


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ("Datos institucionales", {"fields": ("rol", "rut")}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Datos institucionales", {"fields": ("rol", "rut")}),
    )
    list_display = UserAdmin.list_display + ("rol", "rut")
    list_filter = UserAdmin.list_filter + ("rol",)
