from rest_framework import serializers

from apps.catalogo.models import TipoEquipo, Ubicacion
from apps.catalogo.serializers import TipoEquipoSerializer, UbicacionSerializer

from .models import ItemOrdenCompra, OrdenCompra, Proveedor
from .services import generar_numero_oc


class ProveedorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Proveedor
        fields = [
            "id",
            "razon_social",
            "rut",
            "direccion",
            "ciudad",
            "contacto_nombre",
            "contacto_telefono",
            "email",
            "activo",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def validate(self, attrs):
        instance = self.instance or Proveedor()
        for attr, value in attrs.items():
            setattr(instance, attr, value)
        instance.full_clean(exclude=None if self.instance else [])
        attrs["rut"] = instance.rut
        return attrs


class ItemOrdenCompraSerializer(serializers.ModelSerializer):
    orden_compra = serializers.PrimaryKeyRelatedField(read_only=True)
    orden_compra_id = serializers.PrimaryKeyRelatedField(
        queryset=OrdenCompra.objects.all(),
        source="orden_compra",
        write_only=True,
        required=False,
    )
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
    total_linea = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        read_only=True,
    )

    class Meta:
        model = ItemOrdenCompra
        fields = [
            "id",
            "orden_compra",
            "orden_compra_id",
            "tipo_equipo",
            "tipo_equipo_id",
            "codigo_material",
            "unidad_medida",
            "precio_unitario",
            "cantidad_solicitada",
            "cantidad_recibida",
            "pendiente",
            "total_linea",
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
    proveedor = ProveedorSerializer(read_only=True)
    proveedor_id = serializers.PrimaryKeyRelatedField(
        queryset=Proveedor.objects.all(),
        source="proveedor",
        write_only=True,
        required=False,
        allow_null=True,
    )
    items = ItemOrdenCompraSerializer(many=True, required=False)
    creado_por = serializers.PrimaryKeyRelatedField(read_only=True)
    revisado_por = serializers.PrimaryKeyRelatedField(read_only=True)
    es_editable = serializers.BooleanField(read_only=True)
    tiene_items_pendientes = serializers.BooleanField(read_only=True)
    subtotal_neto = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        read_only=True,
    )
    monto_afecto = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        read_only=True,
    )
    iva = serializers.DecimalField(max_digits=14, decimal_places=0, read_only=True)
    total_general = serializers.DecimalField(
        max_digits=14,
        decimal_places=0,
        read_only=True,
    )

    class Meta:
        model = OrdenCompra
        fields = [
            "id",
            "numero",
            "proveedor",
            "proveedor_id",
            "numero_inacap",
            "numero_documento",
            "fecha_documento",
            "fecha_publicacion",
            "fecha_emision",
            "sede_destino",
            "direccion_despacho",
            "recibido_por_nombre",
            "comprador_nombre",
            "referencia_pedido",
            "codigo_inversion",
            "tasa_iva",
            "descuentos",
            "subtotal_neto",
            "monto_afecto",
            "iva",
            "total_general",
            "estado",
            "observaciones",
            "creado_por",
            "revisado_por",
            "fecha_revision",
            "created_at",
            "updated_at",
            "es_editable",
            "tiene_items_pendientes",
            "items",
        ]
        read_only_fields = [
            "numero",
            "estado",
            "creado_por",
            "revisado_por",
            "fecha_revision",
            "created_at",
            "updated_at",
            "es_editable",
            "tiene_items_pendientes",
            "subtotal_neto",
            "monto_afecto",
            "iva",
            "total_general",
        ]

    def create(self, validated_data):
        items_data = validated_data.pop("items", [])
        request = self.context.get("request")
        numero = generar_numero_oc()
        orden = OrdenCompra.objects.create(
            numero=numero,
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
                ItemOrdenCompra.objects.create(orden_compra=instance, **item_data)
        return instance


class RechazarOrdenCompraSerializer(serializers.Serializer):
    observaciones = serializers.CharField(required=False, allow_blank=True, default="")
