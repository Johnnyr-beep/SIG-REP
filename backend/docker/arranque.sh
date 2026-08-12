#!/bin/sh
# Arranque del contenedor de la API de SIGREP.
#
# Aplicar las migraciones aquí simplifica plataformas como Dokploy, donde no hay
# orquestador que garantice el orden de arranque. Alembic es idempotente: si el
# esquema ya está al día, no hace nada.

set -eu

# La base puede tardar en aceptar conexiones cuando todo el stack arranca a la
# vez. Se reintenta con espera en lugar de morir en el primer fallo, que dejaría
# el contenedor en bucle de reinicio por una carrera de segundos.
INTENTOS="${SIGREP_INTENTOS_MIGRACION:-12}"
ESPERA=5
n=1

while [ "$n" -le "$INTENTOS" ]; do
    echo "[SIGREP] Aplicando migraciones (intento ${n}/${INTENTOS})…"
    if alembic upgrade head; then
        echo "[SIGREP] Esquema al día."
        break
    fi

    if [ "$n" -eq "$INTENTOS" ]; then
        echo "[SIGREP] ERROR: no se pudo migrar la base tras ${INTENTOS} intentos." >&2
        echo "[SIGREP] Verifique SIGREP_DB_* y que la base acepte conexiones." >&2
        exit 1
    fi

    echo "[SIGREP] La base no responde todavía; reintentando en ${ESPERA}s…"
    sleep "$ESPERA"
    n=$((n + 1))
done

# Un worker por núcleo más uno es el punto de partida para carga mixta de E/S y
# CPU. SIGREP_WORKERS permite ajustarlo sin reconstruir la imagen.
#
# SIGREP no tiene tareas periódicas ni proceso planificador: los reportes se
# calculan al consultarlos. Escalar workers o réplicas es seguro; no hay estado
# en memoria que se duplique.
WORKERS="${SIGREP_WORKERS:-2}"

echo "[SIGREP] Iniciando API con ${WORKERS} worker(s)…"
exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers "${WORKERS}" \
    --proxy-headers \
    --forwarded-allow-ips='*' \
    --no-server-header \
    --timeout-keep-alive 30
