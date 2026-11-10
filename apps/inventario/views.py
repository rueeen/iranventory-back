from django.conf import settings
from django.db.models import Max
from django_filters import rest_framework as filters
from drf_spectacular.utils import extend_schema
from rest_framework import decorators, response, viewsets
from rest_framework.filters import SearchFilter

from apps.cuentas.permissions import SoloLecturaOPanolero, SoloPanoleroODirector
from apps.mantencion.api import validar_operacion
from apps.mantencion.serializers import FichaMantencionSerializer
from apps.mantencion.services import enviar_a_mantencion

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
    search_fields = [
        "codigo_activo",
        "codigo_peoplesoft",
        "numero_serie",
        "marca",
        "modelo",
        "tipo_equipo__nombre",
    ]

    @extend_schema(request=None, responses=UnidadSerializer)
    @decorators.action(
        detail=True,
        methods=["post"],
        url_path="enviar-mantencion",
        permission_classes=[SoloPanoleroODirector],
    )
    def enviar_mantencion(self, request, pk=None):
        unidad = validar_operacion(enviar_a_mantencion, self.get_object(), request.user)
        return response.Response(self.get_serializer(unidad).data)

    @extend_schema(responses=FichaMantencionSerializer)
    @decorators.action(
        detail=True,
        methods=["get"],
        url_path="ficha-mantencion",
        permission_classes=[SoloPanoleroODirector],
    )
    def ficha_mantencion(self, request, pk=None):
        unidad = self.get_object()
        registros = unidad.registros_mantencion.order_by("fecha_realizacion", "id")
        tipo = unidad.tipo_equipo
        datos = {
            "area": settings.INVENTARIO_AREA,
            "sede": settings.INVENTARIO_SEDE,
            "nombre_equipo": tipo.nombre,
            "tipo_equipo": tipo.categoria.nombre if tipo.categoria else "",
            "fecha_solicitud_mantenimiento": registros.aggregate(
                ultima=Max("fecha_solicitud")
            )["ultima"],
            "marca": unidad.marca,
            "modelo": unidad.modelo,
            "ubicacion": str(unidad.ubicacion) if unidad.ubicacion else "",
            "serie": unidad.numero_serie,
            "codigo_inventario": unidad.codigo_activo,
            "codigo_peoplesoft": unidad.codigo_peoplesoft,
            "codigo_proyecto": unidad.codigo_proyecto,
            "periodo_calibracion": unidad.periodo_calibracion,
            "registros": registros,
        }
        return response.Response(FichaMantencionSerializer(datos).data)
