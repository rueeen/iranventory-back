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
