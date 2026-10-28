-- Roles de BD de minimo privilegio para Incubus (idempotente; ver README raiz,
-- seccion "Produccion (backend)").
--
--   incubus_migrator  duenio del esquema, tablas, funciones y triggers; hace el
--                     DDL. SOLO lo usa Alembic (MIGRATION_DATABASE_URL).
--   incubus_app       lo que usa la API (DATABASE_URL): SELECT/INSERT/UPDATE/DELETE
--                     sobre las tablas normales y USAGE/SELECT en las secuencias.
--                     Sin DDL, sin TRUNCATE, sin acceso a alembic_version.
--                     Tablas append-only (trigger que prohibe UPDATE y DELETE:
--                     queue_status_history, order_test_events, settings_history)
--                     solo SELECT e INSERT. Tablas con trigger que prohibe DELETE
--                     (patients, orders, ...) sin DELETE. Se descubren por los
--                     triggers: una tabla nueva con trigger queda cubierta al
--                     re-aplicar el script. Sin superusuario.
--
-- Correr como superusuario (o un rol que pueda crear roles y cambiar duenios),
-- conectado a la BD de Incubus:
--
--   psql -d incubus -v ON_ERROR_STOP=1 -f deploy/db_roles.sql
--
-- NO define contrasenas (no hay secretos en el repo): los roles se crean
-- LOGIN sin contrasena y no pueden entrar hasta que el operador la fije, p. ej.
-- con `\password incubus_app` en psql. Volver a correr despues de CADA migracion
-- que agregue tablas: los permisos no se heredan solos (a proposito: una tabla
-- nueva falla cerrada hasta que se re-aplica el script; no hay ALTER DEFAULT
-- PRIVILEGES).

-- 1) Roles (sin superusuario, sin crear BD/roles, sin saltarse RLS).
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'incubus_migrator') THEN
        CREATE ROLE incubus_migrator LOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'incubus_app') THEN
        CREATE ROLE incubus_app LOGIN;
    END IF;
END
$$;

ALTER ROLE incubus_migrator NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
ALTER ROLE incubus_app NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;

-- 2) Conexion solo a esta BD.
DO $$
BEGIN
    EXECUTE format(
        'GRANT CONNECT ON DATABASE %I TO incubus_app, incubus_migrator',
        current_database()
    );
END
$$;

-- 3) incubus_migrator es duenio del esquema y de sus tablas y funciones.
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
ALTER SCHEMA public OWNER TO incubus_migrator;

DO $$
DECLARE
    obj record;
BEGIN
    FOR obj IN
        SELECT tablename FROM pg_tables
        WHERE schemaname = 'public' AND tableowner <> 'incubus_migrator'
    LOOP
        -- Las secuencias de columnas serial/identity cambian de duenio con la tabla.
        EXECUTE format('ALTER TABLE public.%I OWNER TO incubus_migrator', obj.tablename);
    END LOOP;
    FOR obj IN
        SELECT p.oid::regprocedure AS signature
        FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'public' AND p.prokind = 'f'
          AND pg_get_userbyid(p.proowner) <> 'incubus_migrator'
          AND NOT EXISTS (
              SELECT 1 FROM pg_depend d
              WHERE d.objid = p.oid AND d.deptype = 'e'
          )
    LOOP
        EXECUTE format('ALTER FUNCTION %s OWNER TO incubus_migrator', obj.signature);
    END LOOP;
END
$$;

-- 4) incubus_app: solo DML. Se parte de cero para quitar lo que sobrara.
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM incubus_app;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM incubus_app;
GRANT USAGE ON SCHEMA public TO incubus_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO incubus_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO incubus_app;

-- 5) Excepciones, descubiertas por los triggers de la BD (tgtype: 8 = DELETE,
-- 16 = UPDATE). Append-only (UPDATE y DELETE prohibidos): solo SELECT e INSERT.
-- Solo DELETE prohibido: sin DELETE.
DO $$
DECLARE
    obj record;
BEGIN
    FOR obj IN
        SELECT DISTINCT c.oid::regclass AS tbl
        FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE NOT t.tgisinternal AND n.nspname = 'public'
          AND (t.tgtype & 8) <> 0 AND (t.tgtype & 16) <> 0
    LOOP
        EXECUTE format('REVOKE ALL ON TABLE %s FROM incubus_app', obj.tbl);
        EXECUTE format('GRANT SELECT, INSERT ON TABLE %s TO incubus_app', obj.tbl);
    END LOOP;
    FOR obj IN
        SELECT DISTINCT c.oid::regclass AS tbl
        FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE NOT t.tgisinternal AND n.nspname = 'public'
          AND (t.tgtype & 8) <> 0 AND (t.tgtype & 16) = 0
          AND pg_get_functiondef(t.tgfoid) LIKE '%INC01%'
    LOOP
        EXECUTE format('REVOKE DELETE ON TABLE %s FROM incubus_app', obj.tbl);
    END LOOP;
    -- Tabla de control de Alembic: la API no la necesita.
    IF to_regclass('public.alembic_version') IS NOT NULL THEN
        REVOKE ALL ON TABLE public.alembic_version FROM incubus_app;
    END IF;
END
$$;
