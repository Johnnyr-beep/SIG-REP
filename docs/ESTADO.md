# Dónde vamos — 14 de agosto de 2026

Nota de continuidad. Lo que está hecho, lo que falta y qué depende de quién.

---

## Hecho

| | |
|---|---|
| Backend | FastAPI · **378 pruebas en verde** · ruff y mypy limpios · migraciones hasta `0005` |
| Frontend | React + TS · 8 pantallas · typecheck y build limpios |
| Integración SIESA | `FuenteVentaSiesa` sobre `costos-razon-social`, validada contra el Excel: **14 de 15 puntos al peso exacto** |
| Categorías | Las 11 reales de SIESA. `OTROS` retirada y su presupuesto repartido |
| Repositorio | `github.com/Johnnyr-beep/SIG-REP` (privado), 10 commits |
| Instancia local | `localhost:8080` con los datos reales cargados |
| Servidor | Dokploy en `20.121.178.90`, proyecto y base creados |

---

## Bloqueado — tres cosas, ninguna es de programación

### 1. DNS · lo bloquea todo

`sigrep.grupo-santacruz.com` **no existe**. Sin él no hay certificado ni acceso.

El dominio lo sirve **Cloudflare** (`connie`/`corey.ns.cloudflare.com`), no Azure:
lo que se cree en Azure DNS no tiene efecto. Registro a crear:

```
Type: A · Name: sigrep · IPv4: 20.121.178.90 · Proxy: DNS only (nube GRIS)
```

La nube gris es temporal: con la naranja, Let's Encrypt valida contra Cloudflare
y el certificado no se emite, con un error que no menciona Cloudflare. Después
de emitirlo se puede activar el proxy, pero con SSL en **Full (strict)**.

### 2. Imágenes de GHCR en privado

`docker stack deploy` no compila: descarga. GitHub las publica privadas y el
servidor no puede bajarlas. Una vez: GitHub → **Packages** → `sigrep-api` y
`sigrep-web` → *Package settings* → *Change visibility* → **Public**.

### 3. El servicio de Dokploy debe ser tipo `Stack`

Traefik corre en modo Swarm y **solo ve servicios de Swarm**. Si el servicio se
creó como *Application*, le es invisible y el dominio responde `404 page not
found` en texto plano con los contenedores sanos. Dokploy fija el tipo al crear:
si no es `Stack`, hay que borrarlo y rehacerlo.

### Variables de entorno — el bloque completo

Ya validado; solo faltaba pegarlo bien (la primera vez fueron los marcadores sin
reemplazar). Cuidado con tres detalles que no son cosméticos: el espacio de
`DB SIG-REP` va **literal**, el token de SIESA **sin el prefijo `1-`**, y
ninguna URL lleva **barra final** —una barra en `CORS_ORIGENES` bloquea todas
las peticiones del navegador con un error que habla de CORS y no de la barra—.

---

## Pendiente del negocio

1. **Días hábiles de 7 zonas** — MALAMBO, CONCORDE, SAN FELIPE, OLAYA, LA 93,
   ALAMEDA y EVENTOS corren con el supuesto de 28. **Mueve el semáforo** de esos
   puntos: es la decisión de más impacto que queda.
2. **Umbrales del semáforo** — amarillo bajo el 90 % del ideal, supuesto mío.
3. **Regla de comisión** — campo modelado, fórmula sin definir. No bloquea.
4. **Confirmar el presupuesto repartido** de las cuatro categorías nuevas. El
   reparto proporcional es un punto de partida y así lo dice cada renglón del
   historial.
5. **Crecimiento contra 2025** — la API no tiene 2025 (medido: 14, 22 y 4 filas
   en todo el año). O se carga de otra fuente, o el indicador sale «—» hasta que
   2026 sirva de base.

---

## Pendiente con el administrador de la API

Uno solo, en `INTEGRACION-SIESA.md` §4.1: **el módulo `SIN ACUMULAR` no entrega
el costo**, así que PEREIRA no tiene margen y el consolidado de la compañía lo
publica como «—». Es deliberado: rellenar con cero daría un 100 % de margen que
nadie ha ganado.

---

## Seguridad — sin cerrar

1. **Rotar tres credenciales** que pasaron por el chat: token de SIESA, clave de
   la base y webhook de Dokploy.
2. **El panel de Dokploy está en HTTP plano** — `http://20.121.178.90:3000`
   responde desde internet sin cifrar, y ahí se administra el despliegue de
   todos los sistemas. Las credenciales viajan en claro. Debería ir tras HTTPS o
   restringido por IP en el grupo de seguridad de Azure.
3. Decisiones menores abiertas: mensaje de «cuenta desactivada» que permite
   enumerar usuarios, `/salud` público con versión y fecha de última ingesta, y
   sin límite de peticiones en el login.

---

## Aparte: GSC ONE

Dos defectos encontrados de rebote, **no corregidos** por estar fuera de alcance:

1. **Está caído ahora mismo**: `gsc.grupo-santacruz.com` devuelve `404 page not
   found`. Es el síntoma del modo Swarm descrito arriba, no un fallo de la
   aplicación.
2. `frontend/docker/nginx.conf` **pierde las cabeceras de seguridad** —CSP
   incluida— en `/index.html` y `/assets/`, porque `add_header` no se hereda en
   un `location` que declare cabeceras propias. Activo en producción.
3. `docker-compose.yml:25` monta el volumen de PostgreSQL en la ruta que la
   imagen 18 abandonó; con esa imagen el contenedor aborta.

---

## Lo primero mañana

El DNS. Bloquea todo lo demás y es un formulario de seis campos.
