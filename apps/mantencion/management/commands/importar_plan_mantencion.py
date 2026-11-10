import json
from zipfile import BadZipFile

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.mantencion.importacion_plan import importar_plan


class Command(BaseCommand):
    help = "Importa el plan institucional de mantención; por defecto solo simula."

    def add_arguments(self, parser):
        parser.add_argument("ruta")
        parser.add_argument("--aplicar", action="store_true")
        parser.add_argument("--crear-faltantes", action="store_true")

    def handle(self, *args, **options):
        try:
            resumen = importar_plan(
                options["ruta"],
                simular=not options["aplicar"],
                crear_faltantes=options["crear_faltantes"],
            )
        except (OSError, ValueError, BadZipFile, ValidationError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(resumen.to_dict(), ensure_ascii=False, indent=2))
