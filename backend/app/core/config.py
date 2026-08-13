"""Configuración de la aplicación.

Toda la configuración proviene de variables de entorno (12-factor). No se admiten
valores por defecto para secretos: la aplicación se niega a arrancar si faltan,
en lugar de operar con una clave conocida y publicada en el repositorio.

Portado de GSC ONE. El prefijo de variables cambia de `GSC_` a `SIGREP_` y se
añaden los parámetros propios del reporte (umbrales del semáforo, fuente de
venta).
"""

from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
from typing import Any, Literal

from pydantic import Field, SecretStr, computed_field, field_validator
from pydantic.fields import FieldInfo
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_settings.sources.providers.env import EnvSettingsSource


class _CSVEnvSource(EnvSettingsSource):
    """Env source que acepta listas como CSV además de JSON."""

    def prepare_field_value(
        self,
        field_name: str,
        field: FieldInfo,
        value: Any,
        value_is_complex: bool,
    ) -> Any:
        is_complex, _ = self._field_is_complex(field)
        if (
            (is_complex or value_is_complex)
            and isinstance(value, str)
            and not value.lstrip().startswith(("[", "{"))
        ):
            return [item.strip() for item in value.split(",") if item.strip()]
        return super().prepare_field_value(field_name, field, value, value_is_complex)


Entorno = Literal["local", "desarrollo", "pruebas", "produccion"]
MotorBD = Literal["postgresql", "mssql"]
#: Implementación del puerto `FuenteVenta` (§5 de la especificación). Cambiar de
#: una a otra es una variable de entorno, nunca un refactor.
FuenteVentaConfigurada = Literal["excel", "siesa"]

#: Esquemas heredados que los proveedores gestionados siguen entregando y que
#: SQLAlchemy 2 ya no reconoce.
_ALIAS_ESQUEMA = {
    "postgres://": "postgresql+psycopg://",
    "postgresql://": "postgresql+psycopg://",
    "postgresql+psycopg2://": "postgresql+psycopg://",
}


def _normalizar_url(url: str) -> str:
    """Ajusta el esquema de una URL de conexión al driver instalado."""
    for viejo, nuevo in _ALIAS_ESQUEMA.items():
        if url.startswith(viejo):
            return nuevo + url[len(viejo) :]
    return url


class Settings(BaseSettings):
    """Parámetros de ejecución de SIGREP."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="SIGREP_",
        extra="ignore",
        frozen=True,
    )

    @classmethod
    def settings_customise_sources(cls, settings_cls, **kwargs):  # type: ignore[no-untyped-def,override]
        sources = super().settings_customise_sources(settings_cls, **kwargs)
        return tuple(
            _CSVEnvSource(settings_cls) if isinstance(s, EnvSettingsSource) else s for s in sources
        )

    # ── Identidad de la aplicación ────────────────────────────────────────────
    nombre_app: str = "SIGREP"
    version: str = "1.0.0"
    entorno: Entorno = "local"
    api_prefix: str = "/api/v1"

    # ── Seguridad ─────────────────────────────────────────────────────────────
    secret_key: SecretStr = Field(
        ...,
        description="Clave HMAC para firmar los JWT. Mínimo 32 caracteres.",
    )
    jwt_algoritmo: str = "HS256"
    access_token_minutos: int = Field(default=30, ge=5, le=480)
    refresh_token_dias: int = Field(default=7, ge=1, le=30)

    # Bloqueo de cuenta tras intentos fallidos (mitiga fuerza bruta).
    max_intentos_login: int = Field(default=5, ge=3, le=10)
    minutos_bloqueo_cuenta: int = Field(default=15, ge=5, le=120)

    cors_origenes: list[str] = Field(default_factory=list)

    #: Nombres de host que la API acepta en producción (defensa contra Host
    #: header injection). Si se deja vacío se derivan de `cors_origenes`, que no
    #: siempre coinciden: detrás de un proxy inverso el `Host` que llega es el
    #: del dominio público mientras que CORS puede estar configurado con otro
    #: origen, y el síntoma —400 «Invalid host header»— no menciona nunca la
    #: palabra CORS.
    hosts_permitidos: list[str] = Field(default_factory=list)

    # ── Base de datos ─────────────────────────────────────────────────────────
    #: Motor de destino. El esquema es idéntico en ambos: los modelos usan tipos
    #: genéricos de SQLAlchemy y las migraciones se generan sin dialecto.
    db_motor: MotorBD = "postgresql"

    db_servidor: str = "localhost"
    db_puerto: int = 5432
    db_nombre: str = "sigrep"
    db_usuario: str = "sigrep_app"
    db_password: SecretStr = SecretStr("")
    #: Solo aplica a SQL Server.
    db_driver: str = "ODBC Driver 18 for SQL Server"
    db_encrypt: bool = True
    db_trust_cert: bool = False
    db_pool_size: int = Field(default=10, ge=1, le=100)
    db_max_overflow: int = Field(default=20, ge=0, le=100)
    db_pool_recycle_seg: int = 1800
    db_echo: bool = False

    # Permite apuntar a SQLite en pruebas sin tocar el resto de la configuración.
    db_url_override: str | None = None

    # ── Reglas de negocio parametrizables ─────────────────────────────────────
    #: Umbral del semáforo (§4.1). El verde es `cumplimiento >= ideal`; el
    #: amarillo llega hasta este factor del ideal y por debajo es rojo.
    #: PENDIENTE DE CONFIRMAR CON EL USUARIO: supuesto 0.90.
    factor_semaforo_amarillo: Decimal = Field(default=Decimal("0.90"), gt=0, le=1)

    #: Días hábiles sembrados para las zonas cuyo calendario aún no confirma el
    #: negocio (§8.1 de la especificación). Supuesto: 28.
    dias_habiles_por_defecto: Decimal = Field(default=Decimal("28"), gt=0, le=31)

    #: Implementación activa del puerto `FuenteVenta` (§5). `excel` lee el libro
    #: que hoy arma el negocio; `siesa` responde 501 mientras su API no llegue.
    fuente_venta: FuenteVentaConfigurada = "excel"

    #: Ruta del libro que lee `FuenteVentaExcel` en `POST /ingesta/ejecutar`.
    #: Sin ella, la carga automática falla con un mensaje que dice qué
    #: configurar, y queda el camino de `POST /ingesta/archivo`, que trae el
    #: libro en la petición. No se le pone valor por defecto a propósito: una
    #: ruta adivinada es una ingesta que carga el archivo equivocado en silencio.
    ruta_archivo_venta: str | None = None

    #: Tope de filas que devuelve un reporte de clientes sin paginar.
    max_filas_reporte_clientes: int = Field(default=500, ge=10, le=5000)

    # ── API de consulta de SIESA (§5) ─────────────────────────────────────────
    #
    # Lo consume `FuenteVentaSiesa` contra `/ventas/costos-razon-social`. Su
    # encabezado explica por qué `fecha_fin` es inclusiva y por qué los dos
    # valores de `Origen` se suman; aquí solo viven los valores.

    siesa_url_base: str = "https://apiconsulta.grupo-santacruz.com"

    #: Token de la API. Se envía en la cabecera `Authorization` con el valor
    #: pelado —sin `Bearer`—. Se admite con y sin el prefijo `1-`, que es un
    #: identificador de clave y no parte del secreto: la fuente lo quita.
    #: `SecretStr` para que no aparezca en un `repr`, un log ni una traza.
    siesa_token: SecretStr = SecretStr("")

    #: Compañías a consultar, una petición por cada una. **Es obligatorio**:
    #: `id_cia` no es opcional en `/ventas/costos-razon-social` y omitirlo no
    #: devuelve «todas» —eso lo hacía el endpoint anterior—. Las de carnes son
    #: la 4, la 6 y la 7; nunca la 3 ni la 8, cuya venta agropecuaria se reporta
    #: en otra instancia. Dejar la lista vacía es un error de configuración y la
    #: fuente se niega a arrancar diciéndolo.
    siesa_companias: list[int] = Field(default_factory=lambda: [4, 6, 7])

    siesa_timeout_conexion_seg: float = Field(default=15.0, gt=0, le=120)
    #: Un mes son cientos de miles de filas en streaming. Diez minutos no es
    #: generosidad: es lo que cuesta la descarga real.
    siesa_timeout_lectura_seg: float = Field(default=600.0, gt=0, le=3600)
    siesa_reintentos: int = Field(default=3, ge=1, le=10)
    siesa_espera_reintento_seg: float = Field(default=2.0, ge=0, le=60)

    @field_validator("secret_key")
    @classmethod
    def _validar_secret_key(cls, valor: SecretStr) -> SecretStr:
        if len(valor.get_secret_value()) < 32:
            raise ValueError("SIGREP_SECRET_KEY debe tener al menos 32 caracteres.")
        return valor

    @computed_field  # type: ignore[prop-decorator]
    @property
    def hosts_efectivos(self) -> list[str]:
        """Hosts que acepta `TrustedHostMiddleware`.

        Orden de resolución: lo declarado explícitamente, luego lo derivado de
        los orígenes CORS, y como último recurso `*`. Nunca se queda con una
        lista vacía, que dejaría la API rechazando todo el tráfico.
        """
        if self.hosts_permitidos:
            return self.hosts_permitidos

        derivados = [
            origen.replace("https://", "").replace("http://", "").rstrip("/")
            for origen in self.cors_origenes
        ]
        return derivados or ["*"]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url(self) -> str:
        """Cadena de conexión SQLAlchemy según el motor configurado.

        `db_url_override` tiene prioridad y admite la URL tal cual la entregan
        los proveedores gestionados, que usan el esquema `postgres://`
        heredado; SQLAlchemy 2 no lo reconoce y se normaliza aquí.
        """
        if self.db_url_override:
            return _normalizar_url(self.db_url_override)

        if self.db_motor == "postgresql":
            return self._url_postgresql()
        return self._url_sqlserver()

    def _url_postgresql(self) -> str:
        from urllib.parse import quote_plus

        usuario = quote_plus(self.db_usuario)
        password = quote_plus(self.db_password.get_secret_value())
        # `prefer` usa TLS si el servidor lo ofrece y no falla si no. Es lo
        # correcto dentro de una red Docker privada, donde exigir `require`
        # rompería la conexión sin ganar nada: el tráfico no sale del host.
        sslmode = "require" if self.db_encrypt else "prefer"
        return (
            f"postgresql+psycopg://{usuario}:{password}"
            f"@{self.db_servidor}:{self.db_puerto}/{self.db_nombre}?sslmode={sslmode}"
        )

    def _url_sqlserver(self) -> str:
        from urllib.parse import quote_plus

        parametros = quote_plus(
            ";".join(
                [
                    f"DRIVER={{{self.db_driver}}}",
                    f"SERVER={self.db_servidor},{self.db_puerto}",
                    f"DATABASE={self.db_nombre}",
                    f"UID={self.db_usuario}",
                    f"PWD={self.db_password.get_secret_value()}",
                    f"Encrypt={'yes' if self.db_encrypt else 'no'}",
                    f"TrustServerCertificate={'yes' if self.db_trust_cert else 'no'}",
                ]
            )
        )
        return f"mssql+pyodbc:///?odbc_connect={parametros}"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def es_produccion(self) -> bool:
        return self.entorno == "produccion"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def docs_habilitados(self) -> bool:
        """La documentación interactiva se apaga en producción."""
        return not self.es_produccion


@lru_cache(maxsize=1)
def obtener_settings() -> Settings:
    """Instancia única de configuración (cacheada para no releer el entorno)."""
    return Settings()
