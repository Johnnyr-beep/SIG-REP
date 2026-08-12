# SIGREP

**Sistema Gerencial de Reportes · Grupo Santa Cruz**

Versión 1.0 — Venta contra presupuesto, por punto de venta y categoría, en pesos
y en kilos.

Reemplaza el libro de Excel de 18 MB que hoy se arma a mano cada mes por una
aplicación donde el presupuesto se parametriza una vez, la venta se ingiere
desde SIESA y el cumplimiento, la proyección y el semáforo **se calculan solos,
con las fórmulas escritas y visibles**.

> **SIGREP no reemplaza a SIESA.** SIESA es la fuente de verdad de la venta.
> SIGREP es la capa de lectura gerencial: presupuesto, comparación y análisis.

Especificación completa —modelo de negocio, indicadores y decisiones tomadas—
en [docs/ESPECIFICACION.md](docs/ESPECIFICACION.md). Contrato de la API en
[docs/API.md](docs/API.md).

---

## Puesta en marcha en cinco minutos

### Con Docker (recomendado)

```bash
cp .env.example .env

# Genere la clave de firma y péguela en .env como SIGREP_SECRET_KEY:
python -c "import secrets; print(secrets.token_urlsafe(48))"
# Defina también SIGREP_DB_PASSWORD. Son las dos únicas variables obligatorias:
# sin SIGREP_SECRET_KEY la aplicación se niega a arrancar, a propósito.

docker compose up -d --build

# Datos base (grupos, puntos de venta, categorías, zonas), calendario del
# período y usuario gerente:
docker compose exec api python -m app.infrastructure.semilla --admin --periodo 2026-08
```

La clave provisional del usuario `gerente` se imprime **una sola vez** al
ejecutar la semilla y no queda en ningún log. Cópiela en ese momento; el sistema
exigirá cambiarla en el primer acceso.

| Servicio | URL | Notas |
|---|---|---|
| Aplicación | <http://localhost:8080> | Nginx: SPA + proxy de `/api` |
| API (directa) | <http://localhost:8000/api/v1> | Publicada solo en local |
| Documentación interactiva | <http://localhost:8000/docs> | Cerrada si `SIGREP_ENTORNO=produccion` |
| Sonda de salud | <http://localhost:8080/api/v1/salud> | Toca la base; es la que usa el contenedor |
| Sonda de preparación | <http://localhost:8000/listo> | Va fuera de `/api`, así que **no** pasa por el proxy |
| PostgreSQL | `localhost:5433` | Puerto 5433 para no chocar con una instalación local |

La base de datos vive en el volumen `sigrep_datos_postgres`. `docker compose
down` conserva los datos; `docker compose down -v` los borra.

### Sin Docker (desarrollo)

```bash
# Backend
cd backend
python -m venv .venv && .venv/Scripts/activate      # Linux/macOS: source .venv/bin/activate
pip install -e ".[dev]"

export SIGREP_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
export SIGREP_DB_URL_OVERRIDE="sqlite:///./sigrep_local.db"   # no hace falta base externa

alembic upgrade head
python -m app.infrastructure.semilla --admin --periodo 2026-08
uvicorn app.main:app --reload

# Frontend, en otra terminal
cd frontend
npm install
npm run dev        # http://localhost:5174, con proxy hacia :8000
```

> El puerto del frontend es **5174** y no el 5173 habitual de Vite: así se puede
> tener GSC ONE y SIGREP levantados a la vez.

La interfaz trae además un modo de datos de ejemplo (`VITE_SIGREP_EJEMPLOS=1` en
`frontend/.env.local`) que sirve cifras ficticias sin llamar al backend, con un
distintivo permanente en la cabecera. **Nunca se construye la imagen con ese modo
activo**: unas cifras inventadas con aspecto de reporte gerencial son peores que
una pantalla vacía.

---

## Arquitectura

```text
Navegador
   │  HTTPS
   ▼
Nginx  ──────────────► React 18 + TypeScript (SPA, Vite)
   │  /api → proxy
   ▼
FastAPI ─── API REST v1 ─── OpenAPI automático
   │
   ├── Aplicación   servicios: reportes, presupuesto, calendario, ingesta
   ├── Dominio      indicadores, semáforo, calendario, puertos  ← sin dependencias externas
   └── Infraestruc. SQLAlchemy 2.0 · Alembic
   │
   ▼
PostgreSQL (SQL Server soportado por tipos genéricos)
   ▲
   │  puerto FuenteVenta
SIESA (fuente de verdad de la venta)
```

Dos procesos en producción, no tres: **SIGREP no tiene planificador**. Los
indicadores se calculan al consultarlos, no por tareas periódicas, así que
escalar la API es seguro y no hay estado en memoria que se duplique.

### Por qué esta estructura

| Decisión | Motivo |
|---|---|
| Mismo stack que GSC ONE | El equipo ya lo domina y hay código probado que se porta en lugar de reinventarse: `core/config.py`, `core/db.py`, `core/security.py`, `core/errors.py`, `core/deps.py`, `core/logging.py`. |
| Dominio sin dependencias de infraestructura | Las fórmulas de cumplimiento, proyección y semáforo se prueban sin base de datos ni servidor. |
| Importes como `Decimal`, nunca `float` | El redondeo binario es inaceptable en un reporte contra presupuesto. |
| Días hábiles como `Decimal` | El negocio maneja medias jornadas: 27.5 y 28.5 días hábiles son valores reales del Excel vigente. |
| El mapeo de categorías es una tabla, no un `dict` | SIESA añade categorías y el negocio las reclasifica sin esperar un despliegue. |
| La venta se guarda al grano de transacción | Guardar solo el total impediría el análisis por cliente, vendedor y categoría que el negocio ya hace. |
| Frontend y API en el mismo origen | Sin CORS ni cookies de terceros: Nginx publica `/api` sobre el mismo dominio. |

---

## Pruebas

```bash
cd backend
pytest                                  # 61 pruebas
pytest --cov=app --cov-report=term      # cobertura
ruff format --check app tests
ruff check app tests
mypy app                                # configurado en modo strict
alembic upgrade head
alembic check                           # detecta deriva entre modelos y migraciones

cd ../frontend
npm run typecheck
npm run build
```

**Estado:** 61 pruebas en verde. Las fórmulas del dominio —`indicadores`,
`semaforo`, `calendario`, `puertos`— entre **99 % y 100 %** de cobertura, que es
donde importa: son los números que la gerencia va a leer.

La cobertura global se mueve mientras se añaden módulos, así que no se fija aquí
un porcentaje que envejece mal: el CI publica `coverage.xml` como artefacto en
cada ejecución.

Las pruebas corren sobre SQLite en memoria (`SIGREP_DB_URL_OVERRIDE=sqlite://`)
y crean el esquema por prueba, así que no necesitan ninguna base levantada.

Estos mismos comandos son los que ejecuta la integración continua
(`.github/workflows/ci.yml`) en cada push y en cada pull request, y ninguno está
marcado como tolerante a fallos: si algo se pone rojo, no se publica imagen ni se
despliega.

---

## Despliegue

Producción corre en **Dokploy** (Docker Swarm) con `docker-compose.dokploy.yml`,
sobre las imágenes que el CI publica en GHCR después de que pasen las pruebas.
El servidor de producción nunca compila.

```text
push a main
   │
   ├── CI: ruff format · ruff check · mypy · 61 pruebas · alembic sobre base efímera
   │      typecheck · build          (si algo falla, aquí se detiene)
   │
   ├── CI: publica sigrep-api y sigrep-web en GHCR
   │
   └── CI: webhook a Dokploy → docker stack deploy
```

Procedimiento completo, variables requeridas, migraciones y respaldos en
[docs/DESPLIEGUE.md](docs/DESPLIEGUE.md).

> ⚠️ **El dominio público de SIGREP está pendiente de definir.** Todo lo que
> depende de él está parametrizado en la variable `SIGREP_DOMINIO` y no hay
> ningún dominio escrito a fuego en el código. Ver
> [docs/DESPLIEGUE.md §3](docs/DESPLIEGUE.md).

---

## Configuración

Toda la configuración entra por variables de entorno con el prefijo `SIGREP_`
(12-factor). [`.env.example`](.env.example) las documenta una por una; las
definitivas están en `backend/app/core/config.py`.

Obligatorias: `SIGREP_SECRET_KEY` (mínimo 32 caracteres) y `SIGREP_DB_PASSWORD`.

Las reglas de negocio que la especificación deja **pendientes de confirmar con
el usuario** son variables, no constantes, para que Gerencia las ajuste sin
desplegar:

| Variable | Por defecto | Qué controla |
|---|---|---|
| `SIGREP_FACTOR_SEMAFORO_AMARILLO` | `0.90` | Umbral del semáforo: amarillo llega hasta este factor del ideal, debajo es rojo |
| `SIGREP_DIAS_HABILES_POR_DEFECTO` | `28` | Días hábiles sembrados para las zonas cuyo calendario aún no confirma el negocio |
| `SIGREP_FUENTE_VENTA` | `excel` | Implementación activa del puerto `FuenteVenta`: `excel` o `siesa` |
| `SIGREP_MAX_FILAS_REPORTE_CLIENTES` | `500` | Tope de filas de un reporte de clientes sin paginar |

---

## Seguridad

| Control | Implementación |
|---|---|
| Contraseñas | Argon2id, con rehash automático |
| Sesión | JWT de acceso corto + refresh separado |
| Fuerza bruta | Bloqueo de cuenta tras N intentos; se bloquea la cuenta, no la IP |
| Autorización | RBAC por endpoint; el rol se relee de la base en cada petición |
| Inyección SQL | SQLAlchemy con parámetros ligados; ninguna consulta se concatena |
| Validación de entrada | Pydantic v2 con límites de longitud y rango |
| Cabeceras | HSTS en producción, CSP estricta sin CDN, `X-Frame-Options`, `nosniff` |
| Host header injection | `TrustedHostMiddleware` en producción (`SIGREP_HOSTS_PERMITIDOS`) |
| Secretos | Solo por variables de entorno; la aplicación **no arranca** sin `SIGREP_SECRET_KEY` |
| Contenedores | Usuario no privilegiado (`sigrep`, uid 10001, y `nginx`), imagen final sin compiladores |

Ningún secreto vive en un archivo versionado. `.env` está en `.gitignore` y
excluido del contexto de construcción por los dos `.dockerignore`.

---

## Estructura

```text
SIGREP/
├── backend/
│   ├── app/
│   │   ├── core/            configuración, base de datos, seguridad, errores, logging
│   │   ├── domain/          indicadores, semáforo, calendario, puertos  ← sin infraestructura
│   │   ├── infrastructure/  modelos ORM, semilla
│   │   ├── application/     servicios (casos de uso)
│   │   ├── api/v1/          routers REST
│   │   └── schemas/         contratos Pydantic
│   ├── alembic/versions/    migraciones
│   ├── docker/arranque.sh   migra y arranca Uvicorn
│   ├── tests/               61 pruebas
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── api/             cliente HTTP tipado y hooks de datos
│   │   ├── auth/            contexto de sesión
│   │   ├── componentes/     piezas compartidas
│   │   ├── paginas/         pantallas
│   │   └── estilos.css      sistema de diseño
│   ├── docker/              nginx.conf y cabeceras de seguridad
│   └── Dockerfile
├── docs/
│   ├── ESPECIFICACION.md    fuente de verdad del negocio
│   ├── API.md               contrato de la API
│   └── DESPLIEGUE.md        procedimiento de despliegue
├── docker-compose.yml           local
├── docker-compose.dokploy.yml   producción (Swarm)
├── .env.example
└── .github/workflows/ci.yml
```

---

## Pendientes con el usuario

Están marcados en la especificación (§8) y el sistema funciona con un supuesto
declarado mientras se resuelven:

1. **Días hábiles** de MALAMBO, CONCORDE, SANFELIPE, OLAYA, LA93, ALAMEDA y
   ALAMEDA2. *Supuesto: 28, parametrizable en pantalla.*
2. **Regla de comisión** (§4.6). *Campo modelado, cálculo pendiente.*
3. **Umbrales del semáforo** (§4.1). *Supuesto: 90 % del ideal.*
4. **Historia 2025** para el indicador de crecimiento. Sin ella el indicador se
   muestra vacío, nunca en cero.
5. **API de SIESA**: pendiente de entrega. La ingesta está diseñada contra un
   puerto, así que cambiar de Excel a SIESA será una variable de entorno.
6. **Dominio público** para el despliegue.

---

Departamento de Tecnología · Grupo Santa Cruz
