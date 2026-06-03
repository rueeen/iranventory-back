from pathlib import Path

import pytest
from rest_framework.test import APIClient

from apps.compras.importacion import limpiar_monto, parsear_orden_compra
from apps.compras.models import Proveedor
from apps.cuentas.models import Usuario

FIXTURE_OC = Path(__file__).parent / "fixtures" / "oc_inacap_ejemplo.txt"


@pytest.fixture
def texto_oc_inacap():
    return FIXTURE_OC.read_text()


@pytest.fixture
def panolero(db, django_user_model):
    return django_user_model.objects.create_user(
        username="panolero-import", password="clave-123", rol=Usuario.Rol.PANOLERO
    )


@pytest.fixture
def alumno(db, django_user_model):
    return django_user_model.objects.create_user(
        username="alumno-import", password="clave-123", rol=Usuario.Rol.ALUMNO
    )


@pytest.fixture
def client():
    return APIClient()


@pytest.mark.django_db
def test_parsear_orden_compra_inacap_extrae_cabecera_proveedor_e_items(texto_oc_inacap):
    data = parsear_orden_compra(texto_oc_inacap)

    assert data["numero_inacap"] == "IPN609714"
    assert data["fecha_publicacion"] == "2026-03-09"
    assert data["fecha_emision"] == "2026-03-30"
    assert data["sede_destino"] == "Arica"
    assert data["direccion_despacho"] == "AV. SANTA MARÍA 2176, ARICA"
    assert data["recibido_por_nombre"] == "JULIO MUJICA CELIS"
    assert data["comprador_nombre"] == "DANIEL GORMAZ R."
    assert data["referencia_pedido"] == "7906890"
    assert data["codigo_inversion"] == "B26SSA8371"
    assert data["tasa_iva"] == "19"

    proveedor = data["proveedor"]
    assert proveedor["razon_social"] == "INGENIERIA MCI LIMITADA"
    assert proveedor["rut"] == "76.269.680-0"
    assert proveedor["direccion"] == "LUIS THAYER OJEDA 0115 OF1104"
    assert proveedor["ciudad"] == "SANTIAGO"
    assert proveedor["contacto_nombre"] == "MAGALY RAMOS"
    assert proveedor["contacto_telefono"] == "56-2-23339579 / 56-9-76831444"
    assert proveedor["email"] == "MRAMOS@MCIELECTRONICS.CL"

    assert len(data["items"]) == 15
    assert data["items"][0] == {
        "codigo_material": "000000000000035369",
        "descripcion": "ARDUINO UNO",
        "cantidad_solicitada": 20,
        "unidad_medida": "UNI",
        "precio_unitario": "24328",
        "tipo_equipo_sugerido_id": None,
    }
    assert data["items"][-1]["codigo_material"] == "000000000000035383"
    assert data["items"][-1]["precio_unitario"] == "659620"
    assert data["advertencias"] == []


def test_limpiar_monto_clp_con_miles():
    assert limpiar_monto("$1.319.240") == 1319240
    assert limpiar_monto("$24.328") == 24328


@pytest.mark.django_db
def test_importar_preview_endpoint_devuelve_dict_estructurado(
    client, panolero, texto_oc_inacap
):
    client.force_authenticate(user=panolero)

    response = client.post(
        "/api/ordenes-compra/importar-preview/",
        {"texto": texto_oc_inacap},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["numero_inacap"] == "IPN609714"
    assert response.data["proveedor"]["rut"] == "76.269.680-0"
    assert len(response.data["items"]) == 15
    assert Proveedor.objects.count() == 0


@pytest.mark.django_db
def test_importar_preview_endpoint_rechaza_texto_vacio(client, panolero):
    client.force_authenticate(user=panolero)

    response = client.post(
        "/api/ordenes-compra/importar-preview/", {"texto": "   "}, format="json"
    )

    assert response.status_code == 400
    assert "texto" in response.data


@pytest.mark.django_db
def test_importar_preview_endpoint_rechaza_alumno(client, alumno, texto_oc_inacap):
    client.force_authenticate(user=alumno)

    response = client.post(
        "/api/ordenes-compra/importar-preview/",
        {"texto": texto_oc_inacap},
        format="json",
    )

    assert response.status_code == 403


@pytest.mark.django_db
def test_parsear_orden_compra_detecta_proveedor_existente_por_rut(texto_oc_inacap):
    proveedor = Proveedor.objects.create(
        razon_social="Ingeniería MCI Limitada",
        rut="76269680-0",
        email="contacto@example.com",
    )

    data = parsear_orden_compra(texto_oc_inacap)

    assert data["proveedor_existente_id"] == proveedor.id
