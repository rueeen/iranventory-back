from copy import deepcopy

from docx.shared import Pt
from docx.table import _Row
from docx.text.paragraph import Paragraph


def escribir_celda(celda, texto):
    primero = celda.paragraphs[0]
    formato_run = deepcopy(primero.runs[0]._r.rPr) if primero.runs else None
    tenia_runs = bool(primero.runs)
    modelo = deepcopy(primero._p)
    for parrafo in celda.paragraphs:
        celda._tc.remove(parrafo._p)
    for linea in str(texto if texto is not None else "").split("\n"):
        elemento = deepcopy(modelo)
        celda._tc.append(elemento)
        parrafo = Paragraph(elemento, celda)
        parrafo.clear()
        run = parrafo.add_run(linea)
        if formato_run is not None:
            run._r.insert(0, deepcopy(formato_run))
        if not tenia_runs:
            run.font.name = "Calibri"
            run.font.size = Pt(8)


def agregar_fila_como(tabla, fila_modelo):
    elemento = deepcopy(fila_modelo._tr)
    tabla._tbl.append(elemento)
    fila = _Row(elemento, tabla)
    vistas = set()
    for celda in fila.cells:
        if celda._tc not in vistas:
            escribir_celda(celda, "")
            vistas.add(celda._tc)
    return fila
