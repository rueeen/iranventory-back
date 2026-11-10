from zipfile import BadZipFile

from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiTypes, extend_schema, extend_schema_view
from openpyxl.utils.exceptions import InvalidFileException
from rest_framework import decorators, parsers, response, serializers, viewsets
from rest_framework.filters import OrderingFilter, SearchFilter

from apps.cuentas.permissions import SoloPanoleroODirector

from .api import validar_operacion
from .filters import PlanMantencionFilter, RegistroMantencionFilter
from .importacion_plan import exportar_plan, importar_plan
from .models import PlanMantencion, RegistroMantencion
from .serializers import (
    ImportarPlanSerializer,
    PlanMantencionSerializer,
    RegistroMantencionSerializer,
    ResumenImportacionPlanSerializer,
    ResumenPlanesSerializer,
)
from .services import recalcular_plan, registrar_mantencion


@extend_schema_view(
    list=extend_schema(summary="Listar planes de mantención"),
    retrieve=extend_schema(summary="Consultar plan de mantención"),
    create=extend_schema(summary="Crear plan de mantención"),
    update=extend_schema(summary="Actualizar plan de mantención"),
    partial_update=extend_schema(summary="Modificar plan de mantención"),
    destroy=extend_schema(summary="Eliminar plan de mantención"),
)
class PlanMantencionViewSet(viewsets.ModelViewSet):
    queryset = PlanMantencion.objects.select_related(
        "unidad__tipo_equipo", "unidad__ubicacion"
    )
    serializer_class = PlanMantencionSerializer
    permission_classes = [SoloPanoleroODirector]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = PlanMantencionFilter
    search_fields = [
        "unidad__codigo_activo",
        "unidad__codigo_peoplesoft",
        "unidad__tipo_equipo__nombre",
        "actividad",
    ]
    ordering_fields = [
        "fecha_proxima_mantencion",
        "prioridad",
        "fecha_ultima_mantencion",
    ]

    @extend_schema(responses=ResumenPlanesSerializer, filters=False)
    @decorators.action(detail=False, methods=["get"])
    def resumen(self, request):
        queryset = self.get_queryset()
        hoy = timezone.localdate()
        return response.Response(
            ResumenPlanesSerializer(
                {
                    "vencidos": queryset.vencidos(hoy).count(),
                    "proximos_30_dias": queryset.proximos(hoy=hoy).count(),
                    "al_dia": queryset.al_dia(hoy=hoy).count(),
                    "total_activos": queryset.filter(activo=True).count(),
                }
            ).data
        )

    @extend_schema(
        responses={
            (
                200,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ): OpenApiTypes.BINARY
        }
    )
    @decorators.action(detail=False, methods=["get"], pagination_class=None)
    def exportar(self, request):
        contenido = exportar_plan(self.filter_queryset(self.get_queryset()))
        respuesta = HttpResponse(
            contenido,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        respuesta["Content-Disposition"] = (
            f'attachment; filename="Plan_de_Mantencion_{timezone.localdate()}.xlsx"'
        )
        return respuesta

    @extend_schema(
        request=ImportarPlanSerializer, responses=ResumenImportacionPlanSerializer
    )
    @decorators.action(
        detail=False, methods=["post"], parser_classes=[parsers.MultiPartParser]
    )
    def importar(self, request):
        serializer = ImportarPlanSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos = serializer.validated_data
        try:
            resumen = validar_operacion(
                importar_plan,
                datos["archivo"],
                simular=datos["simular"],
                crear_faltantes=datos["crear_faltantes"],
            )
        except (ValueError, BadZipFile, InvalidFileException) as exc:
            raise serializers.ValidationError(
                {"archivo": "El archivo Excel no es válido."}
            ) from exc
        return response.Response(
            ResumenImportacionPlanSerializer(resumen.to_dict()).data
        )


@extend_schema_view(
    list=extend_schema(summary="Listar registros de mantención"),
    retrieve=extend_schema(summary="Consultar registro de mantención"),
    create=extend_schema(summary="Registrar mantención y actualizar plan y unidad"),
    update=extend_schema(summary="Editar registro y recalcular planes asociados"),
    partial_update=extend_schema(
        summary="Modificar registro y recalcular planes asociados"
    ),
    destroy=extend_schema(summary="Eliminar registro y recalcular su plan"),
)
class RegistroMantencionViewSet(viewsets.ModelViewSet):
    queryset = RegistroMantencion.objects.select_related(
        "unidad", "unidad__tipo_equipo", "plan", "proveedor", "orden_compra"
    )
    serializer_class = RegistroMantencionSerializer
    permission_classes = [SoloPanoleroODirector]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_class = RegistroMantencionFilter
    search_fields = [
        "unidad__codigo_activo",
        "unidad__codigo_peoplesoft",
        "unidad__tipo_equipo__nombre",
        "descripcion",
        "empresa",
        "realizado_por",
    ]

    def perform_create(self, serializer):
        serializer.instance = validar_operacion(
            registrar_mantencion, serializer.validated_data, self.request.user
        )

    @transaction.atomic
    def perform_update(self, serializer):
        # Bloquea el registro antes de leer el plan anterior.
        registro = RegistroMantencion.objects.select_for_update().get(
            pk=serializer.instance.pk
        )
        anterior = registro.plan_id
        serializer.instance = registro
        validar_operacion(serializer.save)
        for plan_id in sorted(
            {p for p in (anterior, serializer.instance.plan_id) if p}
        ):
            recalcular_plan(plan_id, self.request.user)

    @transaction.atomic
    def perform_destroy(self, instance):
        registro = RegistroMantencion.objects.select_for_update().get(pk=instance.pk)
        plan_id = registro.plan_id
        registro.delete()
        recalcular_plan(plan_id, self.request.user)
