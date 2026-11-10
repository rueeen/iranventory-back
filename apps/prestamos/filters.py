from django_filters import rest_framework as filters

from .models import Prestamo


class PrestamoFilter(filters.FilterSet):
    atrasado = filters.BooleanFilter(method="filter_atrasado")

    class Meta:
        model = Prestamo
        fields = ["estado", "solicitante", "asignatura"]

    def filter_atrasado(self, queryset, name, value):
        atrasados = queryset.atrasados()
        if value:
            return atrasados
        return queryset.exclude(pk__in=atrasados.values("pk"))
