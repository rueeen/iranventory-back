import pytest
from django.contrib.auth import get_user_model

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
