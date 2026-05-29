from pathlib import Path

import pytest
from django.core.management import call_command
from openpyxl import Workbook

from apps.catalogo.models import TipoEquipo
from apps.inventario.models import Unidad


def build_workbook(path: Path) -> None:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append(["Inventario taller IRA"])
    worksheet.append(["Generado para pruebas"])
    worksheet.append(["Nombre", "Cantidad Total", "Código Inventario", "Asignaturas"])
    worksheet.append(
        [
            "Multímetro digital",
            3,
            "18-0001 18-0002 Inventario Activo Fijo 2018 18-0003",
            "MATE01 FISI02",
        ]
    )
    worksheet.append(["Multímetro digital", 1, "???", "MATE01"])
    workbook.save(path)


@pytest.mark.django_db
def test_importar_inventario_crea_unidades_y_es_idempotente(tmp_path):
    workbook_path = tmp_path / "inventario.xlsx"
    build_workbook(workbook_path)

    call_command("importar_inventario", str(workbook_path))

    assert TipoEquipo.objects.count() == 1
    assert Unidad.objects.count() == 4
    assert Unidad.objects.filter(codigo_activo__isnull=False).count() == 3
    assert (
        Unidad.objects.filter(
            codigo_activo__isnull=True, requiere_revision=True
        ).count()
        == 1
    )

    call_command("importar_inventario", str(workbook_path))

    assert TipoEquipo.objects.count() == 1
    assert Unidad.objects.count() == 4
    assert Unidad.objects.filter(codigo_activo__isnull=False).count() == 3
    assert (
        Unidad.objects.filter(
            codigo_activo__isnull=True, requiere_revision=True
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_importar_inventario_dry_run_no_escribe(tmp_path):
    workbook_path = tmp_path / "inventario.xlsx"
    build_workbook(workbook_path)

    call_command("importar_inventario", str(workbook_path), dry_run=True)

    assert TipoEquipo.objects.count() == 0
    assert Unidad.objects.count() == 0
