from rest_framework import serializers

from apps.catalogo.models import TipoEquipo, Ubicacion
from apps.catalogo.serializers import TipoEquipoSerializer, UbicacionSerializer

from .models import Unidad


class UnidadSerializer(serializers.ModelSerializer):
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
        model = Unidad
        fields = [
            "id",
            "tipo_equipo",
            "tipo_equipo_id",
            "codigo_activo",
            "estado",
            "situacion",
            "ubicacion",
            "ubicacion_id",
            "requiere_revision",
        ]
