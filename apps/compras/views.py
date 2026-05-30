from django.core.exceptions import ValidationError as DjangoValidationError
from django_filters import rest_framework as filters
from rest_framework import decorators, response, serializers, status, viewsets
from rest_framework.filters import SearchFilter

from apps.cuentas.permissions import SoloLecturaOPanolero

from .models import ItemOrdenCompra, OrdenCompra
from .serializers import (
    ItemOrdenCompraSerializer,
    OrdenCompraSerializer,
    RechazarOrdenCompraSerializer,
)
from .services import (
    aceptar_orden_compra,
    enviar_revision_orden_compra,
    rechazar_orden_compra,
)


class OrdenCompraViewSet(viewsets.ModelViewSet):
    queryset = OrdenCompra.objects.select_related(
        "creado_por",
        "revisado_por",
    ).prefetch_related(
        "items",
        "items__tipo_equipo",
        "items__tipo_equipo__categoria",
        "items__tipo_equipo__ubicacion_default",
        "items__tipo_equipo__carreras",
        "items__tipo_equipo__asignaturas",
    )
    serializer_class = OrdenCompraSerializer
    permission_classes = [SoloLecturaOPanolero]
    filter_backends = [filters.DjangoFilterBackend, SearchFilter]
    filterset_fields = ["estado"]
    search_fields = ["numero", "proveedor"]

    @decorators.action(detail=True, methods=["post"], url_path="enviar_revision")
    def enviar_revision(self, request, pk=None):
        orden_compra = _ejecutar_accion(
            enviar_revision_orden_compra,
            self.get_object(),
            request.user,
        )
        return response.Response(
            self.get_serializer(orden_compra).data,
            status=status.HTTP_200_OK,
        )

    @decorators.action(detail=True, methods=["post"])
    def aceptar(self, request, pk=None):
        orden_compra = _ejecutar_accion(
            aceptar_orden_compra,
            self.get_object(),
            request.user,
        )
        return response.Response(
            self.get_serializer(orden_compra).data,
            status=status.HTTP_200_OK,
        )

    @decorators.action(detail=True, methods=["post"])
    def rechazar(self, request, pk=None):
        serializer = RechazarOrdenCompraSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        orden_compra = _ejecutar_accion(
            rechazar_orden_compra,
            self.get_object(),
            request.user,
            serializer.validated_data.get("observaciones", ""),
        )
        return response.Response(
            self.get_serializer(orden_compra).data,
            status=status.HTTP_200_OK,
        )


class ItemOrdenCompraViewSet(viewsets.ModelViewSet):
    queryset = ItemOrdenCompra.objects.select_related(
        "orden_compra",
        "tipo_equipo",
        "tipo_equipo__categoria",
        "tipo_equipo__ubicacion_default",
    ).prefetch_related("tipo_equipo__carreras", "tipo_equipo__asignaturas")
    serializer_class = ItemOrdenCompraSerializer
    permission_classes = [SoloLecturaOPanolero]
    filter_backends = [filters.DjangoFilterBackend]
    filterset_fields = ["tipo_equipo", "orden_compra"]


def _ejecutar_accion(funcion, *args, **kwargs):
    try:
        return funcion(*args, **kwargs)
    except DjangoValidationError as exc:
        if hasattr(exc, "message_dict"):
            raise serializers.ValidationError(exc.message_dict) from exc
        raise serializers.ValidationError(exc.messages) from exc
