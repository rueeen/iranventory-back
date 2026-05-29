import pytest
from axes.handlers.proxy import AxesProxyHandler
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient, APIRequestFactory

from apps.cuentas.models import Usuario
from apps.cuentas.permissions import EsPanolero


@pytest.mark.django_db
def test_obtener_y_refrescar_token_con_credenciales_validas():
    usuario = get_user_model().objects.create_user(
        username="panolero",
        password="clave-segura-123",
        rol=Usuario.Rol.PANOLERO,
    )
    client = APIClient()

    response = client.post(
        "/api/token/",
        {"username": usuario.username, "password": "clave-segura-123"},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["access"]
    assert response.data["refresh"]

    refresh_response = client.post(
        "/api/token/refresh/",
        {"refresh": response.data["refresh"]},
        format="json",
    )

    assert refresh_response.status_code == 200
    assert refresh_response.data["access"]
    assert refresh_response.data["refresh"]


@pytest.mark.django_db
def test_api_catalogo_rechaza_peticion_sin_token():
    client = APIClient()

    response = client.get("/api/categorias/")

    assert response.status_code == 401


@pytest.mark.django_db
def test_es_panolero_permita_panolero_y_niega_alumno():
    factory = APIRequestFactory()
    permission = EsPanolero()
    panolero = get_user_model().objects.create_user(
        username="encargado",
        password="clave-segura-123",
        rol=Usuario.Rol.PANOLERO,
    )
    alumno = get_user_model().objects.create_user(
        username="alumno",
        password="clave-segura-123",
        rol=Usuario.Rol.ALUMNO,
    )

    request_panolero = factory.post("/api/categorias/")
    request_panolero.user = panolero
    request_alumno = factory.post("/api/categorias/")
    request_alumno.user = alumno

    assert permission.has_permission(request_panolero, view=None)
    assert not permission.has_permission(request_alumno, view=None)


@pytest.mark.django_db
def test_api_catalogo_rechaza_escritura_de_alumno_con_403():
    alumno = get_user_model().objects.create_user(
        username="alumno-endpoint",
        password="clave-segura-123",
        rol=Usuario.Rol.ALUMNO,
    )
    client = APIClient()
    client.force_authenticate(user=alumno)

    response = client.post(
        "/api/categorias/",
        {"nombre": "Herramientas"},
        format="json",
    )

    assert response.status_code == 403


@pytest.mark.django_db
def test_axes_registra_bloqueo_en_endpoint_token():
    usuario = get_user_model().objects.create_user(
        username="axes-token",
        password="clave-segura-123",
    )
    client = APIClient()

    for _ in range(5):
        client.post(
            "/api/token/",
            {"username": usuario.username, "password": "clave-incorrecta"},
            format="json",
        )

    request = APIRequestFactory().post(
        "/api/token/",
        {"username": usuario.username, "password": "clave-incorrecta"},
        format="json",
    )

    assert not AxesProxyHandler.is_allowed(request, {"username": usuario.username})
