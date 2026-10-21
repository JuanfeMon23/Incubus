"""Entorno de pruebas: valores FALSOS de Leo, fijados antes de importar la app.

`app.core.leo` crea `LeoAuth` al importarse y exige estas variables; los tests
no deben depender de (ni leer) el `.env` real ni hablar con un Leo real.
"""

import os

os.environ.update(
    LEO_URL="http://leo.test",
    LEO_API_URL="http://leo.test/api/v1",
    APP_CLIENT_ID="incubus",
    APP_CLIENT_SECRET="secreto-falso-solo-para-tests",
    PUBLIC_URL="http://incubus.test",
    COOKIE_SECURE="false",
)
