from django_filters import rest_framework as filters

from .models import PlanMantencion, RegistroMantencion


class PlanMantencionFilter(filters.FilterSet):
    estado_plan = filters.ChoiceFilter(
        choices=[(valor, valor) for valor in ("VENCIDO", "PROXIMO", "AL_DIA")],
        method="filtrar_estado",
    )

    class Meta:
        model = PlanMantencion
        fields = ["unidad", "prioridad", "frecuencia", "activo"]

    def filtrar_estado(self, queryset, name, value):
        return {
            "VENCIDO": queryset.vencidos,
            "PROXIMO": queryset.proximos,
            "AL_DIA": queryset.al_dia,
        }[value]()


class RegistroMantencionFilter(filters.FilterSet):
    fecha_desde = filters.DateFilter(field_name="fecha_realizacion", lookup_expr="gte")
    fecha_hasta = filters.DateFilter(field_name="fecha_realizacion", lookup_expr="lte")

    class Meta:
        model = RegistroMantencion
        fields = ["unidad", "plan", "tipo", "fecha_realizacion"]
