# SIGREP — Manual de despliegue

Destino: **Dokploy** (Docker Swarm), el mismo servidor donde ya corre GSC ONE.
Base de datos: **PostgreSQL**, servicio administrado por la plataforma.

Este documento cubre el despliegue de producción. Para levantar el sistema en
una máquina de desarrollo, el [README](../README.md) es más corto y suficiente.

---

## 0. Estado y decisiones pendientes

> ⚠️ **El dominio público de SIGREP está por definir.**
>
> Nada en el repositorio lo da por sentado: el enrutamiento se resuelve por la
> variable `SIGREP_DOMINIO`, que se fija en el panel de Dokploy. El valor por
> defecto del compose —`sigrep.grupo-santacruz.com`— es un **marcador de
> posición** coherente con el de GSC ONE (`gsc.grupo-santacruz.com`), no un
> dominio confirmado ni registrado.
>
> Cuando el usuario lo defina hay que fijar **tres** variables coherentes entre
> sí, y darlo de alta además en la pestaña *Domains* del servicio:
>
> | Variable | Ejemplo |
> |---|---|
> | `SIGREP_DOMINIO` | `sigrep.grupo-santacruz.com` (sin esquema ni barra) |
> | `SIGREP_CORS_ORIGENES` | `https://sigrep.grupo-santacruz.com` (con esquema, sin barra final) |
> | `SIGREP_HOSTS_PERMITIDOS` | `sigrep.grupo-santacruz.com` (si se omite, hereda de `SIGREP_DOMINIO`) |

---

## 1. Topología

```mermaid
graph TB
    U[Usuarios<br/>Grupo Santa Cruz] -->|HTTPS| T[Traefik<br/>TLS · Let's Encrypt]
    T --> W[Servicio web<br/>Nginx + SPA · puerto 8080]
    W -->|/api → proxy| A[Servicio api<br/>FastAPI · puerto 8000]
    A --> PG[(PostgreSQL<br/>servicio de Dokploy)]

    subgraph red interna
        W
        A
    end
```

Dos servicios, no tres. **SIGREP no tiene planificador**: los indicadores se
calculan al consultarlos, no por tareas periódicas. Es la diferencia principal
con GSC ONE y la razón por la que aquí se puede escalar `api` sin precauciones.

| Servicio | Imagen | Redes | Expuesto |
|---|---|---|---|
| `api` | `sigrep-api` | `interna` | No — solo alcanzable por `web` |
| `web` | `sigrep-web` | `interna` + `dokploy-network` | Sí, por Traefik |

---

## 2. Requisitos de una sola vez

### 2.1 El repositorio

Dokploy despliega desde Git, no desde su disco local. El repositorio debe ser
**privado** y `.env` no puede estar dentro:

```bash
git status --short | grep -i "\.env$"     # no debe devolver nada
```

`.gitignore` ya excluye `.env`, `*.db`, `.venv/`, `node_modules/` y los libros
de Excel con datos comerciales.

### 2.2 Imágenes públicas en GHCR

`docker stack deploy` no compila: descarga imágenes ya publicadas. Las publica
el CI en cada push a `main`, después de que pasen las pruebas, como
`ghcr.io/<propietario>/sigrep-api` y `sigrep-web`.

GitHub las crea **privadas** y así el servidor no puede descargarlas. Póngalas
públicas una vez: GitHub → **Packages** → cada paquete → *Package settings* →
*Change visibility* → **Public**.

### 2.3 El tipo de servicio debe ser «Stack»

Es el ajuste que más cuesta descubrir y el que hace que todo lo demás funcione.

El Traefik de este servidor corre con `--providers.docker.swarmMode=true`. En
ese modo **solo ve servicios de Docker Swarm**: los contenedores que crea
`docker compose` le son invisibles. El síntoma no se parece a un fallo de la
aplicación:

> El dominio responde **404 page not found** en texto plano mientras los
> contenedores están sanos, Nginx sirve la interfaz y la sonda devuelve 200.

Un **502** habría significado «tengo la ruta y no alcanzo el backend». El
**404** significa «no tengo ruta»: Traefik nunca registró el router porque no
vio el servicio. Si algún día reaparece ese 404, esta es la primera causa a
descartar.

Dokploy fija el tipo **al crear el servicio** y no siempre deja cambiarlo
después. Compruébelo en la cabecera del log de despliegue: debe decir
`Compose Type: stack` y el comando debe ser `docker stack deploy`.

### 2.4 La base de datos

Cree el servicio PostgreSQL en Dokploy **antes** que la aplicación y tome de su
pestaña *General* la **Internal Connection URL**:

```
postgresql://usuario:clave@nombre-servicio:5432/basededatos
```

SIGREP la acepta tal cual —incluso con el esquema `postgres://` heredado, que
SQLAlchemy 2 ya no reconoce— porque la normaliza al driver instalado.

Si crea la base desde cero, hágalo con intercalación española sin distinción de
mayúsculas ni acentos. Sin esto, buscar «visceras» no encontrará «VISCERAS» ni
«vísceras», y los usuarios reportarán que «el buscador no funciona»:

```sql
CREATE COLLATION IF NOT EXISTS es_insensible (
    provider = icu,
    locale = 'es-CO-u-ks-level1',
    deterministic = false
);
```

---

## 3. Variables de entorno

Genere la clave de firma **en su máquina** y péguela solo en el panel de
Dokploy. Nunca en un archivo, un chat, un correo ni una captura:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Bloque completo para el campo *Environment* del servicio:

```env
# ── Obligatorias ─────────────────────────────────────────────────────────────
SIGREP_SECRET_KEY=<la-clave-de-48-caracteres-que-acaba-de-generar>
SIGREP_DB_URL_OVERRIDE=postgresql://usuario:clave@host-interno:5432/sigrep

# ── Dominio — PENDIENTE DE DEFINIR, los tres deben coincidir ─────────────────
SIGREP_DOMINIO=sigrep.grupo-santacruz.com
SIGREP_CORS_ORIGENES=https://sigrep.grupo-santacruz.com
SIGREP_HOSTS_PERMITIDOS=sigrep.grupo-santacruz.com

# ── Reglas de negocio — CONFIRMAR CON GERENCIA antes de salir a producción ───
SIGREP_FACTOR_SEMAFORO_AMARILLO=0.90
SIGREP_DIAS_HABILES_POR_DEFECTO=28
SIGREP_FUENTE_VENTA=excel
SIGREP_MAX_FILAS_REPORTE_CLIENTES=500

# ── Sesión ───────────────────────────────────────────────────────────────────
SIGREP_ACCESS_TOKEN_MINUTOS=30
SIGREP_MAX_INTENTOS_LOGIN=5

# ── Escala ───────────────────────────────────────────────────────────────────
SIGREP_WORKERS=2
SIGREP_REPLICAS_API=1
SIGREP_REPLICAS_WEB=1
```

`SIGREP_ENTORNO=produccion` ya viene fijado en el compose: cierra `/docs`,
`/redoc` y `/openapi.json`, oculta las trazas de error, activa HSTS y enciende
la validación de cabecera `Host`.

### Variables obligatorias

| Variable | Qué pasa si falta |
|---|---|
| `SIGREP_SECRET_KEY` | La aplicación **no arranca**. Mínimo 32 caracteres, validado al iniciar |
| `SIGREP_DB_URL_OVERRIDE` *(o el juego `SIGREP_DB_*`)* | El arranque reintenta migrar 12 veces y termina abortando |

### Variables ajustables sin desplegar

Son decisiones de Gerencia, no de Tecnología, y por eso son variables:
`SIGREP_FACTOR_SEMAFORO_AMARILLO`, `SIGREP_DIAS_HABILES_POR_DEFECTO`,
`SIGREP_FUENTE_VENTA`, `SIGREP_MAX_FILAS_REPORTE_CLIENTES`,
`SIGREP_ACCESS_TOKEN_MINUTOS`, `SIGREP_MAX_INTENTOS_LOGIN`,
`SIGREP_MINUTOS_BLOQUEO_CUENTA`.

El inventario completo, comentado uno a uno, está en
[`.env.example`](../.env.example).

> **`SIGREP_CORS_ORIGENES` nunca debe ser `*`.** Ponga el origen exacto, con
> `https://` y sin barra final. Si todavía no hay dominio y se usa la URL
> temporal que asigna Dokploy, ponga esa.

---

## 4. Crear el servicio

1. Proyecto en Dokploy → **Create Service** → **Compose**.
2. Nombre: `sigrep-app`.
3. **Compose Type**: **`Stack`** ← el paso que no se puede omitir (§2.3).
4. **Provider**: Git → este repositorio → rama `main`.
5. **Compose Path**: `docker-compose.dokploy.yml`
6. **Environment**: el bloque de §3.
7. **Domains**: el dominio apuntando al servicio **`web`**, puerto **`8080`**,
   con *HTTPS* y *Let's Encrypt* activados.
8. **Deploy**.

El despliegue es rápido: solo descarga las dos imágenes que el CI ya construyó.
Compilar es trabajo del CI, no del servidor de producción, y así lo que se
despliega es exactamente lo que pasó las 61 pruebas.

---

## 5. Migraciones

**Se aplican solas al arrancar el contenedor.** `backend/docker/arranque.sh`
ejecuta `alembic upgrade head` antes de levantar Uvicorn, y Alembic es
idempotente: si el esquema ya está al día, no hace nada.

La base puede tardar en aceptar conexiones cuando todo arranca a la vez, así que
el script reintenta **12 veces con 5 segundos de espera**
(`SIGREP_INTENTOS_MIGRACION`) en lugar de morir al primer fallo, que dejaría el
contenedor en bucle de reinicio por una carrera de segundos.

Con varias réplicas arrancando a la vez, la primera toma el bloqueo de la tabla
de versión de Alembic y las demás esperan y encuentran el esquema ya migrado.

### Orden correcto de un despliegue que incluye migración

1. **Revisar el SQL.** `alembic upgrade head --sql > migracion.sql` lo genera
   sin ejecutarlo, para aprobarlo antes.
2. **Respaldo** (§7). Antes de una migración estructural, siempre.
3. **Desplegar.** El arranque migra de forma idempotente.
4. **Verificar** `/api/v1/salud` (§6).

### Reversión

```bash
# Volver a una etiqueta anterior: el CI publica cada imagen también con el SHA
SIGREP_VERSION=<sha-del-commit-anterior>
```

> **Volver a una imagen anterior NO revierte el esquema.** Diseñe siempre
> migraciones compatibles hacia atrás: añada columnas como nulables y elimine en
> un despliegue posterior, nunca en el mismo. Si hay que revertir el esquema,
> `alembic downgrade -1` — y hágalo con respaldo reciente.

El CI ejecuta `alembic upgrade head` sobre una **base PostgreSQL efímera** y
después `alembic check` en cada push. Eso detecta el olvido clásico —cambiar un
modelo y no generar la migración— antes de que llegue a producción, donde se
manifestaría como una columna que no existe.

---

## 6. Inicialización y verificación

Con el despliegue en verde, abra la terminal del contenedor `api` desde el panel
y siembre los datos base:

```bash
python -m app.infrastructure.semilla --admin --periodo 2026-08
```

Esto crea los 4 grupos, los 16 puntos de venta con su C.O. de SIESA, las 8
categorías con su tabla de mapeo, las zonas con su calendario, y el usuario
`gerente`.

**Copie la clave provisional en el momento.** Se imprime **una sola vez**, no
queda en ningún log, y el sistema exigirá cambiarla en el primer acceso.

### Comprobaciones, en este orden

| Comprobación | Resultado esperado |
|---|---|
| `https://<dominio>/api/v1/salud` | `{"estado":"operativo","base_datos":"disponible",…}` |
| Abrir el dominio en el navegador | Pantalla de acceso de SIGREP |
| Entrar como `gerente` | Exige cambiar la clave provisional |
| `https://<dominio>/docs` | **404** — correcto, se cierra en producción |

> **Sobre las sondas.** `/api/v1/salud` toca la base y es la que se publica.
> `/listo` vive **fuera** del prefijo `/api`, así que no pasa por el proxy de
> Nginx: pedirlo por el dominio devuelve la SPA, no el JSON. Es útil solo contra
> la API directamente (`api:8000/listo` dentro de la red).
>
> El `HEALTHCHECK` del contenedor de la API apunta a `/api/v1/salud` pero es una
> sonda de **vida**, no de preparación: ese endpoint responde 200 con
> `estado: "degradado"` cuando la base no contesta, y es deliberado. Si el
> contenedor se marcara enfermo por una caída momentánea de PostgreSQL, Swarm
> reiniciaría todas las réplicas en cadena justo cuando la base menos lo
> necesita.

### Configuración funcional mínima

Sin esto el sistema no produce ningún reporte útil:

1. **Calendario de días hábiles** por zona y período. Los de MALAMBO, CONCORDE,
   SANFELIPE, OLAYA, LA93, ALAMEDA y ALAMEDA2 están **sembrados con el supuesto
   de 28** y deben confirmarse con el negocio.
2. **Presupuesto** del período por punto de venta y categoría, capturado o
   cargado masivamente.
3. **Ingesta de venta** del período.
4. **Usuarios** con sus roles: `GERENTE`, `ANALISTA`, `CONSULTA`.

---

## 7. Respaldo y recuperación

| Elemento | Mecanismo | Frecuencia | Retención |
|---|---|---|---|
| PostgreSQL | Respaldo de Dokploy a destino S3 | Diaria | 30 días |
| PostgreSQL (antes de migrar) | `pg_dump` manual | Por despliegue estructural | 4 semanas |
| Imágenes | Etiqueta con el SHA en GHCR | Por commit | 6 versiones |

**Actívelo antes de cargar datos reales**, no después.

### Respaldo manual

```bash
# Desde el servidor, contra el servicio de base de Dokploy
docker exec <contenedor-postgres> \
  pg_dump -U <usuario> -d <basededatos> --format=custom --no-owner \
  > sigrep-$(date +%Y%m%d-%H%M).dump
```

### Restauración

```bash
docker exec -i <contenedor-postgres> \
  pg_restore -U <usuario> -d <basededatos> --clean --if-exists --no-owner \
  < sigrep-20260812-1400.dump
```

### En desarrollo local

La base vive en el volumen `sigrep_datos_postgres`:

```bash
docker compose exec postgres pg_dump -U sigrep_app -d sigrep --format=custom \
  > respaldo-local.dump
```

> **Pruebe la restauración al menos una vez por semestre.** Un respaldo que
> nunca se ha restaurado es una hipótesis, no un respaldo.

---

## 8. Despliegue continuo

El flujo `.github/workflows/ci.yml` llama al webhook de Dokploy **solo si todo
lo anterior pasó**: formato, lint, tipos en modo estricto, las 61 pruebas,
migraciones sobre base efímera sin deriva, `typecheck`, `build` y la
construcción de ambas imágenes.

Para activarlo, en GitHub → **Settings → Secrets and variables → Actions**:

| Secreto | Valor |
|---|---|
| `DOKPLOY_WEBHOOK_URL` | La URL de despliegue del servicio Compose |

**Quien tenga esa URL puede desplegar**: es una credencial, trátela como tal. Si
circuló por un chat, un correo o una captura, regenérela desde el panel.

Recomendado además: **Settings → Environments → New environment** con el nombre
`produccion` y *Required reviewers* activado. Así cada despliegue a producción
exige una aprobación humana explícita.

### Disparo manual

El endpoint espera el cuerpo de un evento *push* y compara la rama con la
configurada en el servicio; un `POST` vacío se rechaza con
`{"message":"Branch Not Match"}`:

```bash
curl -X POST "http://<host-dokploy>:3000/api/deploy/compose/<identificador>" \
     -H "Content-Type: application/json" \
     -d '{"ref":"refs/heads/main"}'
```

---

## 9. Problemas frecuentes

| Síntoma | Causa probable | Solución |
|---|---|---|
| El dominio responde **404** en texto plano con todo sano | El servicio no es de tipo *Stack*: Traefik en modo Swarm no ve contenedores de `docker compose` | Recrear el servicio con **Compose Type = Stack** (§2.3) |
| **502** desde Traefik | La API todavía está migrando | Espere: el arranque reintenta 12 veces con 5 s |
| Toda petición responde **400 «Invalid host header»** | El `Host` público no coincide con el origen CORS | Declare `SIGREP_HOSTS_PERMITIDOS` con el dominio real |
| El contenedor reinicia en bucle con «no se pudo migrar la base» | URL de conexión incorrecta o base inaccesible | Revise `SIGREP_DB_URL_OVERRIDE`: el host debe ser el **interno** de Dokploy, nunca `localhost` |
| `sslmode value "require" invalid` o fallo de TLS | La base interna no ofrece TLS | Use la URL sin `?sslmode=require`, o `SIGREP_DB_ENCRYPT=false` |
| «SIGREP_SECRET_KEY debe tener al menos 32 caracteres» | Variable ausente o corta | Genere una nueva de 48 caracteres |
| El frontend carga pero toda petición falla con CORS | `SIGREP_CORS_ORIGENES` no coincide con el dominio | Origen exacto, con `https://` y sin barra final |
| PostgreSQL aborta con «there appears to be PostgreSQL data in `/var/lib/postgresql/data` (unused mount/volume)» | Desde la imagen 18 el volumen se monta en `/var/lib/postgresql`, no en `.../data` | Ya corregido en `docker-compose.yml`; si reaparece, revise el punto de montaje |
| Una ruta sirve la SPA sin CSP ni `X-Frame-Options` | `add_header` de nginx **no se hereda** en un `location` que declare cabeceras propias | Incluya `cabeceras-seguridad.inc` también en ese `location` |

Para ver qué pasó: pestaña **Logs** del servicio. Los registros son JSON
estructurado con `request_id`, así que se puede seguir una petición completa
filtrando por ese campo.

---

## 10. Lista de verificación previa a producción

**Dominio y red**

- [ ] Dominio **definido por el usuario** y dado de alta en *Domains*
- [ ] `SIGREP_DOMINIO`, `SIGREP_CORS_ORIGENES` y `SIGREP_HOSTS_PERMITIDOS` coherentes
- [ ] HTTPS con certificado válido y redirección desde el puerto 80

**Seguridad**

- [ ] `SIGREP_SECRET_KEY` generada aleatoriamente y solo en el panel de Dokploy
- [ ] `SIGREP_ENTORNO=produccion` (`/docs` responde 404)
- [ ] `SIGREP_CORS_ORIGENES` con el dominio real, nunca `*`
- [ ] Repositorio **privado** y `.env` confirmado como no versionado
- [ ] Clave del usuario `gerente` cambiada tras el primer acceso
- [ ] Cuenta de base de datos con privilegio mínimo

**Operación**

- [ ] Respaldos activados y **una restauración probada**
- [ ] Servicio de tipo *Stack* confirmado en el log de despliegue
- [ ] Paquetes de GHCR en visibilidad pública
- [ ] `DOKPLOY_WEBHOOK_URL` en los secretos y entorno `produccion` con revisor

**Funcional**

- [ ] Semilla ejecutada y estructura verificada (4 grupos, 16 PDV, 8 categorías)
- [ ] Días hábiles de las zonas pendientes **confirmados con el negocio**
- [ ] Umbral del semáforo **confirmado por escrito con Gerencia**
- [ ] Presupuesto del período cargado
- [ ] Una ingesta de venta completa ejecutada y su bitácora revisada
- [ ] Usuarios creados con sus roles

---

## 11. Contactos

| Rol | Responsabilidad |
|---|---|
| Gerencia | Umbrales del semáforo, días hábiles, regla de comisión |
| Departamento de Tecnología | Despliegue, operación, respaldos |
| Líder técnico | Migraciones y revisión de cambios de esquema |
