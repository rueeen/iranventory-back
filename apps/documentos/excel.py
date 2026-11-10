from copy import copy

from openpyxl.worksheet.cell_range import CellRange


def copiar_estilo_fila(ws, fila_origen, fila_destino, columnas):
    for columna in columnas:
        origen = ws.cell(fila_origen, columna)
        destino = ws.cell(fila_destino, columna)
        for atributo in (
            "font",
            "border",
            "fill",
            "alignment",
            "number_format",
            "protection",
        ):
            setattr(destino, atributo, copy(getattr(origen, atributo)))
    ws.row_dimensions[fila_destino].height = ws.row_dimensions[fila_origen].height


def extender_validacion(ws, rango_original, ultima_fila):
    original = CellRange(rango_original)
    for validacion in ws.data_validations.dataValidation:
        rangos = []
        for rango in validacion.sqref.ranges:
            ampliado = copy(rango)
            if (
                rango.min_col == original.min_col
                and rango.max_col == original.max_col
                and rango.min_row <= original.max_row
                and rango.max_row >= original.min_row
            ):
                ampliado.max_row = max(rango.max_row, ultima_fila)
            rangos.append(str(ampliado))
        validacion.sqref = " ".join(rangos)
