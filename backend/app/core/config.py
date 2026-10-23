"""Configuracion leida de `backend/.env`. Unico punto de acceso al entorno."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Obligatorias, sin defaults (ningun valor de entorno en el codigo), salvo las
    opcionales de tiempo real de abajo, que traen un valor seguro."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    database_url: str
    cors_origins: str
    vladimir_api_url: str

    # Tiempo real (opcionales).
    # Clientes sin cabecera `Origin` (no navegadores): rechazados salvo que se
    # active (desarrollo / herramientas internas).
    socketio_allow_no_origin: bool = False
    # Si se define, varios procesos comparten los rooms por Redis. Requiere el
    # paquete `redis` (`uv add redis`), que NO se instala por defecto.
    socketio_redis_url: str | None = None

    # Codigo de activacion (opcional): llave del HMAC del codigo; si falta se
    # deriva del secreto de la app en Leo. Vigencia e intentos: ver ajustes
    # (`app.core.runtime_settings`).
    activation_code_pepper: str | None = None

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


# Variable de entorno heredada -> clave de ajuste que inicializa.
LEGACY_SETTINGS_ENV: dict[str, str] = {
    "ACTIVATION_CODE_TTL_DAYS": "activation.code_ttl_days",
    "ACTIVATION_VERIFY_MAX_PER_IP_DOC": "activation.verify_max_per_ip_doc",
    "ACTIVATION_VERIFY_MAX_PER_DOC": "activation.verify_max_per_doc",
    "ACTIVATION_VERIFY_WINDOW_SECONDS": "activation.verify_window_seconds",
    "SOCKETIO_MAX_ROOMS": "realtime.socket_max_rooms",
    "SOCKETIO_SWEEP_SECONDS": "realtime.sweep_seconds",
}


class LegacySettingsEnv(BaseSettings):
    """Variables que existian antes de la tabla `settings`.

    Opcionales y NO documentadas: si estan en el entorno (o en `.env`),
    `initial_values()` las entrega como valor inicial de la clave nueva; el
    registro solo las usa al INSERTAR la clave (primer arranque), asi que
    despues la unica fuente es la BD. Un valor no numerico se ignora.
    """

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    activation_code_ttl_days: str | None = None
    activation_verify_max_per_ip_doc: str | None = None
    activation_verify_max_per_doc: str | None = None
    activation_verify_window_seconds: str | None = None
    socketio_max_rooms: str | None = None
    socketio_sweep_seconds: str | None = None

    def initial_values(self) -> dict[str, int]:
        values: dict[str, int] = {}
        for env_name, key in LEGACY_SETTINGS_ENV.items():
            raw = getattr(self, env_name.lower())
            if raw is None:
                continue
            try:
                values[key] = int(float(raw.strip()))
            except ValueError:
                continue
        return values


@lru_cache
def get_settings() -> Settings:
    return Settings()
