from pathlib import Path

DIRECTORIO_PLANTILLAS = Path(__file__).resolve().parent / "plantillas"


def ruta_plantilla(nombre: str) -> Path:
    ruta = DIRECTORIO_PLANTILLAS / nombre
    if Path(nombre).name != nombre or not ruta.is_file():
        raise FileNotFoundError(f"No se encontró la plantilla institucional: {nombre}")
    return ruta
