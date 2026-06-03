from django.core.exceptions import ValidationError as DjangoValidationError
from django_filters import rest_framework as filters
from rest_framework import decorators, response, serializers, status, viewsets
from rest_framework.filters import SearchFilter

from apps.cuentas.permissions import PermisoOrdenCompra

from .models import ItemOrdenCompra, OrdenCompra, Proveedor
from .serializers import (
    ItemOrdenCompraSerializer,
    OrdenCompraSerializer,
    ProveedorSerializer,
    RechazarOrdenCompraSerializer,
)
from .services import aceptar_orden_compra, enviar_revision, rechazar_orden_compra


class ProveedorViewSet(viewsets.ModelViewSet):
    queryset = Proveedor.objects.all()
    serializer_class = ProveedorSerializer
    permission_classes = [PermisoOrdenCompra]
    filter_backends = [filters.DjangoFilterBackend, SearchFilter]
    filterset_fields = ["activo"]
    search_fields = ["razon_social", "rut"]


class OrdenCompraViewSet(viewsets.ModelViewSet):
    queryset = OrdenCompra.objects.select_related(
        "proveedor",
        "creado_por",
        "revisado_por",
    ).prefetch_related(
        "items",
        "items__tipo_equipo",
        "items__tipo_equipo__categoria",
        "items__tipo_equipo__ubicacion_default",
        "items__tipo_equipo__carreras",
        "items__tipo_equipo__asignaturas",
        "items__ubicacion",
    )
    serializer_class = OrdenCompraSerializer
    permission_classes = [PermisoOrdenCompra]
    filter_backends = [filters.DjangoFilterBackend, SearchFilter]
    filterset_fields = ["estado"]
    search_fields = [
        "numero",
        "proveedor__razon_social",
        "proveedor__rut",
        "numero_documento",
    ]

    def update(self, request, *args, **kwargs):
        orden = self.get_object()
        if not orden.es_editable:
            raise serializers.ValidationError(
                f"La orden {orden.numero} está en estado '{orden.get_estado_display()}'"
                " y no puede modificarse."
            )
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)

    @decorators.action(detail=True, methods=["post"], url_path="enviar-revision")
    def enviar_revision(self, request, pk=None):
        orden = _ejecutar_accion(
            enviar_revision, self.get_object(), request.user)
        return response.Response(
            self.get_serializer(orden).data, status=status.HTTP_200_OK
        )

    @decorators.action(detail=True, methods=["post"])
    def aceptar(self, request, pk=None):
        orden = _ejecutar_accion(aceptar_orden_compra,
                                 self.get_object(), request.user)
        return response.Response(
            self.get_serializer(orden).data, status=status.HTTP_200_OK
        )

    @decorators.action(detail=True, methods=["post"])
    def rechazar(self, request, pk=None):
        ser = RechazarOrdenCompraSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        orden = _ejecutar_accion(
            rechazar_orden_compra,
            self.get_object(),
            request.user,
            ser.validated_data.get("observaciones", ""),
        )
        return response.Response(
            self.get_serializer(orden).data, status=status.HTTP_200_OK
        )


class ItemOrdenCompraViewSet(viewsets.ModelViewSet):
    queryset = ItemOrdenCompra.objects.select_related(
        "orden_compra",
        "tipo_equipo",
        "tipo_equipo__categoria",
        "tipo_equipo__ubicacion_default",
        "ubicacion",
    ).prefetch_related("tipo_equipo__carreras", "tipo_equipo__asignaturas")
    serializer_class = ItemOrdenCompraSerializer
    permission_classes = [PermisoOrdenCompra]
    filter_backends = [filters.DjangoFilterBackend]
    filterset_fields = ["tipo_equipo", "orden_compra"]

    def _verificar_oc_editable(self, item=None, orden_compra_id=None):
        """Lanza ValidationError si la OC asociada no está en BORRADOR."""
        if item:
            orden_compra_id = item.orden_compra_id
        try:
            oc = OrdenCompra.objects.get(pk=orden_compra_id)
        except OrdenCompra.DoesNotExist:
            raise serializers.ValidationError(
                {"orden_compra": "La orden de compra indicada no existe."}
            ) from None
        if not oc.es_editable:
            raise serializers.ValidationError(
                f"La orden {oc.numero} está en estado '{oc.get_estado_display()}'"
                " y no admite cambios en sus ítems."
            )

    def create(self, request, *args, **kwargs):
        oc_id = request.data.get("orden_compra")
        self._verificar_oc_editable(orden_compra_id=oc_id)
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        self._verificar_oc_editable(item=self.get_object())
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        self._verificar_oc_editable(item=self.get_object())
        return super().destroy(request, *args, **kwargs)


def _ejecutar_accion(funcion, *args, **kwargs):
    try:
        return funcion(*args, **kwargs)
    except DjangoValidationError as exc:
        if hasattr(exc, "message_dict"):
            raise serializers.ValidationError(exc.message_dict) from exc
        raise serializers.ValidationError(exc.messages) from exc
