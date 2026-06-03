import re

from rest_framework import serializers

from .models import Usuario

RUT_REGEX = re.compile(r"^\d{7,8}-[\dkK]$")


class UsuarioSerializer(serializers.ModelSerializer):
    class Meta:
        model = Usuario
        fields = ["id", "username", "email", "first_name", "last_name", "rol", "rut"]
        read_only_fields = ["id", "username", "rol"]

    def validate_rut(self, value):
        if value and not RUT_REGEX.fullmatch(value):
            raise serializers.ValidationError("El RUT debe tener formato 12345678-9.")
        return value


class RegistroSerializer(serializers.ModelSerializer):
    password = serializers.CharField(min_length=8, write_only=True)
    email = serializers.EmailField(required=True)

    class Meta:
        model = Usuario
        fields = ["username", "password", "email", "first_name", "last_name", "rut"]

    def validate_rut(self, value):
        if value and not RUT_REGEX.fullmatch(value):
            raise serializers.ValidationError("El RUT debe tener formato 12345678-9.")
        return value

    def create(self, validated_data):
        password = validated_data.pop("password")
        usuario = Usuario(**validated_data, rol=Usuario.Rol.ALUMNO)
        usuario.set_password(password)
        usuario.save()
        return usuario
