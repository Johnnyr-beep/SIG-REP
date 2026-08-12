# syntax=docker/dockerfile:1.7
#
# Imagen de la API de SIGREP.
#
# Por defecto se compila para PostgreSQL, que no requiere ninguna dependencia
# del sistema: `psycopg[binary]` trae la libpq compilada. El resultado es una
# imagen pequeña y un build que no depende de repositorios externos.
#
# Para desplegar sobre SQL Server: descomente el bloque marcado más abajo y
# cambie `pip install .` por `pip install ".[sqlserver]"`.

# ── Etapa de dependencias ─────────────────────────────────────────────────────
FROM python:3.12-slim-bookworm AS dependencias

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build
COPY pyproject.toml ./
COPY app ./app

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir .

# ── SQL Server (opcional) ─────────────────────────────────────────────────────
# Descomente para habilitar el motor mssql:
#
# RUN apt-get update && apt-get install --no-install-recommends -y \
#         curl gnupg ca-certificates \
#     && curl -fsSL https://packages.microsoft.com/keys/microsoft.asc \
#         | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg \
#     && echo "deb [arch=amd64,arm64 signed-by=/usr/share/keyrings/microsoft-prod.gpg] \
#         https://packages.microsoft.com/debian/12/prod bookworm main" \
#         > /etc/apt/sources.list.d/mssql-release.list \
#     && apt-get update \
#     && ACCEPT_EULA=Y apt-get install --no-install-recommends -y msodbcsql18 unixodbc \
#     && rm -rf /var/lib/apt/lists/* \
#     && pip install --no-cache-dir ".[sqlserver]"

# ── Imagen final ──────────────────────────────────────────────────────────────
#
# Se parte otra vez de la imagen base y solo se copia el entorno virtual ya
# resuelto: pip, setuptools y las cabeceras de compilación se quedan en la etapa
# anterior y nunca llegan a producción.
FROM python:3.12-slim-bookworm AS produccion

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    SIGREP_ENTORNO=produccion

# `curl` se usa en la sonda de salud; nada más se añade al sistema base.
RUN apt-get update \
    && apt-get install --no-install-recommends -y curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=dependencias /opt/venv /opt/venv

# Principio de mínimo privilegio: el proceso nunca corre como root.
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin sigrep
WORKDIR /app

COPY --chown=sigrep:sigrep app ./app
COPY --chown=sigrep:sigrep alembic ./alembic
COPY --chown=sigrep:sigrep alembic.ini ./
COPY --chown=sigrep:sigrep docker/arranque.sh /usr/local/bin/arranque.sh
RUN chmod +x /usr/local/bin/arranque.sh

USER sigrep
EXPOSE 8000

# Sonda de **vida**, no de preparación. `/api/v1/salud` responde 200 con
# `estado: "degradado"` cuando la base no contesta, y eso es deliberado: si el
# contenedor se marcara enfermo por una caída momentánea de PostgreSQL, el
# orquestador reiniciaría todas las réplicas en cadena justo cuando la base
# menos lo necesita. Lo que esta sonda comprueba es que Uvicorn atiende.
HEALTHCHECK --interval=30s --timeout=5s --start-period=25s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/api/v1/salud || exit 1

ENTRYPOINT ["/usr/local/bin/arranque.sh"]
