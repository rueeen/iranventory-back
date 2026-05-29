from django.core.exceptions import ValidationError as DjangoValidationError
from django_filters import rest_framework as filters
from rest_framework import decorators, response, serializers, status, viewsets
from rest_framework.filters import SearchFilter

from apps.cuentas.permissions import SoloLecturaOPanolero

from .models import EntradaInventario
from .serializers import EntradaInventarioSerializer
from .services import aceptar_entrada, enviar_a_revision, rechazar_entrada


class EntradaInventarioViewSet(viewsets.ModelViewSet):
    queryset = EntradaInventario.objects.prefetch_related(
        "lineas",
        "lineas__tipo_equipo",
        "lineas__ubicacion",
    ).select_related("revisada_por", "aceptada_por")
    serializer_class = EntradaInventarioSerializer
    permission_classes = [SoloLecturaOPanolero]
    filter_backends = [filters.DjangoFilterBackend, SearchFilter]
    filterset_fields = ["estado", "proveedor", "fecha_documento"]
    search_fields = ["numero_documento", "proveedor"]

    @decorators.action(detail=True, methods=["post"], url_path="enviar-a-revision")
    def enviar_a_revision(self, request, pk=None):
        entrada = _ejecutar_transicion(
            enviar_a_revision, self.get_object(), request.user
        )
        serializer = self.get_serializer(entrada)
        return response.Response(serializer.data, status=status.HTTP_200_OK)

    @decorators.action(detail=True, methods=["post"])
    def aceptar(self, request, pk=None):
        entrada = _ejecutar_transicion(aceptar_entrada, self.get_object(), request.user)
        serializer = self.get_serializer(entrada)
        return response.Response(serializer.data, status=status.HTTP_200_OK)

    @decorators.action(detail=True, methods=["post"])
    def rechazar(self, request, pk=None):
        entrada = _ejecutar_transicion(
            rechazar_entrada, self.get_object(), request.user
        )
        serializer = self.get_serializer(entrada)
        return response.Response(serializer.data, status=status.HTTP_200_OK)


def _ejecutar_transicion(funcion, *args, **kwargs):
    try:
        return funcion(*args, **kwargs)
    except DjangoValidationError as exc:
        raise serializers.ValidationError(exc.messages) from exc
