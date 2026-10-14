# Incubus

## Requisitos

Python 3.13+, [uv](https://docs.astral.sh/uv/), Node.js con [pnpm](https://pnpm.io/), PostgreSQL 18 y la API de Vladimir en ejecución.

## Ejecutar

1. Crea una base de datos vacía (por ejemplo `incubus`).
2. Backend (`http://localhost:8001`, documentación en `/docs`):
   ```bash
   cd backend
   cp .env.example .env    # DATABASE_URL, CORS_ORIGINS, VLADIMIR_API_URL
   uv sync
   uv run alembic upgrade head
   uv run uvicorn app.main:app --port 8001 --reload
   ```
3. Frontend (`http://localhost:3000`):
   ```bash
   cd frontend
   cp .env.example .env    # NUXT_PUBLIC_API_BASE=http://localhost:8001/api/v1
   pnpm install
   pnpm run dev
   ```
