from rest_framework import viewsets
from rest_framework.generics import CreateAPIView, RetrieveUpdateAPIView
from rest_framework.permissions import (
    SAFE_METHODS,
    AllowAny,
    BasePermission,
    IsAuthenticated,
)
from rest_framework.response import Response

from .models import Usuario
from .serializers import RegistroSerializer, UsuarioAdminSerializer, UsuarioSerializer


class MeView(RetrieveUpdateAPIView):
    serializer_class = UsuarioSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "patch", "head", "options"]

    def get_object(self):
        return self.request.user


class RegistroView(CreateAPIView):
    serializer_class = RegistroSerializer
    permission_classes = [AllowAny]


class UsuarioPermiso(BasePermission):
    """Lectura para PANOLERO o DIRECTOR; escritura solo para DIRECTOR."""

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False

        if request.method in SAFE_METHODS:
            return request.user.rol in {Usuario.Rol.PANOLERO, Usuario.Rol.DIRECTOR}

        return request.user.rol == Usuario.Rol.DIRECTOR


class UsuarioViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Usuario.objects.all().order_by("username")
    permission_classes = [UsuarioPermiso]
    http_method_names = ["get", "patch", "head", "options"]

    def get_serializer_class(self):
        if self.action == "partial_update":
            return UsuarioAdminSerializer
        return UsuarioSerializer

    def partial_update(self, request, *args, **kwargs):
        usuario = self.get_object()
        serializer = self.get_serializer(usuario, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
