#!/usr/bin/env bash
#
# Corre en local exactamente lo que corre la integracion continua.
#
#   scripts/pruebas-como-ci.sh              # backend y frontend
#   scripts/pruebas-como-ci.sh --backend    # solo backend
#   scripts/pruebas-como-ci.sh --frontend   # solo frontend
#
# Por que existe: el CI corria las pruebas sobre SQLite en memoria y en local se
# corrian sobre un archivo `.db` con esquema y datos de una corrida anterior. Una
# prueba dejaba el registro de motores vacio; en local pasaba y en el CI tumbaba
# 31 pruebas. Cuatro horas de las de hoy salieron de esa diferencia.
#
# En Windows: use Git Bash, o `scripts\pruebas-como-ci.ps1` desde PowerShell.

set -u

raiz="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$raiz" || exit 1

hacer_backend=1
hacer_frontend=1
case "${1:-}" in
    --backend)  hacer_frontend=0 ;;
    --frontend) hacer_backend=0 ;;
    "")         ;;
    *) echo "Uso: $0 [--backend | --frontend]" >&2; exit 2 ;;
esac

# ── Paridad de entorno ────────────────────────────────────────────────────────
#
# Se borra TODA variable `SIGREP_*` heredada de la terminal antes de cargar las
# del CI. `conftest.py` usa `os.environ.setdefault`, asi que una variable que ya
# venga puesta gana sobre el valor de las pruebas: un `SIGREP_DB_URL_OVERRIDE`
# apuntando a un archivo, o un `SIGREP_FUENTE_VENTA=siesa` de una prueba manual,
# cambian en silencio lo que se esta verificando.
while IFS='=' read -r nombre _; do
    case "$nombre" in SIGREP_*) unset "$nombre" ;; esac
done < <(env)

set -a
# shellcheck disable=SC1091
. "$raiz/scripts/entorno-pruebas.env"
set +a

if [ -f "$raiz/backend/.env" ]; then
    echo "AVISO: existe backend/.env. Pydantic lo lee, pero las variables de"
    echo "       entorno tienen prioridad, asi que no altera esta corrida."
    echo
fi

# El entorno virtual del backend, si esta y no hay ninguno activo. El CI instala
# las dependencias en el interprete del runner; en local casi siempre viven aqui.
if [ -z "${VIRTUAL_ENV:-}" ]; then
    for activador in "$raiz/backend/.venv/bin/activate" "$raiz/backend/.venv/Scripts/activate"; do
        if [ -f "$activador" ]; then
            # shellcheck disable=SC1090
            . "$activador"
            echo "Entorno virtual activado: $VIRTUAL_ENV"
            echo
            break
        fi
    done
fi

fallos=0
resumen=""

# Corre un comando, informa el resultado y sigue. El CI se detiene en el primer
# paso rojo; aqui interesa la lista completa para no descubrir los errores de
# uno en uno. El veredicto final es el mismo.
paso() {
    etiqueta="$1"
    shift
    printf '\n\033[1m── %s\033[0m\n' "$etiqueta"
    if "$@"; then
        resumen="${resumen}  OK    ${etiqueta}\n"
    else
        resumen="${resumen}  FALLA ${etiqueta}\n"
        fallos=$((fallos + 1))
    fi
}

if [ "$hacer_backend" -eq 1 ]; then
    cd "$raiz/backend" || exit 1
    paso "Formato (ruff format --check)" ruff format --check app tests
    paso "Lint (ruff check)"             ruff check app tests
    paso "Tipos (mypy)"                  mypy app
    paso "Pruebas"                       pytest --cov=app --cov-report=term
fi

if [ "$hacer_frontend" -eq 1 ]; then
    cd "$raiz/frontend" || exit 1
    paso "Frontend · tipos"      npm run typecheck
    paso "Frontend · compilar"   npm run build
fi

# `alembic upgrade head` y `alembic check` no estan aqui a proposito: el CI los
# corre contra un PostgreSQL efimero levantado por el propio runner. Reproducirlo
# en local es `docker compose up -d postgres` y apuntar SIGREP_DB_URL_OVERRIDE a
# esa base; verificarlos contra SQLite no probaria lo mismo.

printf '\n\033[1m── Resumen\033[0m\n'
printf "%b" "$resumen"

if [ "$fallos" -gt 0 ]; then
    printf '\n%s paso(s) en rojo. Esto mismo pondria el CI en rojo.\n' "$fallos"
    exit 1
fi

printf '\nTodo en verde con el entorno del CI.\n'
