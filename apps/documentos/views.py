from drf_spectacular.utils import extend_schema
from rest_framework import response, serializers
from rest_framework.views import APIView

from apps.cuentas.permissions import SoloPanoleroODirector

from .pdf import pdf_disponible


class CapacidadesDocumentosSerializer(serializers.Serializer):
    pdf = serializers.BooleanField()


class CapacidadesDocumentosView(APIView):
    permission_classes = [SoloPanoleroODirector]

    @extend_schema(responses=CapacidadesDocumentosSerializer)
    def get(self, request):
        return response.Response({"pdf": pdf_disponible()})
