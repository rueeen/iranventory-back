"""URL configuration for the IRA inventory backend."""

from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import (
    TokenBlacklistView,
    TokenObtainPairView,
    TokenRefreshView,
)

from apps.catalogo.views import (
    AsignaturaViewSet,
    CarreraViewSet,
    CategoriaViewSet,
    TipoEquipoViewSet,
    UbicacionViewSet,
)
from apps.inventario.views import UnidadViewSet

router = DefaultRouter()
router.register("categorias", CategoriaViewSet, basename="categoria")
router.register("carreras", CarreraViewSet, basename="carrera")
router.register("asignaturas", AsignaturaViewSet, basename="asignatura")
router.register("ubicaciones", UbicacionViewSet, basename="ubicacion")
router.register("tipos-equipo", TipoEquipoViewSet, basename="tipo-equipo")
router.register("unidades", UnidadViewSet, basename="unidad")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    path("api/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("api/token/blacklist/", TokenBlacklistView.as_view(), name="token_blacklist"),
    path("api/", include(router.urls)),
]
