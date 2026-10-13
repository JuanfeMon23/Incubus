# Incubus

Aplicación del workflow del laboratorio. Consume la API `/api/v1` de **Vladimir** (catálogo de exámenes, precondiciones). Primer módulo: **Atención** (cola en tiempo real: pre-recepción → recepción → toma de muestras).

## Puesta en marcha

Requisitos: Python 3.13 + `uv`, `pnpm`, PostgreSQL 18 (usa `uuidv7()`), Vladimir corriendo.

```bash
# Backend
cd backend
cp .env.example .env          # DATABASE_URL, CORS_ORIGINS, VLADIMIR_API_URL
uv sync
uv run alembic upgrade head   # crea el esquema y siembra prioridades y motivos
uv run uvicorn app.main:app --port 8001

# Frontend
cd frontend
cp .env.example .env          # NUXT_PUBLIC_API_BASE=http://localhost:8001/api/v1
pnpm install
pnpm dev                      # http://localhost:3000
```

Pruebas: `cd backend && uv run pytest` · `cd frontend && pnpm test`.
Las pruebas del backend usan la BD de `DATABASE_URL` dentro de una transacción que se revierte.

## Reglas de negocio (módulo Atención)

- **Estados:** `pre_recepcion → en_atencion_recepcion → en_espera_toma_muestras → en_atencion_toma_muestras`, más `retirado`. Mapa único en `backend/app/modules/queue/transitions.py`.
- **Devoluciones:** recepción → pre-recepción y toma de muestras → espera; exigen motivo (`return_reasons`). **Retiro** exige motivo (`removal_reasons`). Prioridades parametrizadas (`priorities`: nombre, color, rango).
- **Historial** (`queue_status_history`): append-only (trigger), `changed_at` lo asigna la BD; base para analítica de tiempos.
- **Nada se elimina:** trigger `fn_forbid_delete` (SQLSTATE `INC01` → 409).
- **Preanalíticos:** por `category` de Vladimir se muestra uno solo, el de mayor duración (normalizada a minutos). `orders/preconditions.py`.
- **Número de orden** `AAMMNNNN`: consecutivo mensual atómico (`order_counters`), zona America/Bogotá, tope 9999/mes. `orders/order_number.py`.
- **Snapshot:** al cerrar recepción la orden guarda el examen tal como lo devolvió Vladimir.
- **Tiempo real:** `WS /ws/queue` difunde `entry_created | status_changed | removed`; las acciones van por REST y la UI re-lista al recibir un evento o reconectar.

## Pendiente

- Autenticación y roles (hoy `actor` es texto libre; no exponer a internet).
- Campos demográficos obligatorios exactos (hoy `sex`, `birth_date`, `address`: `REQUIRED_PATIENT_FIELDS`).
- Validar el parser de cédula (`patients/cedula.py`) con tramas reales (amarilla y digital).
- Tope de 9999 órdenes/mes.
- Vladimir aún no expone `lab-tests/catalog` ni autenticación máquina a máquina; se consumen los endpoints existentes.
- Vista de toma de muestras (módulo siguiente).
