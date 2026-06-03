import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from model_bakery import baker
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
    rechazar_prestamo,
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


def _tipo_serie(nombre="Equipo serie"):
    return baker.make(
        TipoEquipo,
        nombre=nombre,
        tipo_seguimiento=TipoEquipo.TipoSeguimiento.SERIE,
    )


def _tipo_granel(nombre="Equipo granel", stock_granel=10):
    return baker.make(
        TipoEquipo,
        nombre=nombre,
        tipo_seguimiento=TipoEquipo.TipoSeguimiento.GRANEL,
        stock_granel=stock_granel,
    )


def _prestamo_serie(alumno, *, unidad=None, nombre="Equipo serie"):
    tipo_equipo = unidad.tipo_equipo if unidad else _tipo_serie(nombre)
    unidad = unidad or baker.make(
        Unidad,
        tipo_equipo=tipo_equipo,
        codigo_activo=f"SER-{tipo_equipo.id or 'X'}",
        situacion=Unidad.Situacion.DISPONIBLE,
        estado=Unidad.Estado.BUENO,
    )
    prestamo = baker.make(Prestamo, solicitante=alumno)
    detalle = baker.make(
        DetallePrestamo,
        prestamo=prestamo,
        tipo_equipo=tipo_equipo,
        unidad=unidad,
        cantidad=1,
        cantidad_devuelta=0,
        cantidad_no_devuelta=0,
    )
    return prestamo, detalle, tipo_equipo, unidad


def _prestamo_granel(alumno, *, cantidad=4, stock_granel=10, nombre="Equipo granel"):
    tipo_equipo = _tipo_granel(nombre, stock_granel)
    prestamo = baker.make(Prestamo, solicitante=alumno)
    detalle = baker.make(
        DetallePrestamo,
        prestamo=prestamo,
        tipo_equipo=tipo_equipo,
        cantidad=cantidad,
        unidad=None,
        cantidad_devuelta=0,
        cantidad_no_devuelta=0,
    )
    return prestamo, detalle, tipo_equipo


@pytest.mark.django_db
def test_fase3a_no_aprueba_prestamo_sin_detalles(alumno):
    prestamo = baker.make(Prestamo, solicitante=alumno)

    with pytest.raises(ValidationError) as exc_info:
        aprobar_prestamo(prestamo)

    prestamo.refresh_from_db()
    assert "al menos un detalle" in str(exc_info.value)
    assert prestamo.estado == Prestamo.Estado.SOLICITADA


@pytest.mark.django_db
def test_fase3a_no_prepara_serie_si_unidad_no_esta_disponible(alumno):
    tipo_equipo = _tipo_serie("Osciloscopio fase 3A")
    unidad = baker.make(
        Unidad,
        tipo_equipo=tipo_equipo,
        codigo_activo="F3A-NODISP",
        situacion=Unidad.Situacion.PRESTADA,
        estado=Unidad.Estado.BUENO,
    )
    prestamo, _detalle, _tipo_equipo, _unidad = _prestamo_serie(
        alumno,
        unidad=unidad,
    )
    aprobar_prestamo(prestamo)

    with pytest.raises(ValidationError):
        preparar_prestamo(prestamo)

    prestamo.refresh_from_db()
    unidad.refresh_from_db()
    assert prestamo.estado == Prestamo.Estado.APROBADA
    assert unidad.situacion == Unidad.Situacion.PRESTADA


@pytest.mark.django_db
def test_fase3a_no_prepara_serie_si_unidad_no_esta_buena(alumno):
    tipo_equipo = _tipo_serie("Generador fase 3A")
    unidad = baker.make(
        Unidad,
        tipo_equipo=tipo_equipo,
        codigo_activo="F3A-MALO",
        situacion=Unidad.Situacion.DISPONIBLE,
        estado=Unidad.Estado.MALO,
    )
    prestamo, _detalle, _tipo_equipo, _unidad = _prestamo_serie(
        alumno,
        unidad=unidad,
    )
    aprobar_prestamo(prestamo)

    with pytest.raises(ValidationError):
        preparar_prestamo(prestamo)

    prestamo.refresh_from_db()
    unidad.refresh_from_db()
    assert prestamo.estado == Prestamo.Estado.APROBADA
    assert unidad.estado == Unidad.Estado.MALO
    assert unidad.situacion == Unidad.Situacion.DISPONIBLE


@pytest.mark.django_db
def test_fase3a_entregar_prestamo_serie_cambia_unidad_a_prestada(alumno):
    prestamo, _detalle, _tipo_equipo, unidad = _prestamo_serie(
        alumno,
        nombre="Multímetro fase 3A",
    )
    aprobar_prestamo(prestamo)
    preparar_prestamo(prestamo)

    entregar_prestamo(prestamo)

    prestamo.refresh_from_db()
    unidad.refresh_from_db()
    assert prestamo.estado == Prestamo.Estado.ENTREGADA
    assert unidad.situacion == Unidad.Situacion.PRESTADA


@pytest.mark.django_db
def test_fase3a_cerrar_devolucion_serie_devuelta_cambia_unidad_a_disponible(alumno):
    prestamo, detalle, _tipo_equipo, unidad = _prestamo_serie(
        alumno,
        nombre="Fuente fase 3A",
    )
    aprobar_prestamo(prestamo)
    preparar_prestamo(prestamo)
    entregar_prestamo(prestamo)
    iniciar_devolucion(prestamo)
    detalle.cantidad_devuelta = 1
    detalle.save(update_fields=["cantidad_devuelta"])

    cerrar_prestamo(prestamo)

    prestamo.refresh_from_db()
    unidad.refresh_from_db()
    assert prestamo.estado == Prestamo.Estado.CERRADA
    assert unidad.situacion == Unidad.Situacion.DISPONIBLE


@pytest.mark.django_db
def test_fase3a_cerrar_devolucion_serie_no_devuelta_cambia_unidad_a_baja(alumno):
    prestamo, detalle, _tipo_equipo, unidad = _prestamo_serie(
        alumno,
        nombre="Pinza amperimétrica fase 3A",
    )
    aprobar_prestamo(prestamo)
    preparar_prestamo(prestamo)
    entregar_prestamo(prestamo)
    iniciar_devolucion(prestamo)
    detalle.cantidad_no_devuelta = 1
    detalle.save(update_fields=["cantidad_no_devuelta"])

    cerrar_prestamo(prestamo)

    prestamo.refresh_from_db()
    unidad.refresh_from_db()
    assert prestamo.estado == Prestamo.Estado.CERRADA
    assert unidad.situacion == Unidad.Situacion.BAJA


@pytest.mark.django_db
def test_fase3a_entregar_prestamo_granel_descuenta_stock(alumno):
    prestamo, _detalle, tipo_equipo = _prestamo_granel(
        alumno,
        cantidad=4,
        stock_granel=10,
        nombre="Cables fase 3A",
    )
    aprobar_prestamo(prestamo)
    preparar_prestamo(prestamo)

    entregar_prestamo(prestamo)

    prestamo.refresh_from_db()
    tipo_equipo.refresh_from_db()
    assert prestamo.estado == Prestamo.Estado.ENTREGADA
    assert tipo_equipo.stock_granel == 6


@pytest.mark.django_db
def test_fase3a_cerrar_devolucion_granel_repone_solo_cantidad_devuelta(alumno):
    prestamo, detalle, tipo_equipo = _prestamo_granel(
        alumno,
        cantidad=5,
        stock_granel=10,
        nombre="Conectores fase 3A",
    )
    aprobar_prestamo(prestamo)
    preparar_prestamo(prestamo)
    entregar_prestamo(prestamo)
    iniciar_devolucion(prestamo)
    detalle.cantidad_devuelta = 2
    detalle.cantidad_no_devuelta = 3
    detalle.save(update_fields=["cantidad_devuelta", "cantidad_no_devuelta"])

    cerrar_prestamo(prestamo)

    prestamo.refresh_from_db()
    tipo_equipo.refresh_from_db()
    assert prestamo.estado == Prestamo.Estado.CERRADA
    assert tipo_equipo.stock_granel == 7


@pytest.mark.django_db
def test_fase3a_no_permite_saltar_estado_entregando_sin_preparar(alumno):
    prestamo, _detalle, _tipo_equipo, unidad = _prestamo_serie(
        alumno,
        nombre="Analizador fase 3A",
    )
    aprobar_prestamo(prestamo)

    with pytest.raises(ValidationError) as exc_info:
        entregar_prestamo(prestamo)

    prestamo.refresh_from_db()
    unidad.refresh_from_db()
    assert "preparados" in str(exc_info.value)
    assert prestamo.estado == Prestamo.Estado.APROBADA
    assert unidad.situacion == Unidad.Situacion.DISPONIBLE


@pytest.mark.django_db
def test_fase3a_no_permite_editar_detalles_cuando_prestamo_esta_aprobada(
    api_client,
    alumno,
    panolero,
):
    prestamo, detalle, tipo_equipo = _prestamo_granel(
        alumno,
        cantidad=1,
        stock_granel=10,
        nombre="Resistencias fase 3A",
    )
    aprobar_prestamo(prestamo, panolero)
    api_client.force_authenticate(user=panolero)

    response = api_client.patch(
        f"/api/prestamos/{prestamo.id}/",
        {
            "detalles": [
                {
                    "tipo_equipo_id": tipo_equipo.id,
                    "cantidad": 2,
                }
            ],
        },
        format="json",
    )

    detalle.refresh_from_db()
    prestamo.refresh_from_db()
    assert response.status_code == 400
    assert "solo pueden modificarse" in str(response.data["detalles"])
    assert prestamo.estado == Prestamo.Estado.APROBADA
    assert detalle.cantidad == 1


@pytest.mark.django_db
def test_aprobar_prestamo_rechaza_solicitud_sin_detalles(alumno):
    prestamo = Prestamo.objects.create(solicitante=alumno)

    with pytest.raises(ValidationError) as exc_info:
        aprobar_prestamo(prestamo)

    prestamo.refresh_from_db()
    assert "al menos un detalle" in str(exc_info.value)
    assert prestamo.estado == Prestamo.Estado.SOLICITADA


@pytest.mark.django_db
def test_preparar_prestamo_granel_informa_tipo_cantidad_y_disponible(alumno):
    tipo_equipo = TipoEquipo.objects.create(
        nombre="Baterías AA",
        tipo_seguimiento=TipoEquipo.TipoSeguimiento.GRANEL,
        stock_granel=1,
    )
    prestamo = Prestamo.objects.create(solicitante=alumno)
    DetallePrestamo.objects.create(
        prestamo=prestamo,
        tipo_equipo=tipo_equipo,
        cantidad=3,
    )
    aprobar_prestamo(prestamo)

    with pytest.raises(ValidationError) as exc_info:
        preparar_prestamo(prestamo)

    prestamo.refresh_from_db()
    tipo_equipo.refresh_from_db()
    mensaje = str(exc_info.value)
    assert "Baterías AA" in mensaje
    assert "solicitado 3" in mensaje
    assert "disponible 1" in mensaje
    assert prestamo.estado == Prestamo.Estado.APROBADA
    assert tipo_equipo.stock_granel == 1


@pytest.mark.django_db
def test_preparar_prestamo_serie_informa_unidad_y_tipo_no_disponible(alumno):
    tipo_equipo = TipoEquipo.objects.create(nombre="Osciloscopio")
    unidad = Unidad.objects.create(
        tipo_equipo=tipo_equipo,
        codigo_activo="OSC-001",
        situacion=Unidad.Situacion.REPARACION,
    )
    prestamo = Prestamo.objects.create(solicitante=alumno)
    DetallePrestamo.objects.create(
        prestamo=prestamo,
        tipo_equipo=tipo_equipo,
        unidad=unidad,
    )
    aprobar_prestamo(prestamo)

    with pytest.raises(ValidationError) as exc_info:
        preparar_prestamo(prestamo)

    prestamo.refresh_from_db()
    unidad.refresh_from_db()
    mensaje = str(exc_info.value)
    assert "OSC-001" in mensaje
    assert "Osciloscopio" in mensaje
    assert "no está disponible" in mensaje
    assert prestamo.estado == Prestamo.Estado.APROBADA
    assert unidad.situacion == Unidad.Situacion.REPARACION


@pytest.mark.django_db
def test_rechazar_prestamo_guarda_motivo_sin_afectar_stock_ni_unidades(
    alumno, panolero
):
    tipo_granel = TipoEquipo.objects.create(
        nombre="Jumpers",
        tipo_seguimiento=TipoEquipo.TipoSeguimiento.GRANEL,
        stock_granel=5,
    )
    tipo_serie = TipoEquipo.objects.create(nombre="Fuente DC")
    unidad = Unidad.objects.create(tipo_equipo=tipo_serie, codigo_activo="FDC-001")
    prestamo = Prestamo.objects.create(solicitante=alumno)
    DetallePrestamo.objects.create(
        prestamo=prestamo,
        tipo_equipo=tipo_granel,
        cantidad=4,
    )
    DetallePrestamo.objects.create(
        prestamo=prestamo,
        tipo_equipo=tipo_serie,
        unidad=unidad,
    )

    rechazar_prestamo(prestamo, panolero, "Sin stock suficiente")

    prestamo.refresh_from_db()
    tipo_granel.refresh_from_db()
    unidad.refresh_from_db()
    assert prestamo.estado == Prestamo.Estado.RECHAZADA
    assert prestamo.motivo_rechazo == "Sin stock suficiente"
    assert tipo_granel.stock_granel == 5
    assert unidad.situacion == Unidad.Situacion.DISPONIBLE


@pytest.mark.django_db
def test_api_rechazar_acepta_motivo_rechazo(api_client, alumno, panolero):
    prestamo = Prestamo.objects.create(solicitante=alumno)
    api_client.force_authenticate(user=panolero)

    response = api_client.post(
        f"/api/prestamos/{prestamo.id}/rechazar/",
        {"motivo_rechazo": "Solicitud duplicada"},
        format="json",
    )

    prestamo.refresh_from_db()
    assert response.status_code == 200
    assert prestamo.estado == Prestamo.Estado.RECHAZADA
    assert prestamo.motivo_rechazo == "Solicitud duplicada"


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
def test_preparar_prestamo_serie_rechaza_unidad_que_requiere_revision(alumno):
    tipo_equipo = TipoEquipo.objects.create(nombre="Fuente DC")
    unidad = Unidad.objects.create(
        tipo_equipo=tipo_equipo,
        codigo_activo="FDC-001",
        requiere_revision=True,
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
def test_entregar_prestamo_serie_rechaza_unidad_que_requiere_revision(alumno):
    tipo_equipo = TipoEquipo.objects.create(nombre="Calibrador")
    unidad = Unidad.objects.create(tipo_equipo=tipo_equipo, codigo_activo="CAL-001")
    prestamo = Prestamo.objects.create(solicitante=alumno)
    DetallePrestamo.objects.create(
        prestamo=prestamo,
        tipo_equipo=tipo_equipo,
        unidad=unidad,
    )

    aprobar_prestamo(prestamo)
    preparar_prestamo(prestamo)
    unidad.requiere_revision = True
    unidad.save(update_fields=["requiere_revision"])

    with pytest.raises(ValidationError):
        entregar_prestamo(prestamo)


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
def test_api_no_crea_prestamo_con_devolucion_anterior_a_requerida(api_client, alumno):
    api_client.force_authenticate(user=alumno)

    response = api_client.post(
        "/api/prestamos/",
        {
            "fecha_requerida": "2026-06-10T10:00:00Z",
            "fecha_devolucion_comprometida": "2026-06-09T10:00:00Z",
        },
        format="json",
    )

    assert response.status_code == 400
    assert Prestamo.objects.count() == 0
    assert "no puede ser anterior" in response.data["fecha_devolucion_comprometida"][0]


@pytest.mark.django_db
def test_api_crea_prestamo_con_devolucion_igual_o_posterior_a_requerida(
    api_client, alumno
):
    api_client.force_authenticate(user=alumno)

    response = api_client.post(
        "/api/prestamos/",
        {
            "fecha_requerida": "2026-06-10T10:00:00Z",
            "fecha_devolucion_comprometida": "2026-06-12T10:00:00Z",
        },
        format="json",
    )

    assert response.status_code == 201
    prestamo = Prestamo.objects.get()
    assert prestamo.solicitante == alumno
    assert prestamo.estado == Prestamo.Estado.SOLICITADA


@pytest.mark.django_db
def test_api_no_actualiza_prestamo_con_devolucion_anterior_a_requerida(
    api_client, alumno, panolero
):
    prestamo = Prestamo.objects.create(
        solicitante=alumno,
        fecha_requerida="2026-06-10T10:00:00Z",
        fecha_devolucion_comprometida="2026-06-12T10:00:00Z",
    )
    api_client.force_authenticate(user=panolero)

    response = api_client.patch(
        f"/api/prestamos/{prestamo.id}/",
        {"fecha_devolucion_comprometida": "2026-06-09T10:00:00Z"},
        format="json",
    )

    prestamo.refresh_from_db()
    assert response.status_code == 400
    assert "no puede ser anterior" in response.data["fecha_devolucion_comprometida"][0]
    assert prestamo.fecha_devolucion_comprometida.isoformat().startswith(
        "2026-06-12T10:00:00"
    )


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
                    "condicion": Unidad.Estado.MALO,
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
    assert detalle.condicion_devolucion == Unidad.Estado.MALO
    assert response.data["detalles"][0]["condicion_devolucion"] == Unidad.Estado.MALO
    assert prestamo.estado == Prestamo.Estado.DEVOLUCION
    assert tipo_equipo.stock_granel == 6

    get_response = api_client.get(f"/api/prestamos/{prestamo.id}/")
    assert get_response.status_code == 200
    assert get_response.data["detalles"][0]["condicion_devolucion"] == Unidad.Estado.MALO

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
