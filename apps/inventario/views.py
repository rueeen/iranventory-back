from django_filters import rest_framework as filters
from rest_framework import viewsets
from rest_framework.filters import SearchFilter

from apps.cuentas.permissions import SoloLecturaOPanolero

from .models import Unidad
from .serializers import UnidadSerializer


class UnidadViewSet(viewsets.ModelViewSet):
    queryset = Unidad.objects.select_related(
        "tipo_equipo",
        "tipo_equipo__categoria",
        "tipo_equipo__ubicacion_default",
        "ubicacion",
    ).prefetch_related("tipo_equipo__carreras", "tipo_equipo__asignaturas")
    serializer_class = UnidadSerializer
    permission_classes = [SoloLecturaOPanolero]
    filter_backends = [filters.DjangoFilterBackend, SearchFilter]
    filterset_fields = [
        "tipo_equipo",
        "estado",
        "situacion",
        "ubicacion",
        "requiere_revision",
    ]
    search_fields = ["codigo_activo", "tipo_equipo__nombre"]
