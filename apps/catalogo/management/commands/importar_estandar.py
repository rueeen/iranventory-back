from pathlib import Path
from zipfile import BadZipFile

from django.core.management.base import BaseCommand, CommandError
from openpyxl.utils.exceptions import InvalidFileException

from apps.catalogo.importacion_estandar import importar_estandar


class Command(BaseCommand):
    help = "Importa uno o varios Excel de estándar de equipamiento INACAP."

    def add_arguments(self, parser):
        parser.add_argument("rutas", nargs="+", help="Ruta(s) a archivo(s) .xlsx")

    def handle(self, *args, **options):
        for ruta in options["rutas"]:
            path = Path(ruta)
            if not path.exists():
                raise CommandError(f"No existe el archivo: {path}")
            if path.suffix.lower() != ".xlsx":
                raise CommandError(f"El archivo debe tener extensión .xlsx: {path}")

            try:
                resumen = importar_estandar(path)
            except (BadZipFile, InvalidFileException, OSError, ValueError) as exc:
                raise CommandError(
                    f"No se pudo leer el archivo .xlsx '{path}'."
                ) from exc

            for advertencia in resumen.advertencias:
                self.stdout.write(self.style.WARNING(advertencia))
            data = resumen.to_dict()
            self.stdout.write(
                self.style.SUCCESS(
                    f"{path}: tipos creados={data['tipos_creados']}; "
                    f"tipos actualizados={data['tipos_actualizados']}; "
                    f"asignaturas creadas={data['asignaturas_creadas']}; "
                    f"vínculos creados={data['vinculos_creados']}; "
                    f"advertencias={len(data['advertencias'])}"
                )
            )
