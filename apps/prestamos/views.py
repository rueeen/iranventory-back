from django.core.exceptions import ValidationError as DjangoValidationError
from django_filters import rest_framework as filters
from rest_framework import decorators, response, serializers, status, viewsets
from rest_framework.filters import SearchFilter

from apps.cuentas.models import Usuario
from apps.cuentas.permissions import PrestamoPermiso

from .models import Prestamo
from .serializers import PrestamoSerializer
from .services import (
    aprobar_prestamo,
    cerrar_prestamo,
    entregar_prestamo,
    iniciar_devolucion,
    preparar_prestamo,
    rechazar_prestamo,
)


class PrestamoViewSet(viewsets.ModelViewSet):
    queryset = Prestamo.objects.select_related(
        "solicitante",
        "asignatura",
        "aprobado_por",
        "preparado_por",
        "entregado_por",
        "cerrado_por",
    ).prefetch_related("detalles", "detalles__tipo_equipo", "detalles__unidad")
    serializer_class = PrestamoSerializer
    permission_classes = [PrestamoPermiso]
    filter_backends = [filters.DjangoFilterBackend, SearchFilter]
    filterset_fields = ["estado", "solicitante", "asignatura"]
    search_fields = ["solicitante__username", "observaciones"]

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.request.user.rol in {Usuario.Rol.PANOLERO, Usuario.Rol.DIRECTOR}:
            return queryset
        return queryset.filter(solicitante=self.request.user)

    @decorators.action(detail=True, methods=["post"])
    def aprobar(self, request, pk=None):
        prestamo = _ejecutar_transicion(
            aprobar_prestamo, self.get_object(), request.user
        )
        return response.Response(
            self.get_serializer(prestamo).data, status=status.HTTP_200_OK
        )

    @decorators.action(detail=True, methods=["post"])
    def rechazar(self, request, pk=None):
        prestamo = _ejecutar_transicion(
            rechazar_prestamo,
            self.get_object(),
            request.user,
            request.data.get("motivo", ""),
        )
        return response.Response(
            self.get_serializer(prestamo).data, status=status.HTTP_200_OK
        )

    @decorators.action(detail=True, methods=["post"])
    def preparar(self, request, pk=None):
        prestamo = _ejecutar_transicion(
            preparar_prestamo, self.get_object(), request.user
        )
        return response.Response(
            self.get_serializer(prestamo).data, status=status.HTTP_200_OK
        )

    @decorators.action(detail=True, methods=["post"])
    def entregar(self, request, pk=None):
        prestamo = _ejecutar_transicion(
            entregar_prestamo, self.get_object(), request.user
        )
        return response.Response(
            self.get_serializer(prestamo).data, status=status.HTTP_200_OK
        )

    @decorators.action(detail=True, methods=["post"], url_path="iniciar-devolucion")
    def iniciar_devolucion(self, request, pk=None):
        prestamo = _ejecutar_transicion(iniciar_devolucion, self.get_object())
        return response.Response(
            self.get_serializer(prestamo).data, status=status.HTTP_200_OK
        )

    @decorators.action(detail=True, methods=["post"])
    def cerrar(self, request, pk=None):
        prestamo = _ejecutar_transicion(
            cerrar_prestamo, self.get_object(), request.user
        )
        return response.Response(
            self.get_serializer(prestamo).data, status=status.HTTP_200_OK
        )


def _ejecutar_transicion(funcion, *args, **kwargs):
    try:
        return funcion(*args, **kwargs)
    except DjangoValidationError as exc:
        raise serializers.ValidationError(exc.messages) from exc
