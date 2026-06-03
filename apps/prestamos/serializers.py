from rest_framework import serializers

from apps.catalogo.models import Asignatura, TipoEquipo
from apps.catalogo.serializers import AsignaturaSerializer, TipoEquipoSerializer
from apps.inventario.models import Unidad
from apps.inventario.serializers import UnidadSerializer

from .models import DetallePrestamo, Prestamo


class DetallePrestamoSerializer(serializers.ModelSerializer):
    tipo_equipo = TipoEquipoSerializer(read_only=True)
    tipo_equipo_id = serializers.PrimaryKeyRelatedField(
        queryset=TipoEquipo.objects.all(),
        source="tipo_equipo",
        write_only=True,
    )
    unidad = UnidadSerializer(read_only=True)
    unidad_id = serializers.PrimaryKeyRelatedField(
        allow_null=True,
        queryset=Unidad.objects.all(),
        required=False,
        source="unidad",
        write_only=True,
    )

    class Meta:
        model = DetallePrestamo
        fields = [
            "id",
            "tipo_equipo",
            "tipo_equipo_id",
            "unidad",
            "unidad_id",
            "cantidad",
            "cantidad_devuelta",
            "cantidad_no_devuelta",
            "observaciones",
        ]
        read_only_fields = ["cantidad_devuelta", "cantidad_no_devuelta"]


class RegistrarDevolucionDetalleSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    cantidad_devuelta = serializers.IntegerField(min_value=0)
    cantidad_no_devuelta = serializers.IntegerField(min_value=0)
    condicion = serializers.ChoiceField(
        choices=Unidad.Estado.choices,
        default=Unidad.Estado.BUENO,
    )


class RegistrarDevolucionSerializer(serializers.Serializer):
    detalles = RegistrarDevolucionDetalleSerializer(many=True, allow_empty=False)

    def validate_detalles(self, detalles):
        ids = [detalle["id"] for detalle in detalles]
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError(
                "No se puede informar el mismo detalle más de una vez."
            )
        return detalles


class PrestamoSerializer(serializers.ModelSerializer):
    asignatura = AsignaturaSerializer(read_only=True)
    asignatura_id = serializers.PrimaryKeyRelatedField(
        allow_null=True,
        queryset=Asignatura.objects.all(),
        required=False,
        source="asignatura",
        write_only=True,
    )
    detalles = DetallePrestamoSerializer(many=True, required=False)

    class Meta:
        model = Prestamo
        fields = [
            "id",
            "solicitante",
            "asignatura",
            "asignatura_id",
            "estado",
            "fecha_solicitud",
            "fecha_requerida",
            "fecha_devolucion_comprometida",
            "aprobado_por",
            "preparado_por",
            "entregado_por",
            "cerrado_por",
            "motivo_rechazo",
            "observaciones",
            "detalles",
        ]
        read_only_fields = [
            "solicitante",
            "estado",
            "fecha_solicitud",
            "aprobado_por",
            "preparado_por",
            "entregado_por",
            "cerrado_por",
            "motivo_rechazo",
        ]

    def create(self, validated_data):
        detalles_data = validated_data.pop("detalles", [])
        prestamo = Prestamo.objects.create(
            solicitante=self.context["request"].user,
            **validated_data,
        )
        for detalle_data in detalles_data:
            DetallePrestamo.objects.create(prestamo=prestamo, **detalle_data)
        return prestamo

    def update(self, instance, validated_data):
        detalles_data = validated_data.pop("detalles", None)
        if detalles_data is not None and instance.estado != Prestamo.Estado.SOLICITADA:
            raise serializers.ValidationError(
                {
                    "detalles": (
                        "Los detalles del préstamo solo pueden modificarse cuando "
                        "el préstamo está en estado SOLICITADA."
                    )
                }
            )

        instance = super().update(instance, validated_data)
        if detalles_data is not None:
            instance.detalles.all().delete()
            for detalle_data in detalles_data:
                DetallePrestamo.objects.create(prestamo=instance, **detalle_data)
        return instance
