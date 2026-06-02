from rest_framework import serializers

from apps.catalogo.models import TipoEquipo, Ubicacion
from apps.catalogo.serializers import TipoEquipoSerializer, UbicacionSerializer

from .models import ItemOrdenCompra, OrdenCompra


class ItemOrdenCompraSerializer(serializers.ModelSerializer):
    tipo_equipo = TipoEquipoSerializer(read_only=True)
    tipo_equipo_id = serializers.PrimaryKeyRelatedField(
        queryset=TipoEquipo.objects.all(),
        source="tipo_equipo",
        write_only=True,
    )
    ubicacion = UbicacionSerializer(read_only=True)
    ubicacion_id = serializers.PrimaryKeyRelatedField(
        queryset=Ubicacion.objects.all(),
        source="ubicacion",
        write_only=True,
        required=False,
        allow_null=True,
    )
    pendiente = serializers.IntegerField(read_only=True)

    class Meta:
        model = ItemOrdenCompra
        fields = [
            "id",
            "tipo_equipo",
            "tipo_equipo_id",
            "cantidad_solicitada",
            "cantidad_recibida",
            "pendiente",
            "codigos_activo",
            "ubicacion",
            "ubicacion_id",
            "observaciones",
        ]

    def validate(self, attrs):
        solicitada = attrs.get(
            "cantidad_solicitada",
            getattr(self.instance, "cantidad_solicitada", None),
        )
        recibida = attrs.get(
            "cantidad_recibida",
            getattr(self.instance, "cantidad_recibida", 0),
        )
        if solicitada is not None and recibida is not None:
            if recibida > solicitada:
                raise serializers.ValidationError(
                    {
                        "cantidad_recibida": (
                            "La cantidad recibida no puede superar la solicitada."
                        )
                    }
                )
        return attrs


class OrdenCompraSerializer(serializers.ModelSerializer):
    items = ItemOrdenCompraSerializer(many=True, required=False)
    creado_por = serializers.PrimaryKeyRelatedField(read_only=True)
    revisado_por = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = OrdenCompra
        fields = [
            "id",
            "numero",
            "proveedor",
            "numero_documento",
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

    def create(self, validated_data):
        items_data = validated_data.pop("items", [])
        request = self.context.get("request")
        orden = OrdenCompra.objects.create(
            creado_por=request.user if request else None,
            **validated_data,
        )
        for item_data in items_data:
            ItemOrdenCompra.objects.create(orden_compra=orden, **item_data)
        return orden

    def update(self, instance, validated_data):
        items_data = validated_data.pop("items", None)
        instance = super().update(instance, validated_data)
        if items_data is not None:
            instance.items.all().delete()
            for item_data in items_data:
                ItemOrdenCompra.objects.create(
                    orden_compra=instance, **item_data)
        return instance


class RechazarOrdenCompraSerializer(serializers.Serializer):
    observaciones = serializers.CharField(
        required=False, allow_blank=True, default="")
