from django.db.models import Count, F, Q
from django_filters import rest_framework as filters
from rest_framework import viewsets
from rest_framework.filters import SearchFilter

from apps.cuentas.permissions import SoloLecturaOPanolero

from .models import Asignatura, Carrera, Categoria, TipoEquipo, Ubicacion
from .serializers import (
    AsignaturaSerializer,
    CarreraSerializer,
    CategoriaSerializer,
    TipoEquipoSerializer,
    UbicacionSerializer,
)


class TipoEquipoFilter(filters.FilterSet):
    carrera = filters.ModelChoiceFilter(
        field_name="carreras",
        queryset=Carrera.objects.all(),
    )
    asignatura = filters.ModelChoiceFilter(
        field_name="asignaturas",
        queryset=Asignatura.objects.all(),
    )
    con_brecha = filters.BooleanFilter(method="filter_con_brecha")

    class Meta:
        model = TipoEquipo
        fields = ["categoria", "tipo_seguimiento", "carrera", "asignatura"]

    def filter_con_brecha(self, queryset, name, value):
        queryset = queryset.annotate(
            unidades_activas=Count(
                "unidades",
                filter=~Q(unidades__situacion="BAJA"),
                distinct=True,
            ),
        )
        granel = Q(tipo_seguimiento=TipoEquipo.TipoSeguimiento.GRANEL)
        con_brecha = (
            granel & Q(cantidad_necesaria__gt=F("stock_granel"))
        ) | (~granel & Q(cantidad_necesaria__gt=F("unidades_activas")))

        if value:
            return queryset.filter(con_brecha).distinct()
        return queryset.exclude(con_brecha).distinct()


class CategoriaViewSet(viewsets.ModelViewSet):
    queryset = Categoria.objects.all()
    serializer_class = CategoriaSerializer
    permission_classes = [SoloLecturaOPanolero]
    search_fields = ["nombre"]
    filter_backends = [filters.DjangoFilterBackend, SearchFilter]


class CarreraViewSet(viewsets.ModelViewSet):
    queryset = Carrera.objects.all()
    serializer_class = CarreraSerializer
    permission_classes = [SoloLecturaOPanolero]
    search_fields = ["nombre"]
    filter_backends = [filters.DjangoFilterBackend, SearchFilter]


class AsignaturaViewSet(viewsets.ModelViewSet):
    queryset = Asignatura.objects.all()
    serializer_class = AsignaturaSerializer
    permission_classes = [SoloLecturaOPanolero]
    search_fields = ["codigo", "nombre"]
    filter_backends = [filters.DjangoFilterBackend, SearchFilter]


class UbicacionViewSet(viewsets.ModelViewSet):
    queryset = Ubicacion.objects.all()
    serializer_class = UbicacionSerializer
    permission_classes = [SoloLecturaOPanolero]
    search_fields = ["nombre", "sede"]
    filter_backends = [filters.DjangoFilterBackend, SearchFilter]


class TipoEquipoViewSet(viewsets.ModelViewSet):
    queryset = TipoEquipo.objects.prefetch_related(
        "carreras",
        "asignaturas",
    ).select_related("categoria", "ubicacion_default")
    serializer_class = TipoEquipoSerializer
    permission_classes = [SoloLecturaOPanolero]
    filterset_class = TipoEquipoFilter
    filter_backends = [filters.DjangoFilterBackend, SearchFilter]
    search_fields = ["nombre"]
