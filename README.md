# Incubus

## Requisitos

Python 3.13+, [uv](https://docs.astral.sh/uv/), Node.js con [pnpm](https://pnpm.io/), PostgreSQL 18 y la API de Vladimir en ejecución.

## Ejecutar

1. Crea una base de datos vacía (por ejemplo `incubus`).
2. Backend (`http://localhost:8001`, documentación en `/docs`):
   ```bash
   cd backend
   cp .env.example .env    # DATABASE_URL, CORS_ORIGINS, VLADIMIR_API_URL, variables de Leo
   uv sync
   uv run alembic upgrade head
   uv run python -m app.core.leo_sync   # publica los permisos de Incubus en Leo
   uv run uvicorn app.main:app --port 8001 --reload
   ```
3. Frontend (`http://localhost:3200`):
   ```bash
   cd frontend
   cp .env.example .env    # API y variables de Leo (NUXT_PUBLIC_LEO_*)
   pnpm install
   pnpm run dev
   ```

## Producción (backend)

Requisitos: PostgreSQL 18 y un superusuario de PostgreSQL para crear los roles.

Roles de BD de mínimo privilegio: `incubus_migrator` (dueño del esquema; solo Alembic) e `incubus_app` (la API: DML sin DDL ni TRUNCATE; en las tablas append-only solo SELECT/INSERT).

```bash
cd backend
psql -d incubus -v ON_ERROR_STOP=1 -f deploy/db_roles.sql   # crea los roles (sin contraseña)
psql -d incubus -c "\password incubus_migrator"             # fija las contraseñas
psql -d incubus -c "\password incubus_app"
# .env: MIGRATION_DATABASE_URL con incubus_migrator, DATABASE_URL con incubus_app
uv run alembic upgrade head                                 # corre como incubus_migrator
psql -d incubus -v ON_ERROR_STOP=1 -f deploy/db_roles.sql   # re-aplicar tras cada migración que agregue tablas
uv run uvicorn app.main:app --port 8001                     # corre como incubus_app
```

## Datos de prueba (solo desarrollo)

Con Leo, Vladimir y el backend de Incubus arrancados, genera órdenes finalizadas de un paciente existente recorriendo todo el flujo por la API (por defecto 10 órdenes para CC 792083643; tarda unos minutos):

```bash
cd backend
uv run python -m scripts.seed_demo_flow
uv run python -m scripts.seed_demo_flow --document-type CC --document-number 792083643 --count 10
```

Usa el administrador de desarrollo de `leo/backend/.env` (o `LEO_ADMIN_USERNAME`/`LEO_ADMIN_PASSWORD`; `--leo-env` para otra ruta). Si el paciente no existe aborta, salvo `--create-patient`.
