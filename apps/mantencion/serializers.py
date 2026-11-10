from rest_framework import serializers

from apps.compras.models import OrdenCompra, Proveedor
from apps.inventario.models import Unidad

from .models import PlanMantencion, RegistroMantencion


class UnidadMantencionSerializer(serializers.ModelSerializer):
    nombre = serializers.CharField(source="tipo_equipo.nombre", read_only=True)
    especificacion = serializers.CharField(
        source="tipo_equipo.especificacion", read_only=True
    )
    ubicacion = serializers.StringRelatedField()

    class Meta:
        model = Unidad
        fields = [
            "id",
            "codigo_activo",
            "codigo_peoplesoft",
            "nombre",
            "especificacion",
            "ubicacion",
        ]


class PlanMantencionSerializer(serializers.ModelSerializer):
    unidad = UnidadMantencionSerializer(read_only=True)
    unidad_id = serializers.PrimaryKeyRelatedField(
        source="unidad", queryset=Unidad.objects.all(), write_only=True
    )
    estado_plan = serializers.CharField(read_only=True)

    class Meta:
        model = PlanMantencion
        fields = [
            "id",
            "unidad",
            "unidad_id",
            "actividad",
            "frecuencia",
            "prioridad",
            "responsable",
            "fecha_ultima_mantencion",
            "fecha_proxima_mantencion",
            "activo",
            "observaciones",
            "created_at",
            "updated_at",
            "estado_plan",
        ]
        read_only_fields = ["fecha_proxima_mantencion", "created_at", "updated_at"]

    def validate(self, attrs):
        unidad = attrs.get("unidad", getattr(self.instance, "unidad", None))
        if self.instance and unidad.pk != self.instance.unidad_id:
            if self.instance.registros.exclude(unidad=unidad).exists():
                raise serializers.ValidationError(
                    {"unidad_id": "El plan tiene registros de otra unidad."}
                )
        return attrs


class ProveedorMantencionSerializer(serializers.ModelSerializer):
    nombre = serializers.CharField(source="razon_social")

    class Meta:
        model = Proveedor
        fields = ["id", "nombre"]


class OrdenMantencionSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrdenCompra
        fields = ["id", "numero"]


class RegistroMantencionSerializer(serializers.ModelSerializer):
    proveedor = ProveedorMantencionSerializer(read_only=True)
    orden_compra = OrdenMantencionSerializer(read_only=True)
    proveedor_id = serializers.PrimaryKeyRelatedField(
        source="proveedor",
        queryset=Proveedor.objects.all(),
        write_only=True,
        required=False,
        allow_null=True,
    )
    orden_compra_id = serializers.PrimaryKeyRelatedField(
        source="orden_compra",
        queryset=OrdenCompra.objects.all(),
        write_only=True,
        required=False,
        allow_null=True,
    )

    class Meta:
        model = RegistroMantencion
        fields = [
            "id",
            "unidad",
            "plan",
            "tipo",
            "fecha_solicitud",
            "fecha_realizacion",
            "descripcion",
            "empresa",
            "proveedor",
            "proveedor_id",
            "orden_compra",
            "orden_compra_id",
            "numero_orden_compra",
            "costo",
            "realizado_por",
            "estado_resultante",
            "registrado_por",
            "created_at",
        ]
        read_only_fields = ["registrado_por", "created_at"]


class ResumenPlanesSerializer(serializers.Serializer):
    vencidos = serializers.IntegerField()
    proximos_30_dias = serializers.IntegerField()
    al_dia = serializers.IntegerField()
    total_activos = serializers.IntegerField()


class ImportarPlanSerializer(serializers.Serializer):
    archivo = serializers.FileField()
    simular = serializers.BooleanField(default=True)
    crear_faltantes = serializers.BooleanField(default=False)


class UnidadNoEncontradaSerializer(serializers.Serializer):
    fila = serializers.IntegerField()
    codigo_activo = serializers.CharField(allow_blank=True)
    codigo_peoplesoft = serializers.CharField(allow_blank=True)
    equipo = serializers.CharField(allow_blank=True)


class ResumenImportacionPlanSerializer(serializers.Serializer):
    planes_creados = serializers.IntegerField()
    planes_actualizados = serializers.IntegerField()
    unidades_creadas = serializers.IntegerField()
    tipos_creados = serializers.IntegerField()
    codigos_peoplesoft_completados = serializers.IntegerField()
    no_encontrados = UnidadNoEncontradaSerializer(many=True)
    advertencias = serializers.ListField(child=serializers.CharField())
    simulado = serializers.BooleanField()


class FilaFichaMantencionSerializer(serializers.Serializer):
    fecha_realizacion = serializers.DateField()
    descripcion = serializers.CharField()
    empresa = serializers.CharField()
    orden_compra = serializers.CharField(source="numero_orden_compra")
    costo = serializers.DecimalField(max_digits=12, decimal_places=2)
    tipo = serializers.CharField()
    realizado_por = serializers.CharField()


class FichaMantencionSerializer(serializers.Serializer):
    area = serializers.CharField()
    sede = serializers.CharField()
    nombre_equipo = serializers.CharField()
    tipo_equipo = serializers.CharField()
    fecha_solicitud_mantenimiento = serializers.DateField(allow_null=True)
    marca = serializers.CharField()
    modelo = serializers.CharField()
    ubicacion = serializers.CharField()
    serie = serializers.CharField()
    codigo_inventario = serializers.CharField(allow_null=True)
    codigo_peoplesoft = serializers.CharField(allow_null=True)
    codigo_proyecto = serializers.CharField()
    periodo_calibracion = serializers.CharField()
    registros = FilaFichaMantencionSerializer(many=True)
