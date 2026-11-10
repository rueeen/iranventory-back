from copy import deepcopy
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from io import BytesIO

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH

from apps.documentos.plantillas import ruta_plantilla
from apps.documentos.word import agregar_fila_como, escribir_celda


def _fecha(valor):
    if not valor:
        return ""
    if isinstance(valor, str):
        valor = date.fromisoformat(valor)
    return valor.strftime("%d/%m/%Y")


def _costo(valor):
    costo = Decimal(str(valor or 0))
    if not costo:
        return ""
    monto = costo.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return "$" + format(monto, ",.0f").replace(",", ".")


def generar_ficha_docx(datos_ficha: dict) -> bytes:
    documento = Document(ruta_plantilla("ficha_mantencion.docx"))
    for fila, campo in enumerate(
        ["nombre_equipo", "tipo_equipo", "area", "fecha_solicitud_mantenimiento"]
    ):
        valor = datos_ficha.get(campo, "")
        if campo == "fecha_solicitud_mantenimiento":
            valor = _fecha(valor)
        escribir_celda(documento.tables[1].cell(fila, 1), valor)
    for fila, campos in enumerate([("marca", "modelo"), ("ubicacion", "serie")]):
        for columna, campo in zip([1, 3], campos, strict=True):
            escribir_celda(
                documento.tables[2].cell(fila, columna), datos_ficha.get(campo, "")
            )
    codigos = "\n".join(
        str(datos_ficha[c])
        for c in ["codigo_inventario", "codigo_peoplesoft"]
        if datos_ficha.get(c)
    )
    escribir_celda(documento.tables[3].cell(0, 1), codigos)
    escribir_celda(
        documento.tables[3].cell(0, 3), datos_ficha.get("codigo_proyecto", "")
    )
    escribir_celda(
        documento.tables[3].cell(1, 1), datos_ficha.get("periodo_calibracion", "")
    )
    registros = sorted(
        datos_ficha.get("registros", []), key=lambda r: str(r["fecha_realizacion"])
    )
    tabla = documento.tables[4]
    while len(tabla.rows) < 3 + len(registros):
        agregar_fila_como(tabla, tabla.rows[9])
    for indice, fila in enumerate(tabla.rows[3:]):
        valores = [""] * 6
        if indice < len(registros):
            registro = registros[indice]
            columna_tipo = 0 if registro["tipo"] == "PREVENTIVO" else 1
            valores[columna_tipo] = _fecha(registro["fecha_realizacion"])
            valores[2:] = [
                registro.get("descripcion", ""),
                registro.get("empresa", ""),
                registro.get("orden_compra", ""),
                _costo(registro.get("costo")),
            ]
        for celda, valor in zip(fila.cells, valores, strict=True):
            escribir_celda(celda, valor)
    if registros and registros[-1].get("realizado_por"):
        for parrafo in documento.paragraphs:
            if parrafo.text.strip() == "___________________________":
                firma = parrafo.insert_paragraph_before(registros[-1]["realizado_por"])
                if parrafo._p.pPr is not None:
                    firma._p.insert(0, deepcopy(parrafo._p.pPr))
                if parrafo.runs and parrafo.runs[0]._r.rPr is not None:
                    firma.runs[0]._r.insert(0, deepcopy(parrafo.runs[0]._r.rPr))
                firma.alignment = WD_ALIGN_PARAGRAPH.CENTER
                break
    salida = BytesIO()
    documento.save(salida)
    return salida.getvalue()
