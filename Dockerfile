# Build completo para Dokploy Application: un contenedor, una entrada HTTP.

FROM node:22-alpine AS frontend-build
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/index.html frontend/tsconfig.json frontend/vite.config.ts ./
COPY frontend/src ./src
COPY frontend/public ./public
RUN npm run build

FROM python:3.12-slim-bookworm AS backend-dependencies
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /build
COPY backend/pyproject.toml ./
COPY backend/app ./app
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir .

FROM python:3.12-slim-bookworm AS produccion
ARG SIGREP_VERSION=0.0.0+direct
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    SIGREP_ENTORNO=produccion \
    SIGREP_API_HOST=127.0.0.1 \
    SIGREP_VERSION=${SIGREP_VERSION}

RUN apt-get update \
    && apt-get install --no-install-recommends -y ca-certificates curl nginx supervisor \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 sigrep \
    && useradd --system --uid 10001 --gid sigrep --create-home \
        --shell /usr/sbin/nologin sigrep \
    && mkdir -p /app /tmp/nginx/client_temp /tmp/nginx/proxy_temp /tmp/nginx/fastcgi_temp \
        /tmp/nginx/uwsgi_temp /tmp/nginx/scgi_temp /var/cache/nginx /var/lib/nginx \
        /var/log/nginx /usr/share/nginx/html \
    && chown -R sigrep:sigrep /app /tmp/nginx /var/cache/nginx /var/lib/nginx \
        /var/log/nginx /usr/share/nginx/html

WORKDIR /app
COPY --from=backend-dependencies /opt/venv /opt/venv
COPY --chown=sigrep:sigrep backend/app ./app
COPY --chown=sigrep:sigrep backend/alembic ./alembic
COPY --chown=sigrep:sigrep backend/alembic.ini ./alembic.ini
COPY --chown=sigrep:sigrep backend/docker/arranque.sh /usr/local/bin/arranque.sh
COPY --from=frontend-build --chown=sigrep:sigrep /build/frontend/dist /usr/share/nginx/html
RUN printf '%s\n' "$SIGREP_VERSION" > /usr/share/nginx/html/version.txt
COPY frontend/docker/cabeceras-seguridad.conf /etc/nginx/conf.d/cabeceras-seguridad.inc
COPY docker/nginx-unificado.conf /etc/nginx/nginx.conf
COPY docker/supervisord-unificado.conf /etc/supervisor/supervisord.conf

RUN chmod 0555 /usr/local/bin/arranque.sh \
    && nginx -t \
    && rm -f /tmp/nginx/nginx.pid \
    && chown -R sigrep:sigrep /tmp/nginx /var/cache/nginx /var/lib/nginx /var/log/nginx

USER sigrep
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=70s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8080/api/v1/salud >/dev/null \
        && curl -fsS http://127.0.0.1:8080/ >/dev/null || exit 1

CMD ["/usr/bin/supervisord", "-n", "-c", "/etc/supervisor/supervisord.conf"]