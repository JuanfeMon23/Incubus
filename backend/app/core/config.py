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
    # Maximo de rooms por socket (una pantalla suscribe varios estados).
    socketio_max_rooms: int = 20
    # Cada cuantos segundos se desconectan los sockets con el token vencido.
    socketio_sweep_seconds: float = 30.0
    # Si se define, varios procesos comparten los rooms por Redis. Requiere el
    # paquete `redis` (`uv add redis`), que NO se instala por defecto.
    socketio_redis_url: str | None = None

    # Codigo de activacion (opcionales). Llave del HMAC del codigo; si falta se
    # deriva del secreto de la app en Leo. Vigencia en dias.
    activation_code_pepper: str | None = None
    activation_code_ttl_days: int = 30
    # Intentos de verificacion por ventana (IP+documento / solo documento).
    activation_verify_max_per_ip_doc: int = 5
    activation_verify_max_per_doc: int = 15
    activation_verify_window_seconds: int = 900

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
