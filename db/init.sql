-- =============================================
-- INIT.SQL 
-- =============================================

-- Habilitar extensiones
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Tipos ENUM
CREATE TYPE task_priority AS ENUM ('baja', 'media', 'alta');
CREATE TYPE task_status   AS ENUM ('pendiente', 'en_progreso', 'completada');

-- ====================== USUARIOS ======================
CREATE TABLE IF NOT EXISTS users (
    id              UUID PRIMARY KEY,
    nombre          VARCHAR(255) NOT NULL,
    email           VARCHAR(255) UNIQUE NOT NULL,
    password_hash   VARCHAR(512),
    google_id       VARCHAR(255) UNIQUE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ====================== TAREAS ======================
CREATE TABLE IF NOT EXISTS tasks (
    id              UUID PRIMARY KEY,
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    nombre          VARCHAR(255) NOT NULL,
    descripcion     TEXT,
    fecha_limite    TIMESTAMPTZ,
    prioridad       task_priority DEFAULT 'media',
    estado          task_status DEFAULT 'pendiente',
    nota            TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ====================== REFRESH TOKENS ======================
CREATE TABLE IF NOT EXISTS refresh_tokens (
    id              UUID PRIMARY KEY,
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash      VARCHAR(512) NOT NULL UNIQUE,
    expires_at      TIMESTAMPTZ NOT NULL,
    revoked         BOOLEAN DEFAULT FALSE,
    used_access_jti VARCHAR(36),   -- JTI del access token usado en el último renew
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ====================== ÍNDICES ======================
CREATE INDEX IF NOT EXISTS idx_tasks_user_id      ON tasks(user_id);
CREATE INDEX IF NOT EXISTS idx_tasks_created_at   ON tasks(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tasks_estado       ON tasks(estado);
CREATE INDEX IF NOT EXISTS idx_tasks_user_estado  ON tasks(user_id, estado);
CREATE INDEX IF NOT EXISTS idx_users_email        ON users(email);

-- Trigger para updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_users_updated_at ON users;
CREATE TRIGGER trigger_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS trigger_tasks_updated_at ON tasks;
CREATE TRIGGER trigger_tasks_updated_at
    BEFORE UPDATE ON tasks
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS trigger_refresh_tokens_updated_at ON refresh_tokens;
CREATE TRIGGER trigger_refresh_tokens_updated_at
    BEFORE UPDATE ON refresh_tokens
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Mensaje de confirmación (solo para logs)
DO $$
BEGIN
    RAISE NOTICE '✅ Base de datos todo_legal_app inicializada correctamente!';
END $$;