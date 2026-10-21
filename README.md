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
