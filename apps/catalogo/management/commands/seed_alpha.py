"""Carga datos mínimos de demostración para el test alpha."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.catalogo.models import Asignatura, Carrera, Categoria, TipoEquipo, Ubicacion
from apps.compras.models import ItemOrdenCompra, OrdenCompra, Proveedor
from apps.cuentas.models import Usuario
from apps.inventario.models import Unidad
from apps.prestamos.models import DetallePrestamo, Prestamo

DEMO_PASSWORD = "Alpha12345"
DEMO_MARKER = "[seed_alpha]"


@dataclass(frozen=True)
class SeedResult:
    created: int = 0
    updated: int = 0

    def __add__(self, other: SeedResult) -> SeedResult:
        return SeedResult(
            created=self.created + other.created,
            updated=self.updated + other.updated,
        )


class Command(BaseCommand):
    help = "Crea o actualiza datos demo mínimos para el test alpha."

    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:
        result = SeedResult()
        result += self._seed_users()
        catalogo = self._seed_catalogo()
        result += catalogo.pop("result")
        result += self._seed_unidades(catalogo)
        result += self._seed_prestamos(catalogo)
        result += self._seed_compras(catalogo)

        self.stdout.write(
            self.style.SUCCESS(
                "Seed alpha ejecutado correctamente: "
                f"{result.created} creados, {result.updated} actualizados."
            )
        )
        self.stdout.write(
            "Credenciales demo: alumno_alpha, docente_alpha, panolero_alpha, "
            f"director_alpha / password: {DEMO_PASSWORD}"
        )

    def _seed_users(self) -> SeedResult:
        user_model = get_user_model()
        result = SeedResult()
        users = [
            ("alumno_alpha", Usuario.Rol.ALUMNO),
            ("docente_alpha", Usuario.Rol.DOCENTE),
            ("panolero_alpha", Usuario.Rol.PANOLERO),
            ("director_alpha", Usuario.Rol.DIRECTOR),
        ]

        for username, rol in users:
            user, created = user_model.objects.update_or_create(
                username=username,
                defaults={
                    "rol": rol,
                    "is_active": True,
                    "email": f"{username}@alpha.local",
                    "first_name": username.split("_", maxsplit=1)[0].title(),
                    "last_name": "Alpha",
                },
            )
            user.set_password(DEMO_PASSWORD)
            user.save(update_fields=["password"])
            result += self._result(created)
        return result

    def _seed_catalogo(self) -> dict[str, Any]:
        result = SeedResult()

        categoria_electronica, created = Categoria.objects.update_or_create(
            nombre="Electrónica",
            defaults={},
        )
        result += self._result(created)
        categoria_componentes, created = Categoria.objects.update_or_create(
            nombre="Componentes",
            defaults={},
        )
        result += self._result(created)

        carrera, created = Carrera.objects.update_or_create(
            nombre="Automatización y Robótica",
            defaults={},
        )
        result += self._result(created)

        asignatura, created = Asignatura.objects.update_or_create(
            codigo="IRA-ALPHA",
            defaults={"nombre": "Laboratorio Alpha"},
        )
        result += self._result(created)

        laboratorio, created = Ubicacion.objects.update_or_create(
            nombre="Laboratorio IRA",
            sede="Sede Alpha",
            defaults={},
        )
        result += self._result(created)
        panol, created = Ubicacion.objects.update_or_create(
            nombre="Pañol IRA",
            sede="Sede Alpha",
            defaults={},
        )
        result += self._result(created)

        tipos = {
            "osciloscopio": self._upsert_tipo_equipo(
                nombre="Osciloscopio",
                categoria=categoria_electronica,
                ubicacion=panol,
                cantidad_necesaria=3,
                stock_granel=0,
                tipo_seguimiento=TipoEquipo.TipoSeguimiento.SERIE,
                carrera=carrera,
                asignatura=asignatura,
            ),
            "multimetro": self._upsert_tipo_equipo(
                nombre="Multímetro",
                categoria=categoria_electronica,
                ubicacion=panol,
                cantidad_necesaria=5,
                stock_granel=0,
                tipo_seguimiento=TipoEquipo.TipoSeguimiento.SERIE,
                carrera=carrera,
                asignatura=asignatura,
            ),
            "cables": self._upsert_tipo_equipo(
                nombre="Cables jumper",
                categoria=categoria_componentes,
                ubicacion=panol,
                cantidad_necesaria=100,
                stock_granel=50,
                tipo_seguimiento=TipoEquipo.TipoSeguimiento.GRANEL,
                carrera=carrera,
                asignatura=asignatura,
            ),
            "resistencias": self._upsert_tipo_equipo(
                nombre="Resistencias",
                categoria=categoria_componentes,
                ubicacion=panol,
                cantidad_necesaria=300,
                stock_granel=200,
                tipo_seguimiento=TipoEquipo.TipoSeguimiento.GRANEL,
                carrera=carrera,
                asignatura=asignatura,
            ),
        }
        result += sum((tipo_result for _, tipo_result in tipos.values()), SeedResult())

        return {
            "result": result,
            "asignatura": asignatura,
            "carrera": carrera,
            "laboratorio": laboratorio,
            "panol": panol,
            "osciloscopio": tipos["osciloscopio"][0],
            "multimetro": tipos["multimetro"][0],
            "cables": tipos["cables"][0],
            "resistencias": tipos["resistencias"][0],
        }

    def _upsert_tipo_equipo(
        self,
        *,
        nombre: str,
        categoria: Categoria,
        ubicacion: Ubicacion,
        cantidad_necesaria: int,
        stock_granel: int,
        tipo_seguimiento: str,
        carrera: Carrera,
        asignatura: Asignatura,
    ) -> tuple[TipoEquipo, SeedResult]:
        tipo_equipo, created = TipoEquipo.objects.update_or_create(
            nombre=nombre,
            defaults={
                "categoria": categoria,
                "ubicacion_default": ubicacion,
                "cantidad_necesaria": cantidad_necesaria,
                "stock_granel": stock_granel,
                "tipo_seguimiento": tipo_seguimiento,
                "observaciones": f"{DEMO_MARKER} Tipo de equipo demo alpha.",
            },
        )
        tipo_equipo.carreras.set([carrera])
        tipo_equipo.asignaturas.set([asignatura])
        return tipo_equipo, self._result(created)

    def _seed_unidades(self, catalogo: dict[str, Any]) -> SeedResult:
        unidades = [
            (
                catalogo["osciloscopio"],
                "OSC-001",
                Unidad.Situacion.DISPONIBLE,
                Unidad.Estado.BUENO,
                False,
            ),
            (
                catalogo["osciloscopio"],
                "OSC-002",
                Unidad.Situacion.DISPONIBLE,
                Unidad.Estado.BUENO,
                False,
            ),
            (
                catalogo["osciloscopio"],
                "OSC-003",
                Unidad.Situacion.REPARACION,
                Unidad.Estado.REPARABLE,
                True,
            ),
            (
                catalogo["multimetro"],
                "MUL-001",
                Unidad.Situacion.DISPONIBLE,
                Unidad.Estado.BUENO,
                False,
            ),
            (
                catalogo["multimetro"],
                "MUL-002",
                Unidad.Situacion.PRESTADA,
                Unidad.Estado.BUENO,
                False,
            ),
        ]

        result = SeedResult()
        for tipo_equipo, codigo, situacion, estado, requiere_revision in unidades:
            _, created = Unidad.objects.update_or_create(
                codigo_activo=codigo,
                defaults={
                    "tipo_equipo": tipo_equipo,
                    "situacion": situacion,
                    "estado": estado,
                    "requiere_revision": requiere_revision,
                    "ubicacion": catalogo["panol"],
                },
            )
            result += self._result(created)
        return result

    def _seed_prestamos(self, catalogo: dict[str, Any]) -> SeedResult:
        alumno = Usuario.objects.get(username="alumno_alpha")
        docente = Usuario.objects.get(username="docente_alpha")
        panolero = Usuario.objects.get(username="panolero_alpha")
        now = timezone.now()

        loans = [
            (
                "prestamo-solicitada",
                Prestamo.Estado.SOLICITADA,
                catalogo["cables"],
                None,
                10,
            ),
            (
                "prestamo-aprobada",
                Prestamo.Estado.APROBADA,
                catalogo["osciloscopio"],
                "OSC-001",
                1,
            ),
            (
                "prestamo-entregada",
                Prestamo.Estado.ENTREGADA,
                catalogo["resistencias"],
                None,
                25,
            ),
            (
                "prestamo-devolucion",
                Prestamo.Estado.DEVOLUCION,
                catalogo["multimetro"],
                "MUL-002",
                1,
            ),
        ]

        result = SeedResult()
        for index, (slug, estado, tipo_equipo, codigo_unidad, cantidad) in enumerate(
            loans,
            start=1,
        ):
            observaciones = f"{DEMO_MARKER} {slug}"
            prestamo, created = self._upsert_prestamo(
                observaciones=observaciones,
                defaults={
                    "solicitante": alumno,
                    "asignatura": catalogo["asignatura"],
                    "estado": estado,
                    "fecha_requerida": now + timezone.timedelta(days=index),
                    "fecha_devolucion_comprometida": (
                        now + timezone.timedelta(days=index + 7)
                    ),
                    "aprobado_por": docente
                    if estado != Prestamo.Estado.SOLICITADA
                    else None,
                    "preparado_por": panolero
                    if estado in {Prestamo.Estado.ENTREGADA, Prestamo.Estado.DEVOLUCION}
                    else None,
                    "entregado_por": panolero
                    if estado in {Prestamo.Estado.ENTREGADA, Prestamo.Estado.DEVOLUCION}
                    else None,
                },
            )
            unidad = (
                Unidad.objects.get(codigo_activo=codigo_unidad)
                if codigo_unidad
                else None
            )
            self._replace_detalle_prestamo(
                prestamo=prestamo,
                tipo_equipo=tipo_equipo,
                unidad=unidad,
                cantidad=cantidad,
            )
            result += self._result(created)
        return result

    def _upsert_prestamo(
        self,
        *,
        observaciones: str,
        defaults: dict[str, Any],
    ) -> tuple[Prestamo, bool]:
        prestamo = Prestamo.objects.filter(observaciones=observaciones).first()
        if prestamo is None:
            prestamo = Prestamo.objects.create(observaciones=observaciones, **defaults)
            return prestamo, True

        for field, value in defaults.items():
            setattr(prestamo, field, value)
        prestamo.save(update_fields=[*defaults.keys()])
        return prestamo, False

    def _replace_detalle_prestamo(
        self,
        *,
        prestamo: Prestamo,
        tipo_equipo: TipoEquipo,
        unidad: Unidad | None,
        cantidad: int,
    ) -> None:
        prestamo.detalles.all().delete()
        DetallePrestamo.objects.create(
            prestamo=prestamo,
            tipo_equipo=tipo_equipo,
            unidad=unidad,
            cantidad=cantidad,
            observaciones=f"{DEMO_MARKER} Detalle demo alpha.",
        )

    def _seed_compras(self, catalogo: dict[str, Any]) -> SeedResult:
        panolero = Usuario.objects.get(username="panolero_alpha")
        director = Usuario.objects.get(username="director_alpha")
        proveedor_demo, created = Proveedor.objects.update_or_create(
            rut="76.269.680-0",
            defaults={
                "razon_social": "Proveedor Demo Alpha",
                "direccion": "Av. Demo 123",
                "ciudad": "Santiago",
                "contacto_nombre": "Contacto Demo",
                "contacto_telefono": "+56 9 0000 0000",
                "email": "demo@proveedor-alpha.cl",
                "activo": True,
            },
        )

        compras = [
            (
                "OC-ALPHA-BORRADOR",
                OrdenCompra.Estado.BORRADOR,
                panolero,
                None,
                [
                    (catalogo["cables"], 50, 0, [], Decimal("150")),
                    (catalogo["resistencias"], 100, 0, [], Decimal("25")),
                ],
            ),
            (
                "OC-ALPHA-REVISION",
                OrdenCompra.Estado.EN_REVISION,
                panolero,
                director,
                [
                    (catalogo["cables"], 100, 40, [], Decimal("150")),
                    (catalogo["resistencias"], 200, 80, [], Decimal("25")),
                ],
            ),
            (
                "OC-ALPHA-ACEPTADA",
                OrdenCompra.Estado.ACEPTADA,
                panolero,
                director,
                [(catalogo["cables"], 30, 30, [], Decimal("150"))],
            ),
            (
                "OC-ALPHA-RECHAZADA",
                OrdenCompra.Estado.RECHAZADA,
                panolero,
                director,
                [(catalogo["osciloscopio"], 1, 0, [], Decimal("450000"))],
            ),
        ]

        result = self._result(created)
        for numero, estado, creado_por, revisado_por, items in compras:
            orden, created = OrdenCompra.objects.update_or_create(
                numero=numero,
                defaults={
                    "proveedor": proveedor_demo,
                    "numero_inacap": f"INA-{numero}",
                    "numero_documento": f"DOC-{numero}",
                    "sede_destino": "Sede Alpha",
                    "comprador_nombre": "Comprador Demo Alpha",
                    "tasa_iva": Decimal("19"),
                    "estado": estado,
                    "observaciones": (
                        f"{DEMO_MARKER} Orden demo {estado}. "
                        "No usar en producción."
                    ),
                    "creado_por": creado_por,
                    "revisado_por": revisado_por,
                    "fecha_revision": timezone.now() if revisado_por else None,
                },
            )
            orden.items.all().delete()
            for tipo_equipo, solicitada, recibida, codigos, precio_unitario in items:
                ItemOrdenCompra.objects.create(
                    orden_compra=orden,
                    tipo_equipo=tipo_equipo,
                    codigo_material=f"DEMO-{tipo_equipo.id}",
                    unidad_medida="UNI",
                    precio_unitario=precio_unitario,
                    cantidad_solicitada=solicitada,
                    cantidad_recibida=recibida,
                    codigos_activo=codigos,
                    ubicacion=catalogo["panol"],
                    observaciones=f"{DEMO_MARKER} Ítem demo alpha.",
                )
            result += self._result(created)
        return result

    @staticmethod
    def _result(created: bool) -> SeedResult:
        return SeedResult(created=1 if created else 0, updated=0 if created else 1)
