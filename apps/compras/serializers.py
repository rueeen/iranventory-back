from django.db import transaction
from rest_framework import serializers

from apps.catalogo.models import TipoEquipo
from apps.catalogo.serializers import TipoEquipoSerializer

from .models import ItemOrdenCompra, OrdenCompra


class ItemOrdenCompraAnidadoSerializer(serializers.ModelSerializer):
    tipo_equipo = TipoEquipoSerializer(read_only=True)
    tipo_equipo_id = serializers.PrimaryKeyRelatedField(
        queryset=TipoEquipo.objects.all(),
        source="tipo_equipo",
        write_only=True,
    )

    class Meta:
        model = ItemOrdenCompra
        fields = [
            "id",
            "tipo_equipo",
            "tipo_equipo_id",
            "cantidad",
            "codigos_activo",
            "observaciones",
        ]


class OrdenCompraSerializer(serializers.ModelSerializer):
    items = ItemOrdenCompraAnidadoSerializer(many=True, required=False)

    class Meta:
        model = OrdenCompra
        fields = [
            "id",
            "numero",
            "proveedor",
            "fecha_documento",
            "estado",
            "observaciones",
            "creado_por",
            "revisado_por",
            "fecha_revision",
            "created_at",
            "updated_at",
            "items",
        ]
        read_only_fields = [
            "estado",
            "creado_por",
            "revisado_por",
            "fecha_revision",
            "created_at",
            "updated_at",
        ]

    @transaction.atomic
    def create(self, validated_data):
        items_data = validated_data.pop("items", [])
        orden_compra = OrdenCompra.objects.create(
            creado_por=self.context["request"].user,
            **validated_data,
        )
        self._guardar_items(orden_compra, items_data)
        return orden_compra

    @transaction.atomic
    def update(self, instance, validated_data):
        items_data = validated_data.pop("items", None)
        orden_compra = super().update(instance, validated_data)
        if items_data is not None:
            orden_compra.items.all().delete()
            self._guardar_items(orden_compra, items_data)
        return orden_compra

    def _guardar_items(self, orden_compra, items_data) -> None:
        for item_data in items_data:
            ItemOrdenCompra.objects.create(
                orden_compra=orden_compra,
                **item_data,
            )


class ItemOrdenCompraSerializer(serializers.ModelSerializer):
    orden_compra_id = serializers.PrimaryKeyRelatedField(
        queryset=OrdenCompra.objects.all(),
        source="orden_compra",
        write_only=True,
    )
    tipo_equipo = TipoEquipoSerializer(read_only=True)
    tipo_equipo_id = serializers.PrimaryKeyRelatedField(
        queryset=TipoEquipo.objects.all(),
        source="tipo_equipo",
        write_only=True,
    )

    class Meta:
        model = ItemOrdenCompra
        fields = [
            "id",
            "orden_compra",
            "orden_compra_id",
            "tipo_equipo",
            "tipo_equipo_id",
            "cantidad",
            "codigos_activo",
            "observaciones",
        ]
        read_only_fields = ["orden_compra"]


class RechazarOrdenCompraSerializer(serializers.Serializer):
    observaciones = serializers.CharField(
        allow_blank=True,
        required=False,
    )
