from rest_framework.response import Response
from rest_framework.views import APIView

from .permissions import EsPanolero


class EndpointProtegidoView(APIView):
    """Endpoint mínimo para verificar autenticación JWT."""

    def get(self, request):
        return Response({"detail": "Autenticado"})


class EndpointPanoleroView(APIView):
    """Endpoint mínimo para verificar permisos por rol."""

    permission_classes = [EsPanolero]

    def get(self, request):
        return Response({"detail": "Rol pañolero autorizado"})
