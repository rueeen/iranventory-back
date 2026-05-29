from rest_framework import serializers

from apps.catalogo.models import TipoEquipo, Ubicacion
from apps.catalogo.serializers import TipoEquipoSerializer, UbicacionSerializer

from .models import EntradaInventario, LineaEntradaInventario


class LineaEntradaInventarioSerializer(serializers.ModelSerializer):
    tipo_equipo = TipoEquipoSerializer(read_only=True)
    tipo_equipo_id = serializers.PrimaryKeyRelatedField(
        queryset=TipoEquipo.objects.all(),
        source="tipo_equipo",
        write_only=True,
    )
    ubicacion = UbicacionSerializer(read_only=True)
    ubicacion_id = serializers.PrimaryKeyRelatedField(
        allow_null=True,
        queryset=Ubicacion.objects.all(),
        required=False,
        source="ubicacion",
        write_only=True,
    )

    class Meta:
        model = LineaEntradaInventario
        fields = [
            "id",
            "tipo_equipo",
            "tipo_equipo_id",
            "cantidad",
            "codigos_activo",
            "ubicacion",
            "ubicacion_id",
            "observaciones",
        ]


class EntradaInventarioSerializer(serializers.ModelSerializer):
    lineas = LineaEntradaInventarioSerializer(many=True, required=False)

    class Meta:
        model = EntradaInventario
        fields = [
            "id",
            "numero_documento",
            "proveedor",
            "fecha_documento",
            "estado",
            "observaciones",
            "revisada_por",
            "fecha_revision",
            "aceptada_por",
            "fecha_aceptacion",
            "lineas",
        ]
        read_only_fields = [
            "estado",
            "revisada_por",
            "fecha_revision",
            "aceptada_por",
            "fecha_aceptacion",
        ]

    def create(self, validated_data):
        lineas_data = validated_data.pop("lineas", [])
        entrada = EntradaInventario.objects.create(**validated_data)
        for linea_data in lineas_data:
            LineaEntradaInventario.objects.create(entrada=entrada, **linea_data)
        return entrada

    def update(self, instance, validated_data):
        lineas_data = validated_data.pop("lineas", None)
        instance = super().update(instance, validated_data)
        if lineas_data is not None:
            instance.lineas.all().delete()
            for linea_data in lineas_data:
                LineaEntradaInventario.objects.create(entrada=instance, **linea_data)
        return instance
