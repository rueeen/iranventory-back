from rest_framework import serializers

from .models import Asignatura, Carrera, Categoria, TipoEquipo, Ubicacion


class CategoriaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Categoria
        fields = ["id", "nombre"]


class CarreraSerializer(serializers.ModelSerializer):
    class Meta:
        model = Carrera
        fields = ["id", "nombre"]


class AsignaturaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Asignatura
        fields = ["id", "codigo", "nombre"]


class UbicacionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ubicacion
        fields = ["id", "nombre", "sede"]


class TipoEquipoSerializer(serializers.ModelSerializer):
    categoria = CategoriaSerializer(read_only=True)
    categoria_id = serializers.PrimaryKeyRelatedField(
        allow_null=True,
        queryset=Categoria.objects.all(),
        required=False,
        source="categoria",
        write_only=True,
    )
    carreras = CarreraSerializer(many=True, read_only=True)
    carreras_ids = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Carrera.objects.all(),
        required=False,
        source="carreras",
        write_only=True,
    )
    asignaturas = AsignaturaSerializer(many=True, read_only=True)
    asignaturas_ids = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Asignatura.objects.all(),
        required=False,
        source="asignaturas",
        write_only=True,
    )
    ubicacion_default = UbicacionSerializer(read_only=True)
    ubicacion_default_id = serializers.PrimaryKeyRelatedField(
        allow_null=True,
        queryset=Ubicacion.objects.all(),
        required=False,
        source="ubicacion_default",
        write_only=True,
    )
    stock_total = serializers.IntegerField(read_only=True)
    stock_disponible = serializers.IntegerField(read_only=True)
    brecha = serializers.IntegerField(read_only=True)

    class Meta:
        model = TipoEquipo
        fields = [
            "id",
            "nombre",
            "especificacion",
            "categoria",
            "categoria_id",
            "carreras",
            "carreras_ids",
            "asignaturas",
            "asignaturas_ids",
            "ubicacion_default",
            "ubicacion_default_id",
            "tipo_seguimiento",
            "valor_uf",
            "cantidad_necesaria",
            "stock_granel",
            "stock_total",
            "stock_disponible",
            "brecha",
            "observaciones",
        ]
