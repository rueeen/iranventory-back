from rest_framework.permissions import SAFE_METHODS, BasePermission

from .models import Usuario


class EsPanolero(BasePermission):
    """Permite el acceso solo a usuarios con rol PANOLERO."""

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.rol == Usuario.Rol.PANOLERO
        )


class EsDirector(BasePermission):
    """Permite el acceso solo a usuarios con rol DIRECTOR."""

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.rol == Usuario.Rol.DIRECTOR
        )


class SoloLecturaOPanolero(BasePermission):
    """Lectura para autenticados; escritura para PANOLERO o DIRECTOR."""

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False

        if request.method in SAFE_METHODS:
            return True

        return request.user.rol in {Usuario.Rol.PANOLERO, Usuario.Rol.DIRECTOR}


class PermisoOrdenCompra(BasePermission):
    """Permisos para órdenes de compra con aprobación exclusiva de DIRECCIÓN."""

    ACCIONES_APROBACION = frozenset({"aceptar", "rechazar"})

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False

        es_staff_compras = request.user.rol in {
            Usuario.Rol.PANOLERO,
            Usuario.Rol.DIRECTOR,
        }

        if request.method in SAFE_METHODS:
            return es_staff_compras

        if view.action in self.ACCIONES_APROBACION:
            return request.user.rol == Usuario.Rol.DIRECTOR

        return es_staff_compras


class PrestamoPermiso(BasePermission):
    """Solicitudes para autenticados; gestión de flujo para PAÑOLERO o DIRECTOR."""

    ACCIONES_GESTION = frozenset(
        {
            "aprobar",
            "rechazar",
            "cancelar",
            "preparar",
            "entregar",
            "iniciar_devolucion",
            "cerrar",
            "registrar_devolucion",
        }
    )

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False

        if request.method in SAFE_METHODS:
            return True

        if view.action == "create":
            return True

        puede_gestionar = request.user.rol in {
            Usuario.Rol.PANOLERO,
            Usuario.Rol.DIRECTOR,
        }

        if view.action in self.ACCIONES_GESTION:
            return puede_gestionar

        return puede_gestionar
