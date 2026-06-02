import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.catalogo.models import TipoEquipo
from apps.cuentas.models import Usuario
from apps.inventario.models import Unidad
from apps.prestamos.models import DetallePrestamo, Prestamo
from apps.prestamos.services import (
    aprobar_prestamo,
    cerrar_prestamo,
    entregar_prestamo,
    iniciar_devolucion,
    preparar_prestamo,
)


@pytest.fixture
def alumno():
    return get_user_model().objects.create_user(
        username="alumno-prestamo",
        password="clave-segura-123",
        rol=Usuario.Rol.ALUMNO,
    )


@pytest.fixture
def panolero():
    return get_user_model().objects.create_user(
        username="panolero-prestamo",
        password="clave-segura-123",
        rol=Usuario.Rol.PANOLERO,
    )


@pytest.fixture
def api_client():
    return APIClient()


@pytest.mark.django_db
def test_flujo_prestamo_serie_no_devuelto_da_de_baja_unidad(alumno):
    tipo_equipo = TipoEquipo.objects.create(nombre="Multímetro")
    unidad = Unidad.objects.create(tipo_equipo=tipo_equipo, codigo_activo="MUL-001")
    prestamo = Prestamo.objects.create(solicitante=alumno)
    detalle = DetallePrestamo.objects.create(
        prestamo=prestamo,
        tipo_equipo=tipo_equipo,
        unidad=unidad,
    )

    aprobar_prestamo(prestamo)
    preparar_prestamo(prestamo)
    entregar_prestamo(prestamo)
    iniciar_devolucion(prestamo)
    detalle.cantidad_no_devuelta = 1
    detalle.save(update_fields=["cantidad_no_devuelta"])
    cerrar_prestamo(prestamo)

    unidad.refresh_from_db()
    prestamo.refresh_from_db()
    assert unidad.situacion == Unidad.Situacion.BAJA
    assert prestamo.estado == Prestamo.Estado.CERRADA


@pytest.mark.django_db
def test_flujo_prestamo_granel_descuenta_y_repone_al_devolver(alumno):
    tipo_equipo = TipoEquipo.objects.create(
        nombre="Amarras plásticas",
        tipo_seguimiento=TipoEquipo.TipoSeguimiento.GRANEL,
        stock_granel=10,
    )
    prestamo = Prestamo.objects.create(solicitante=alumno)
    detalle = DetallePrestamo.objects.create(
        prestamo=prestamo,
        tipo_equipo=tipo_equipo,
        cantidad=4,
    )

    aprobar_prestamo(prestamo)
    preparar_prestamo(prestamo)
    entregar_prestamo(prestamo)
    tipo_equipo.refresh_from_db()
    assert tipo_equipo.stock_granel == 6

    iniciar_devolucion(prestamo)
    detalle.cantidad_devuelta = 3
    detalle.cantidad_no_devuelta = 1
    detalle.save(update_fields=["cantidad_devuelta", "cantidad_no_devuelta"])
    cerrar_prestamo(prestamo)

    tipo_equipo.refresh_from_db()
    assert tipo_equipo.stock_granel == 9


@pytest.mark.django_db
@pytest.mark.parametrize("estado", [Unidad.Estado.REPARABLE, Unidad.Estado.MALO])
def test_preparar_prestamo_serie_rechaza_unidad_disponible_no_buena(alumno, estado):
    tipo_equipo = TipoEquipo.objects.create(nombre=f"Generador {estado}")
    unidad = Unidad.objects.create(
        tipo_equipo=tipo_equipo,
        codigo_activo=f"GEN-{estado}",
        estado=estado,
    )
    prestamo = Prestamo.objects.create(solicitante=alumno)
    DetallePrestamo.objects.create(
        prestamo=prestamo,
        tipo_equipo=tipo_equipo,
        unidad=unidad,
    )

    aprobar_prestamo(prestamo)

    with pytest.raises(ValidationError):
        preparar_prestamo(prestamo)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("situacion", "estado"),
    [
        (Unidad.Situacion.REPARACION, Unidad.Estado.BUENO),
        (Unidad.Situacion.PRESTADA, Unidad.Estado.BUENO),
        (Unidad.Situacion.BAJA, Unidad.Estado.BUENO),
        (Unidad.Situacion.DISPONIBLE, Unidad.Estado.REPARABLE),
        (Unidad.Situacion.DISPONIBLE, Unidad.Estado.MALO),
    ],
)
def test_entregar_prestamo_serie_revalida_situacion_y_estado(alumno, situacion, estado):
    tipo_equipo = TipoEquipo.objects.create(nombre=f"Analizador {situacion} {estado}")
    unidad = Unidad.objects.create(tipo_equipo=tipo_equipo, codigo_activo="ANA-001")
    prestamo = Prestamo.objects.create(solicitante=alumno)
    DetallePrestamo.objects.create(
        prestamo=prestamo,
        tipo_equipo=tipo_equipo,
        unidad=unidad,
    )

    aprobar_prestamo(prestamo)
    preparar_prestamo(prestamo)
    unidad.situacion = situacion
    unidad.estado = estado
    unidad.save(update_fields=["situacion", "estado"])

    with pytest.raises(ValidationError):
        entregar_prestamo(prestamo)


@pytest.mark.django_db
def test_api_permite_editar_detalles_en_estado_solicitada(api_client, alumno, panolero):
    tipo_equipo = TipoEquipo.objects.create(
        nombre="Resistencias",
        tipo_seguimiento=TipoEquipo.TipoSeguimiento.GRANEL,
        stock_granel=10,
    )
    prestamo = Prestamo.objects.create(solicitante=alumno)
    DetallePrestamo.objects.create(
        prestamo=prestamo,
        tipo_equipo=tipo_equipo,
        cantidad=1,
    )
    api_client.force_authenticate(user=panolero)

    response = api_client.patch(
        f"/api/prestamos/{prestamo.id}/",
        {
            "detalles": [
                {
                    "tipo_equipo_id": tipo_equipo.id,
                    "cantidad": 3,
                }
            ]
        },
        format="json",
    )

    assert response.status_code == 200
    assert list(prestamo.detalles.values_list("cantidad", flat=True)) == [3]


@pytest.mark.django_db
def test_api_bloquea_editar_detalles_despues_de_aprobada(api_client, alumno, panolero):
    tipo_equipo = TipoEquipo.objects.create(
        nombre="Capacitores",
        tipo_seguimiento=TipoEquipo.TipoSeguimiento.GRANEL,
        stock_granel=10,
    )
    prestamo = Prestamo.objects.create(solicitante=alumno)
    DetallePrestamo.objects.create(
        prestamo=prestamo,
        tipo_equipo=tipo_equipo,
        cantidad=1,
    )
    aprobar_prestamo(prestamo, panolero)
    api_client.force_authenticate(user=panolero)

    response = api_client.patch(
        f"/api/prestamos/{prestamo.id}/",
        {
            "observaciones": "Cambio permitido sin tocar detalles",
            "detalles": [
                {
                    "tipo_equipo_id": tipo_equipo.id,
                    "cantidad": 4,
                }
            ],
        },
        format="json",
    )

    prestamo.refresh_from_db()
    assert response.status_code == 400
    assert "solo pueden modificarse" in str(response.data["detalles"])
    assert prestamo.observaciones == ""
    assert list(prestamo.detalles.values_list("cantidad", flat=True)) == [1]


@pytest.mark.django_db
def test_api_accion_aprobar_sigue_funcionando_con_detalles(
    api_client, alumno, panolero
):
    tipo_equipo = TipoEquipo.objects.create(
        nombre="Protoboard",
        tipo_seguimiento=TipoEquipo.TipoSeguimiento.GRANEL,
        stock_granel=10,
    )
    prestamo = Prestamo.objects.create(solicitante=alumno)
    DetallePrestamo.objects.create(
        prestamo=prestamo,
        tipo_equipo=tipo_equipo,
        cantidad=2,
    )
    api_client.force_authenticate(user=panolero)

    response = api_client.post(f"/api/prestamos/{prestamo.id}/aprobar/")

    prestamo.refresh_from_db()
    assert response.status_code == 200
    assert prestamo.estado == Prestamo.Estado.APROBADA


@pytest.mark.django_db
def test_api_registrar_devolucion_guarda_cantidades_sin_cerrar(
    api_client, alumno, panolero
):
    tipo_equipo = TipoEquipo.objects.create(
        nombre="Cables HDMI",
        tipo_seguimiento=TipoEquipo.TipoSeguimiento.GRANEL,
        stock_granel=10,
    )
    prestamo = Prestamo.objects.create(solicitante=alumno)
    detalle = DetallePrestamo.objects.create(
        prestamo=prestamo,
        tipo_equipo=tipo_equipo,
        cantidad=4,
    )
    aprobar_prestamo(prestamo, panolero)
    preparar_prestamo(prestamo, panolero)
    entregar_prestamo(prestamo, panolero)
    iniciar_devolucion(prestamo)
    api_client.force_authenticate(user=panolero)

    response = api_client.post(
        f"/api/prestamos/{prestamo.id}/registrar-devolucion/",
        {
            "detalles": [
                {
                    "id": detalle.id,
                    "cantidad_devuelta": 3,
                    "cantidad_no_devuelta": 1,
                }
            ]
        },
        format="json",
    )

    detalle.refresh_from_db()
    prestamo.refresh_from_db()
    tipo_equipo.refresh_from_db()
    assert response.status_code == 200
    assert detalle.cantidad_devuelta == 3
    assert detalle.cantidad_no_devuelta == 1
    assert prestamo.estado == Prestamo.Estado.DEVOLUCION
    assert tipo_equipo.stock_granel == 6

    cerrar_prestamo(prestamo, panolero)
    tipo_equipo.refresh_from_db()
    assert tipo_equipo.stock_granel == 9


@pytest.mark.django_db
def test_api_registrar_devolucion_rechaza_prestamo_fuera_de_devolucion(
    api_client, alumno, panolero
):
    tipo_equipo = TipoEquipo.objects.create(
        nombre="Adaptadores",
        tipo_seguimiento=TipoEquipo.TipoSeguimiento.GRANEL,
        stock_granel=10,
    )
    prestamo = Prestamo.objects.create(solicitante=alumno)
    detalle = DetallePrestamo.objects.create(
        prestamo=prestamo,
        tipo_equipo=tipo_equipo,
        cantidad=2,
    )
    api_client.force_authenticate(user=panolero)

    response = api_client.post(
        f"/api/prestamos/{prestamo.id}/registrar-devolucion/",
        {
            "detalles": [
                {
                    "id": detalle.id,
                    "cantidad_devuelta": 1,
                    "cantidad_no_devuelta": 0,
                }
            ]
        },
        format="json",
    )

    detalle.refresh_from_db()
    assert response.status_code == 400
    assert detalle.cantidad_devuelta == 0
    assert detalle.cantidad_no_devuelta == 0


@pytest.mark.django_db
def test_api_registrar_devolucion_rechaza_detalle_de_otro_prestamo(
    api_client, alumno, panolero
):
    tipo_equipo = TipoEquipo.objects.create(
        nombre="Sensores",
        tipo_seguimiento=TipoEquipo.TipoSeguimiento.GRANEL,
        stock_granel=10,
    )
    prestamo = Prestamo.objects.create(solicitante=alumno)
    otro_prestamo = Prestamo.objects.create(solicitante=alumno)
    detalle = DetallePrestamo.objects.create(
        prestamo=prestamo,
        tipo_equipo=tipo_equipo,
        cantidad=2,
    )
    detalle_otro = DetallePrestamo.objects.create(
        prestamo=otro_prestamo,
        tipo_equipo=tipo_equipo,
        cantidad=1,
    )
    aprobar_prestamo(prestamo, panolero)
    preparar_prestamo(prestamo, panolero)
    entregar_prestamo(prestamo, panolero)
    iniciar_devolucion(prestamo)
    api_client.force_authenticate(user=panolero)

    response = api_client.post(
        f"/api/prestamos/{prestamo.id}/registrar-devolucion/",
        {
            "detalles": [
                {
                    "id": detalle_otro.id,
                    "cantidad_devuelta": 1,
                    "cantidad_no_devuelta": 0,
                }
            ]
        },
        format="json",
    )

    detalle.refresh_from_db()
    detalle_otro.refresh_from_db()
    assert response.status_code == 400
    assert detalle.cantidad_devuelta == 0
    assert detalle_otro.cantidad_devuelta == 0


@pytest.mark.django_db
def test_api_registrar_devolucion_rechaza_suma_mayor_a_cantidad(
    api_client, alumno, panolero
):
    tipo_equipo = TipoEquipo.objects.create(
        nombre="Pinzas",
        tipo_seguimiento=TipoEquipo.TipoSeguimiento.GRANEL,
        stock_granel=10,
    )
    prestamo = Prestamo.objects.create(solicitante=alumno)
    detalle = DetallePrestamo.objects.create(
        prestamo=prestamo,
        tipo_equipo=tipo_equipo,
        cantidad=2,
    )
    aprobar_prestamo(prestamo, panolero)
    preparar_prestamo(prestamo, panolero)
    entregar_prestamo(prestamo, panolero)
    iniciar_devolucion(prestamo)
    api_client.force_authenticate(user=panolero)

    response = api_client.post(
        f"/api/prestamos/{prestamo.id}/registrar-devolucion/",
        {
            "detalles": [
                {
                    "id": detalle.id,
                    "cantidad_devuelta": 2,
                    "cantidad_no_devuelta": 1,
                }
            ]
        },
        format="json",
    )

    detalle.refresh_from_db()
    assert response.status_code == 400
    assert detalle.cantidad_devuelta == 0
    assert detalle.cantidad_no_devuelta == 0
