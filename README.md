# Backend Inventario Taller IRA

Backend Django 5 + Django REST Framework para el sistema de inventario y préstamo
de equipamiento del Taller de Automatización y Robótica.

## Estado actual del proyecto

El backend ya incluye los módulos principales para operar cuentas, catálogo,
inventario, compras y préstamos. El estado documentado anteriormente como
"Fase 2" quedó desactualizado: el código contiene flujo de compras con aceptación
o rechazo de órdenes y un módulo de préstamos con su ciclo de estados.

El frontend React todavía no se toca en este repositorio; esta documentación
refleja únicamente el estado actual del backend.

## Apps existentes

- `cuentas`
- `catalogo`
- `inventario`
- `compras`
- `prestamos`

## Flujo de compras

El flujo de una orden de compra es:

```text
BORRADOR -> EN_REVISION -> ACEPTADA / RECHAZADA
```

Pendiente: no asumir funcionalidades fuera de este flujo si no están presentes
en el código o en sus pruebas.

## Flujo de préstamos

El flujo principal de un préstamo es:

```text
SOLICITADA -> APROBADA -> PREPARADA -> ENTREGADA -> DEVOLUCION -> CERRADA
```

Un préstamo está atrasado solo si está `ENTREGADA`, tiene fecha de devolución
comprometida y esa fecha ya pasó. Los días de atraso se calculan por calendario
en `America/Santiago`, con mínimo uno. El filtro `?atrasado=true` lista los
atrasados y `GET /api/prestamos/resumen-atrasos/` entrega sus conteos y el más
antiguo, respetando la visibilidad por usuario.

También existe una rama de rechazo:

```text
SOLICITADA -> RECHAZADA
```

Pendiente: cualquier ampliación del flujo o integración no presente en el backend
actual debe documentarse e implementarse por separado.

## Desarrollo local

1. Crear entorno virtual e instalar dependencias:

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. Crear `.env` desde el ejemplo (usa SQLite por defecto, sin configurar BD):

   ```bash
   cp .env.example .env
   ```

3. Aplicar migraciones y levantar servidor:

   ```bash
   python manage.py migrate
   python manage.py runserver
   ```

4. Ejecutar checks de desarrollo:

   ```bash
   pytest
   ruff check .
   python manage.py makemigrations --check --dry-run
   ```

## Datos demo para test alpha

El proyecto incluye un seed idempotente para poblar datos mínimos de prueba en
entornos locales o de test alpha. Estos datos son únicamente demostrativos y no
deben cargarse en producción porque crean usuarios con una contraseña conocida.

Ejecutar después de aplicar migraciones:

```bash
python manage.py seed_alpha
```

El comando crea o actualiza usuarios, catálogo base, tipos de equipo, unidades,
préstamos en distintos estados y órdenes de compra demo sin duplicar usuarios ni
códigos de activo si se ejecuta más de una vez.

Credenciales demo:

| Usuario | Rol | Password |
| --- | --- | --- |
| `alumno_alpha` | `ALUMNO` | `Alpha12345` |
| `docente_alpha` | `DOCENTE` | `Alpha12345` |
| `panolero_alpha` | `PANOLERO` | `Alpha12345` |
| `director_alpha` | `DIRECTOR` | `Alpha12345` |

## Mantención

`PlanMantencion` define actividades preventivas por unidad, frecuencia (mensual,
trimestral, semestral o anual), prioridad y responsable. La próxima fecha se
calcula sumando meses a la última mantención, ajustando al último día del mes.
Los planes activos sin ejecución o con próxima fecha anterior a hoy están
`VENCIDO`; los que vencen entre hoy y los próximos 30 días están `PROXIMO`, y
los posteriores `AL_DIA`. Los inactivos quedan fuera de esos conteos. Las fechas
se interpretan en `America/Santiago`.

`RegistroMantencion` contiene las actividades preventivas o correctivas, fechas,
empresa/proveedor, orden de compra interna o externa, costo y colaborador.
Crear un registro actualiza el plan si la fecha es más reciente y aplica el
estado resultante de la unidad. No se permite registrar una unidad `PRESTADA`.
En `REPARACION`, un resultado `BUENO` o `REPARABLE` vuelve la unidad a
`DISPONIBLE`; `MALO` la mantiene en reparación. Editar o eliminar un registro
recalcula la última fecha de sus planes asociados según sus registros restantes,
sin volver a modificar la unidad. Ambos modelos conservan historial.

Acceso exclusivo de PAÑOLERO y DIRECTOR, incluso en lectura:

- `/api/planes-mantencion/`: CRUD; filtros `unidad`, `prioridad`, `frecuencia`,
  `activo` y `estado_plan=VENCIDO|PROXIMO|AL_DIA`; búsqueda y ordenamiento.
- `/api/planes-mantencion/resumen/`: vencidos, próximos 30 días, al día y activos.
- `/api/planes-mantencion/exportar/`: Excel institucional con los filtros de la
  consulta, sin paginación.
- `/api/planes-mantencion/importar/`: POST multipart con `archivo`, `simular`
  (por defecto `true`) y `crear_faltantes` (por defecto `false`).
- `/api/registros-mantencion/`: CRUD; filtros `unidad`, `plan`, `tipo`,
  `fecha_realizacion`, `fecha_desde` y `fecha_hasta`.
- `/api/unidades/{id}/enviar-mantencion/`: POST; solo desde `DISPONIBLE`.
- `/api/unidades/{id}/ficha-mantencion/`: GET; cabecera y registros por fecha
  ascendente para que el frontend genere la ficha PDF.

La ficha toma el área y sede de `INVENTARIO_AREA` e `INVENTARIO_SEDE`, con valores
predeterminados "Informática, Ciberseguridad y Telecomunicaciones" y "Arica".
Las unidades admiten marca, modelo, número de serie, código de proyecto y período
de calibración. `codigo_activo` es el código institucional con prefijo UTC/CFT/IPF;
`codigo_peoplesoft` es el número 1800…; ambos códigos vacíos se guardan como `null`.

El importador acepta el formato institucional (encabezados dentro de las primeras
15 filas, normalmente fila 5), separa ambos códigos y entrega un resumen con
advertencias por fila y unidades no encontradas. La simulación ejecuta la
importación completa dentro de una transacción y revierte todos sus cambios.
Las unidades creadas quedan con `requiere_revision=True`.

```bash
# Simular sin persistir cambios:
python manage.py importar_plan_mantencion plan.xlsx
# Aplicar; opcionalmente crear unidades y tipos no encontrados:
python manage.py importar_plan_mantencion plan.xlsx --aplicar --crear-faltantes
```

La exportación y posterior importación identifican el plan por unidad y actividad
para actualizarlo sin duplicarlo. El formato Excel contiene las ocho columnas
institucionales; no transporta las observaciones ni la bandera `activo` del plan.
