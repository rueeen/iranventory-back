"""Importación y exportación del formato institucional de mantención."""

import re
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from io import BytesIO

from django.core.exceptions import ValidationError
from django.db import transaction
from openpyxl import load_workbook

from apps.catalogo.models import TipoEquipo
from apps.documentos.excel import copiar_estilo_fila, extender_validacion
from apps.documentos.plantillas import ruta_plantilla
from apps.inventario.models import Unidad

from .models import PlanMantencion

ENCABEZADOS = [
    "CODIGO INVENTARIO PEOPLESOFT",
    "EQUIPO",
    "ESPECIFICACION TECNICA DETALLADA",
    "ACTIVIDAD",
    "FRECUENCIA",
    "PRIORIDAD",
    "FECHA ULTIMA MANTENCIÓN REALIZADA",
    "MANTENCIÓN REALIZADA POR",
]
TITULO = "PLAN DE MANTENCIÓN EQUIPOS DE LABORATORIO Y TALLER"


@dataclass
class ResumenImportacionPlan:
    planes_creados: int = 0
    planes_actualizados: int = 0
    unidades_creadas: int = 0
    tipos_creados: int = 0
    codigos_peoplesoft_completados: int = 0
    no_encontrados: list[dict] = field(default_factory=list)
    advertencias: list[str] = field(default_factory=list)
    simulado: bool = True

    def to_dict(self):
        return asdict(self)


def texto(valor):
    return str(valor).strip() if valor is not None else ""


def normalizar(valor):
    valor = unicodedata.normalize("NFKD", texto(valor))
    return " ".join(
        "".join(c for c in valor if not unicodedata.combining(c)).casefold().split()
    )


def _codigos(valor, fila, resumen):
    activo, peoplesoft = "", ""
    for token in texto(valor).split():
        if re.fullmatch(r"[A-Z]{2,5}\d{5,}", token):
            if activo and activo != token:
                resumen.advertencias.append(
                    f"Fila {fila}: múltiples códigos de activo."
                )
            else:
                activo = token
        elif re.fullmatch(r"\d{9,}", token):
            if peoplesoft and peoplesoft != token:
                resumen.advertencias.append(
                    f"Fila {fila}: múltiples códigos PeopleSoft."
                )
            else:
                peoplesoft = token
        else:
            resumen.advertencias.append(f"Fila {fila}: código desconocido '{token}'.")
    return activo, peoplesoft


def _opcion(valor, opciones, default, fila, nombre, resumen):
    for clave, etiqueta in opciones:
        if normalizar(valor) in {normalizar(clave), normalizar(etiqueta)}:
            return clave
    resumen.advertencias.append(
        f"Fila {fila}: {nombre} desconocida '{texto(valor)}'; se usa {default}."
    )
    return default


def _fecha(valor, fila, resumen):
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    if not texto(valor):
        return None
    try:
        return datetime.strptime(texto(valor), "%d/%m/%Y").date()
    except ValueError:
        resumen.advertencias.append(f"Fila {fila}: fecha inválida '{texto(valor)}'.")
        return None


def _columnas(hoja):
    for fila in hoja.iter_rows(min_row=1, max_row=15):
        columnas = {normalizar(c.value): c.column - 1 for c in fila if texto(c.value)}
        codigo = next((k for k in columnas if "codigo inventario" in k), None)
        if codigo and "equipo" in columnas:
            columnas[normalizar(ENCABEZADOS[0])] = columnas[codigo]
            requeridas = [normalizar(c) for c in ENCABEZADOS]
            if any(c not in columnas for c in requeridas):
                raise ValidationError(
                    "Faltan columnas del formato de plan de mantención."
                )
            return fila[0].row, [columnas[c] for c in requeridas]
    raise ValidationError(
        "No se encontró el encabezado del plan en las primeras 15 filas."
    )


def _importar_fila(valores, fila, resumen, crear_faltantes):
    (
        codigo,
        equipo,
        especificacion,
        actividad,
        frecuencia,
        prioridad,
        fecha,
        responsable,
    ) = valores
    if not texto(codigo) and not texto(equipo):
        return
    activo, peoplesoft = _codigos(codigo, fila, resumen)
    unidad = Unidad.objects.filter(codigo_activo=activo).first() if activo else None
    if unidad is None and peoplesoft:
        unidad = Unidad.objects.filter(codigo_peoplesoft=peoplesoft).first()
    if unidad is None:
        if not crear_faltantes or not texto(equipo):
            resumen.no_encontrados.append(
                {
                    "fila": fila,
                    "codigo_activo": activo,
                    "codigo_peoplesoft": peoplesoft,
                    "equipo": texto(equipo),
                }
            )
            return
        tipo = TipoEquipo.objects.filter(nombre__iexact=texto(equipo)).first()
        if tipo is None:
            tipo = TipoEquipo.objects.create(
                nombre=texto(equipo),
                especificacion=texto(especificacion),
                tipo_seguimiento=TipoEquipo.TipoSeguimiento.SERIE,
            )
            resumen.tipos_creados += 1
        unidad = Unidad.objects.create(
            tipo_equipo=tipo,
            codigo_activo=activo or None,
            codigo_peoplesoft=peoplesoft or None,
            requiere_revision=True,
        )
        resumen.unidades_creadas += 1
    elif peoplesoft:
        if unidad.codigo_peoplesoft and unidad.codigo_peoplesoft != peoplesoft:
            resumen.advertencias.append(
                f"Fila {fila}: PeopleSoft distinto del existente; no se sobrescribe."
            )
        elif not unidad.codigo_peoplesoft:
            if (
                Unidad.objects.filter(codigo_peoplesoft=peoplesoft)
                .exclude(pk=unidad.pk)
                .exists()
            ):
                resumen.advertencias.append(
                    f"Fila {fila}: PeopleSoft pertenece a otra unidad; no se asigna."
                )
            else:
                unidad.codigo_peoplesoft = peoplesoft
                unidad.save(update_fields=["codigo_peoplesoft"])
                resumen.codigos_peoplesoft_completados += 1
    tipo = unidad.tipo_equipo
    if not tipo.especificacion and texto(especificacion):
        tipo.especificacion = texto(especificacion)
        tipo.save(update_fields=["especificacion"])
    if not texto(actividad):
        raise ValidationError(f"Fila {fila}: la actividad es obligatoria.")
    plan, creado = PlanMantencion.objects.update_or_create(
        unidad=unidad,
        actividad=texto(actividad),
        defaults={
            "frecuencia": _opcion(
                frecuencia,
                PlanMantencion.Frecuencia.choices,
                "ANUAL",
                fila,
                "frecuencia",
                resumen,
            ),
            "prioridad": _opcion(
                prioridad,
                PlanMantencion.Prioridad.choices,
                "MEDIA",
                fila,
                "prioridad",
                resumen,
            ),
            "responsable": texto(responsable),
            "fecha_ultima_mantencion": _fecha(fecha, fila, resumen),
        },
    )
    plan.full_clean()
    if creado:
        resumen.planes_creados += 1
    else:
        resumen.planes_actualizados += 1


@transaction.atomic
def importar_plan(
    archivo, *, simular=True, crear_faltantes=False
) -> ResumenImportacionPlan:
    resumen = ResumenImportacionPlan(simulado=simular)
    libro = load_workbook(archivo, data_only=True)
    try:
        hoja = next(
            (h for h in libro if normalizar(h.title) == "mantencion de equipos"),
            libro.worksheets[0],
        )
        encabezado, columnas = _columnas(hoja)
        for fila, valores in enumerate(
            hoja.iter_rows(min_row=encabezado + 1, values_only=True),
            start=encabezado + 1,
        ):
            _importar_fila(
                [valores[c] for c in columnas], fila, resumen, crear_faltantes
            )
        if simular:
            transaction.set_rollback(True)
        return resumen
    finally:
        libro.close()


def exportar_plan(queryset):
    libro = load_workbook(ruta_plantilla("plan_mantencion.xlsx"))
    try:
        hoja = libro["MANTENCIÓN DE EQUIPOS"]
        ultima = 6
        for fila, plan in enumerate(queryset, start=6):
            if fila > 40:
                copiar_estilo_fila(hoja, 6, fila, range(1, 9))
            unidad = plan.unidad
            codigos = "\n".join(
                c for c in [unidad.codigo_activo, unidad.codigo_peoplesoft] if c
            )
            valores = [
                codigos,
                unidad.tipo_equipo.nombre,
                unidad.tipo_equipo.especificacion,
                plan.actividad,
                plan.get_frecuencia_display(),
                plan.get_prioridad_display(),
                plan.fecha_ultima_mantencion,
                plan.responsable,
            ]
            for columna, valor in enumerate(valores, start=1):
                celda = hoja.cell(fila, columna, valor)
                if isinstance(valor, str):
                    celda.data_type = "s"
            hoja.cell(fila, 7).number_format = "DD/MM/YYYY"
            ultima = fila
        extender_validacion(hoja, "F6:F40", ultima)
        hoja.print_area = f"A1:H{ultima}"
        hoja.page_setup.fitToWidth = 1
        hoja.page_setup.fitToHeight = 0
        hoja.sheet_properties.pageSetUpPr.fitToPage = True
        hoja.page_setup.orientation = "landscape"
        hoja.print_title_rows = "5:5"
        salida = BytesIO()
        libro.save(salida)
        return salida.getvalue()
    finally:
        libro.close()
