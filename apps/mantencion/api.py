from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers


def validar_operacion(funcion, *args, **kwargs):
    try:
        return funcion(*args, **kwargs)
    except DjangoValidationError as exc:
        detalle = exc.message_dict if hasattr(exc, "message_dict") else exc.messages
        raise serializers.ValidationError(detalle) from exc
