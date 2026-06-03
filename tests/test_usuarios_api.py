import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.cuentas.models import Usuario


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def director():
    return get_user_model().objects.create_user(
        username="director-usuarios",
        password="clave-segura-123",
        rol=Usuario.Rol.DIRECTOR,
    )


@pytest.fixture
def panolero():
    return get_user_model().objects.create_user(
        username="panolero-usuarios",
        password="clave-segura-123",
        rol=Usuario.Rol.PANOLERO,
    )


def crear_usuario(nombre_usuario, rol, **kwargs):
    datos = {"username": nombre_usuario, "password": "clave-segura-123", "rol": rol}
    datos.update(kwargs)
    return get_user_model().objects.create_user(**datos)


def ids_resultados(response):
    return {usuario["id"] for usuario in response.data["results"]}


def primer_resultado(response):
    return response.data["results"][0]


@pytest.mark.django_db
@pytest.mark.parametrize("rol", [Usuario.Rol.PANOLERO, Usuario.Rol.DIRECTOR])
def test_panolero_y_director_pueden_listar_usuarios(api_client, rol):
    usuario = crear_usuario(f"lector-{rol.lower()}", rol)
    api_client.force_authenticate(user=usuario)

    response = api_client.get("/api/usuarios/")

    assert response.status_code == 200


@pytest.mark.django_db
@pytest.mark.parametrize("rol", [Usuario.Rol.ALUMNO, Usuario.Rol.DOCENTE])
def test_alumno_y_docente_no_pueden_listar_usuarios(api_client, rol):
    usuario = crear_usuario(f"sin-listado-{rol.lower()}", rol)
    api_client.force_authenticate(user=usuario)

    response = api_client.get("/api/usuarios/")

    assert response.status_code == 403


@pytest.mark.django_db
def test_filtro_por_rol_devuelve_solo_usuarios_del_rol_solicitado(api_client, director):
    alumno = crear_usuario("alumno-filtrado", Usuario.Rol.ALUMNO)
    crear_usuario("docente-filtrado", Usuario.Rol.DOCENTE)
    crear_usuario("panolero-filtrado", Usuario.Rol.PANOLERO)
    api_client.force_authenticate(user=director)

    response = api_client.get("/api/usuarios/", {"rol": Usuario.Rol.ALUMNO})

    assert response.status_code == 200
    assert ids_resultados(response) == {alumno.id}
    assert primer_resultado(response)["rol"] == Usuario.Rol.ALUMNO


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("campo", "valor", "termino"),
    [
        ("username", "busqueda-username", "username"),
        ("email", "persona.buscada@example.com", "buscada@example"),
        ("first_name", "Valentina", "valentina"),
        ("last_name", "Contreras", "contreras"),
        ("rut", "12345678-9", "12345678"),
    ],
)
def test_busqueda_de_usuarios_consulta_campos_permitidos(
    api_client, director, campo, valor, termino
):
    usuario_buscado = crear_usuario(
        f"usuario-{campo}",
        Usuario.Rol.ALUMNO,
        **{campo: valor},
    )
    crear_usuario("usuario-sin-coincidencia", Usuario.Rol.ALUMNO)
    api_client.force_authenticate(user=director)

    response = api_client.get("/api/usuarios/", {"search": termino})

    assert response.status_code == 200
    assert ids_resultados(response) == {usuario_buscado.id}
    assert "password" not in primer_resultado(response)
    assert "is_staff" not in primer_resultado(response)
    assert "is_superuser" not in primer_resultado(response)


@pytest.mark.django_db
def test_busqueda_y_filtro_por_rol_se_pueden_combinar(api_client, director):
    docente = crear_usuario(
        "docente-robotica",
        Usuario.Rol.DOCENTE,
        email="robotica.docente@example.com",
    )
    crear_usuario(
        "alumno-robotica",
        Usuario.Rol.ALUMNO,
        email="robotica.alumno@example.com",
    )
    crear_usuario("docente-matematica", Usuario.Rol.DOCENTE)
    api_client.force_authenticate(user=director)

    response = api_client.get(
        "/api/usuarios/",
        {"search": "robotica", "rol": Usuario.Rol.DOCENTE},
    )

    assert response.status_code == 200
    assert ids_resultados(response) == {docente.id}


@pytest.mark.django_db
def test_api_me_sigue_disponible_para_usuario_autenticado_sin_permiso_de_listado(
    api_client,
):
    alumno = crear_usuario(
        "alumno-me",
        Usuario.Rol.ALUMNO,
        email="alumno.me@example.com",
    )
    api_client.force_authenticate(user=alumno)

    response = api_client.get("/api/me/")
    listado_response = api_client.get("/api/usuarios/")

    assert response.status_code == 200
    assert response.data["id"] == alumno.id
    assert response.data["email"] == "alumno.me@example.com"
    assert listado_response.status_code == 403


@pytest.mark.django_db
def test_solo_director_puede_modificar_usuarios(api_client, director, panolero):
    usuario = crear_usuario("usuario-a-modificar", Usuario.Rol.ALUMNO)

    api_client.force_authenticate(user=panolero)
    panolero_response = api_client.patch(
        f"/api/usuarios/{usuario.id}/",
        {"rol": Usuario.Rol.DOCENTE},
        format="json",
    )

    api_client.force_authenticate(user=director)
    director_response = api_client.patch(
        f"/api/usuarios/{usuario.id}/",
        {"rol": Usuario.Rol.DOCENTE},
        format="json",
    )

    usuario.refresh_from_db()
    assert panolero_response.status_code == 403
    assert director_response.status_code == 200
    assert usuario.rol == Usuario.Rol.DOCENTE
