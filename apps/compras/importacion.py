"""Parser tolerante para previews de órdenes de compra INACAP pegadas como texto."""

import re
import unicodedata
from datetime import datetime
from typing import Any

from django.db import DatabaseError

from apps.catalogo.models import TipoEquipo

from .models import Proveedor

_LABEL_ALIASES = {
    "razon_social": ["razon social", "razón social"],
    "rut": ["r.u.t.", "rut", "r.u.t"],
    "direccion": ["direccion", "dirección"],
    "ciudad": ["ciudad"],
    "contacto_nombre": ["atencion", "atención", "contacto"],
    "contacto_telefono": ["telefono", "teléfono", "fono"],
    "email": ["email", "e-mail", "correo"],
    "numero_inacap": ["orden de compra", "nro oc", "numero oc", "número oc"],
    "fecha_publicacion": ["fecha publicacion", "fecha publicación"],
    "fecha_emision": ["fecha emision", "fecha emisión"],
    "sede_destino": ["sede destino", "sede"],
    "direccion_despacho": ["direccion despacho", "dirección despacho", "despacho"],
    "recibido_por_nombre": ["recibido por"],
    "comprador_nombre": ["comprador"],
    "referencia_pedido": ["referencia pedido", "pedido"],
    "codigo_inversion": ["codigo inversion", "código inversión", "cod inversion"],
    "tasa_iva": ["iva", "tasa iva"],
}

_DATE_RE = re.compile(r"\b(\d{1,2}/\d{1,2}/\d{4})\b")
_EMAIL_RE = re.compile(r"[\w.!#$%&'*+/=?^`{|}~-]+@[\w-]+(?:\.[\w-]+)+", re.I)
_ITEM_START_RE = re.compile(r"^\s*\d{1,3}\s+\d{8,}\b")
_ITEM_RE = re.compile(
    r"^\s*(?P<orden>\d{1,3})\s+"
    r"(?P<codigo>\d{8,})\s+"
    r"(?P<descripcion>.+?)\s+"
    r"(?P<cantidad>\d+(?:[.,]\d+)?)\s+"
    r"(?P<unidad>[A-ZÁÉÍÓÚÑ]{2,10})\s+"
    r"(?P<precio>\$?\s*[\d.]+(?:,\d+)?)\s+"
    r"(?P<total>\$?\s*[\d.]+(?:,\d+)?)\s*$",
    re.I,
)


def parsear_orden_compra(texto: str) -> dict[str, Any]:
    """Extrae un borrador estructurado desde texto plano de una OC INACAP."""
    resultado: dict[str, Any] = _resultado_vacio()
    advertencias = resultado["advertencias"]

    try:
        lineas = _lineas_limpias(texto or "")
        texto_normalizado = "\n".join(lineas)

        _extraer_cabecera(resultado, lineas, texto_normalizado)
        _extraer_proveedor(resultado["proveedor"], lineas)
        resultado["items"] = _extraer_items(lineas, advertencias)
        resultado["proveedor_existente_id"] = _buscar_proveedor_existente(
            resultado["proveedor"].get("rut")
        )
        _sugerir_tipos_equipo(resultado["items"])

        if not resultado["items"]:
            advertencias.append("No se detectaron ítems en el texto importado.")
        if not resultado["proveedor"].get("rut"):
            advertencias.append("No se detectó el RUT del proveedor.")
    except Exception as exc:  # noqa: BLE001 - contrato: nunca propagar errores de parseo
        advertencias.append(f"No se pudo completar el parseo: {exc}")

    return resultado


def limpiar_monto(valor: str | int | None) -> int | None:
    """Convierte montos CLP como '$1.319.240' en enteros."""
    if valor is None:
        return None
    limpio = re.sub(r"[^\d,.-]", "", str(valor)).strip()
    if not limpio:
        return None
    if "," in limpio and limpio.rfind(",") > limpio.rfind("."):
        limpio = limpio.split(",", 1)[0]
    limpio = limpio.replace(".", "").replace(",", "")
    try:
        return int(limpio)
    except ValueError:
        return None


def normalizar_rut(rut: str | None) -> str:
    """Normaliza RUT para comparación: sin puntos/espacios y DV en mayúscula."""
    if not rut:
        return ""
    return re.sub(r"[^0-9kK]", "", rut).upper()


def _resultado_vacio() -> dict[str, Any]:
    return {
        "numero_inacap": None,
        "fecha_publicacion": None,
        "fecha_emision": None,
        "sede_destino": None,
        "direccion_despacho": None,
        "recibido_por_nombre": None,
        "comprador_nombre": None,
        "referencia_pedido": None,
        "codigo_inversion": None,
        "tasa_iva": None,
        "proveedor": {
            "razon_social": None,
            "rut": None,
            "direccion": None,
            "ciudad": None,
            "contacto_nombre": None,
            "contacto_telefono": None,
            "email": None,
        },
        "proveedor_existente_id": None,
        "items": [],
        "advertencias": [],
    }


def _lineas_limpias(texto: str) -> list[str]:
    return [
        re.sub(r"\s+", " ", linea).strip()
        for linea in texto.splitlines()
        if linea.strip()
    ]


def _extraer_cabecera(resultado: dict[str, Any], lineas: list[str], texto: str) -> None:
    for campo in (
        "numero_inacap",
        "fecha_publicacion",
        "fecha_emision",
        "sede_destino",
        "direccion_despacho",
        "recibido_por_nombre",
        "comprador_nombre",
        "referencia_pedido",
        "codigo_inversion",
        "tasa_iva",
    ):
        valor = _buscar_valor_por_etiquetas(lineas, _LABEL_ALIASES[campo])
        if valor:
            resultado[campo] = valor

    numero = re.search(r"\b(IPN\d{4,})\b", texto, re.I)
    if numero:
        resultado["numero_inacap"] = numero.group(1).upper()

    for campo in ("fecha_publicacion", "fecha_emision"):
        resultado[campo] = _parsear_fecha(resultado.get(campo))

    if not resultado["fecha_publicacion"]:
        resultado["fecha_publicacion"] = _buscar_fecha_cercana(lineas, "public")
    if not resultado["fecha_emision"]:
        resultado["fecha_emision"] = _buscar_fecha_cercana(lineas, "emisi")

    if resultado.get("tasa_iva"):
        iva = re.search(r"\d+(?:[,.]\d+)?", str(resultado["tasa_iva"]))
        resultado["tasa_iva"] = iva.group(0).replace(",", ".") if iva else None


def _extraer_proveedor(proveedor: dict[str, Any], lineas: list[str]) -> None:
    bloque = _bloque_proveedor(lineas)
    fuente = bloque or lineas

    for campo, aliases in _LABEL_ALIASES.items():
        if campo not in proveedor:
            continue
        valor = _buscar_valor_por_etiquetas(fuente, aliases)
        if valor:
            proveedor[campo] = valor

    texto_bloque = "\n".join(fuente)
    rut = re.search(
        r"\b\d{1,3}(?:\.\d{3}){2}-[\dkK]\b|\b\d{7,8}-[\dkK]\b",
        texto_bloque,
    )
    if rut:
        proveedor["rut"] = rut.group(0).upper()

    email = _EMAIL_RE.search(texto_bloque)
    if email:
        proveedor["email"] = email.group(0).upper()


def _extraer_items(lineas: list[str], advertencias: list[str]) -> list[dict[str, Any]]:
    items = []
    i = 0
    while i < len(lineas):
        linea = lineas[i]
        if not _ITEM_START_RE.match(linea):
            i += 1
            continue

        combinada = linea
        inicio = i + 1
        match = _ITEM_RE.match(combinada)
        while (
            not match
            and i + 1 < len(lineas)
            and not _ITEM_START_RE.match(lineas[i + 1])
        ):
            i += 1
            combinada = f"{combinada} {lineas[i]}"
            match = _ITEM_RE.match(combinada)

        if not match:
            advertencias.append(f"No se pudo interpretar la línea {inicio}: {linea}")
            i += 1
            continue

        precio = limpiar_monto(match.group("precio"))
        cantidad = _parsear_cantidad(match.group("cantidad"))
        if precio is None or cantidad is None:
            advertencias.append(
                f"Ítem de la línea {inicio} tiene cantidad o precio inválido."
            )
            i += 1
            continue

        items.append(
            {
                "codigo_material": match.group("codigo"),
                "descripcion": _limpiar_descripcion(match.group("descripcion")),
                "cantidad_solicitada": cantidad,
                "unidad_medida": match.group("unidad").upper(),
                "precio_unitario": str(precio),
                "tipo_equipo_sugerido_id": None,
            }
        )
        i += 1
    return items


def _buscar_proveedor_existente(rut: str | None) -> int | None:
    rut_normalizado = normalizar_rut(rut)
    if not rut_normalizado:
        return None
    try:
        for proveedor in Proveedor.objects.only("id", "rut"):
            if normalizar_rut(proveedor.rut) == rut_normalizado:
                return proveedor.id
    except DatabaseError:
        return None
    return None


def _sugerir_tipos_equipo(items: list[dict[str, Any]]) -> None:
    try:
        tipos = list(TipoEquipo.objects.only("id", "nombre"))
    except DatabaseError:
        return

    for item in items:
        descripcion = _normalizar_texto(item.get("descripcion", ""))
        coincidencias = [
            tipo.id
            for tipo in tipos
            if (nombre := _normalizar_texto(tipo.nombre))
            and (nombre in descripcion or descripcion in nombre)
        ]
        if len(coincidencias) == 1:
            item["tipo_equipo_sugerido_id"] = coincidencias[0]


def _bloque_proveedor(lineas: list[str]) -> list[str]:
    inicio = next(
        (
            idx
            for idx, linea in enumerate(lineas)
            if "proveedor" in _normalizar_texto(linea)
        ),
        None,
    )
    if inicio is None:
        return []
    fin = len(lineas)
    for idx in range(inicio + 1, len(lineas)):
        normalizada = _normalizar_texto(lineas[idx])
        if _ITEM_START_RE.match(lineas[idx]) or any(
            token in normalizada
            for token in ("detalle", "items", "item ", "subtotal", "totales")
        ):
            fin = idx
            break
    return lineas[inicio:fin]


def _buscar_valor_por_etiquetas(lineas: list[str], etiquetas: list[str]) -> str | None:
    etiquetas_norm = [_normalizar_texto(etiqueta) for etiqueta in etiquetas]
    for indice, linea in enumerate(lineas):
        linea_norm = _normalizar_texto(linea)
        for etiqueta in etiquetas_norm:
            patron = rf"{re.escape(etiqueta)}\s*:?\s*(.+)$"
            match = re.search(patron, linea_norm, re.I)
            if match:
                valor = linea[match.start(1) :].strip(" :-")
                return valor or _siguiente_valor(lineas, indice)
            if linea_norm.rstrip(":") == etiqueta:
                return _siguiente_valor(lineas, indice)
    return None


def _siguiente_valor(lineas: list[str], indice: int) -> str | None:
    if indice + 1 >= len(lineas):
        return None
    siguiente = lineas[indice + 1].strip(" :-")
    return siguiente or None


def _parsear_fecha(valor: str | None) -> str | None:
    if not valor:
        return None
    match = _DATE_RE.search(valor)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%d/%m/%Y").date().isoformat()
    except ValueError:
        return None


def _buscar_fecha_cercana(lineas: list[str], token: str) -> str | None:
    for linea in lineas:
        if token in _normalizar_texto(linea):
            fecha = _parsear_fecha(linea)
            if fecha:
                return fecha
    return None


def _parsear_cantidad(valor: str) -> int | None:
    try:
        return int(float(valor.replace(".", "").replace(",", ".")))
    except ValueError:
        return None


def _limpiar_descripcion(descripcion: str) -> str:
    return re.sub(r"\s+", " ", descripcion).strip(" -")


def _normalizar_texto(valor: str) -> str:
    sin_acentos = "".join(
        caracter
        for caracter in unicodedata.normalize("NFKD", valor or "")
        if not unicodedata.combining(caracter)
    )
    return re.sub(r"\s+", " ", sin_acentos).strip().lower()
