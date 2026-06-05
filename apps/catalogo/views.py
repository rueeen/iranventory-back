from zipfile import BadZipFile

from django.db.models import Count, F, Q
from django_filters import rest_framework as filters
from openpyxl.utils.exceptions import InvalidFileException
from rest_framework import parsers, response, serializers, status, views, viewsets
from rest_framework.filters import SearchFilter

from apps.cuentas.permissions import SoloLecturaOPanolero

from .importacion_estandar import importar_estandar
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
        con_brecha = (granel & Q(cantidad_necesaria__gt=F("stock_granel"))) | (
            ~granel & Q(cantidad_necesaria__gt=F("unidades_activas"))
        )

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


class ImportarEstandarCatalogoView(views.APIView):
    """Carga en memoria una planilla .xlsx del estándar de equipamiento."""

    permission_classes = [SoloLecturaOPanolero]
    parser_classes = [parsers.MultiPartParser, parsers.FormParser]
    max_upload_size = 10 * 1024 * 1024

    def post(self, request):
        archivo = request.FILES.get("archivo")
        if archivo is None:
            raise serializers.ValidationError(
                {"archivo": "Debe enviar un archivo .xlsx en el campo 'archivo'."}
            )

        nombre = archivo.name or ""
        if not nombre.lower().endswith(".xlsx"):
            raise serializers.ValidationError(
                {"archivo": "El archivo debe tener extensión .xlsx."}
            )
        if archivo.size > self.max_upload_size:
            raise serializers.ValidationError(
                {"archivo": "El archivo no puede superar 10 MB."}
            )

        try:
            resumen = importar_estandar(archivo)
        except (BadZipFile, InvalidFileException, OSError, ValueError) as exc:
            raise serializers.ValidationError(
                {
                    "archivo": "No se pudo leer el archivo .xlsx. "
                    "Verifique que no esté corrupto."
                }
            ) from exc

        return response.Response(resumen.to_dict(), status=status.HTTP_200_OK)
