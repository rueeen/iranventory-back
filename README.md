# Backend Inventario Taller IRA

Backend Django 5 + Django REST Framework para el sistema de inventario y préstamo
de equipamiento del Taller de Automatización y Robótica.

## Fase actual

Fase 1: estructura base del proyecto, configuración por `.env`, usuario custom y
apps de dominio iniciales.

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
