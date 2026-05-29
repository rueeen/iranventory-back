from django.utils import timezone
from django_filters import rest_framework as filters
from rest_framework import decorators, response, serializers, status, viewsets
from rest_framework.filters import SearchFilter

from apps.cuentas.permissions import SoloLecturaOPanolero

from .models import ItemOrdenCompra, OrdenCompra
from .serializers import ItemOrdenCompraSerializer, OrdenCompraSerializer


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

    @decorators.action(detail=True, methods=["post"], url_path="enviar-a-revision")
    def enviar_a_revision(self, request, pk=None):
        orden_compra = self.get_object()
        if orden_compra.estado != OrdenCompra.Estado.BORRADOR:
            raise serializers.ValidationError(
                "Solo las órdenes en borrador pueden enviarse a revisión."
            )

        orden_compra.estado = OrdenCompra.Estado.EN_REVISION
        orden_compra.revisado_por = request.user
        orden_compra.fecha_revision = timezone.now()
        orden_compra.save(
            update_fields=["estado", "revisado_por", "fecha_revision", "updated_at"]
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
