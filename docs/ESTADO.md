# Donde vamos — 19 de agosto de 2026

Nota de continuidad. Lo que esta hecho, lo que falta y de quien depende.

> **SIGREP esta EN PRODUCCION** en https://sigrep.grupo-santacruz.com
> API operativa, base conectada, certificado valido. Cuentas `admin` y `gerente`
> creadas. **La base no tiene datos todavia**: `ultima_ingesta: null`.

## Hecho

| | |
|---|---|
| Backend | FastAPI · **424 pruebas en verde** · ruff y mypy limpios · migraciones hasta `0006` |
| Frontend | React + TS · 11 pantallas · typecheck y build limpios |
| Integración SIESA | `FuenteVentaSiesa` sobre `costos-razon-social`, validada contra el Excel: **14 de 15 puntos al peso exacto** |
| Categorías | Las 11 reales de SIESA. `OTROS` retirada y su presupuesto repartido |
| Repositorio | `github.com/Johnnyr-beep/SIG-REP` (privado), 19 commits |
| Instancia local | `localhost:8080` con los datos reales cargados |
| **Produccion** | **Desplegada y respondiendo**, dominio con TLS de Let's Encrypt |
| Usuarios | Modulo completo: rol ADMIN, alta, roles, alcances, auditoria y cambio de clave |
| Marcas | Selector de unidad de negocio con las tres identidades, paleta muestreada de los logos |

---

## Lo primero manana

1. **Desplegar.** El selector de marcas y la paleta estan en GitHub, no en el
   contenedor. Espere el CI y pulse **Deploy** en Dokploy. El paso «Desplegar en
   Dokploy» del CI sale rojo siempre: falta el secreto `DOKPLOY_WEBHOOK_URL` y
   el webhook rechaza con `Branch Not Match` porque tiene otra rama configurada.
   Arreglarlo es lo que hara que dejen de hacer falta clics.

2. **Revisar el selector en produccion, en claro y en oscuro.** Los contrastes
   se auditaron numericamente —17 pares por marca— pero nadie ha mirado las
   tarjetas con los ojos.

3. **Cargar el mes desde SIESA y cuadrar contra el Excel.** Es lo unico que
   falta para que el sistema sirva. Hasta que los numeros cuadren, SIGREP esta
   terminado pero no probado en lo que importa.

## Deuda conocida

- **La semilla no tiene `--forzar-clave`.** Si alguien pierde la clave que
  imprime, hoy la unica salida es un fragmento de Python contra la base de
  produccion. Ya paso una vez.
- **La instancia de agropecuaria** tiene su marca lista pero **no su modelo**:
  sus reportes serian los de carnes. Falta que el negocio entregue la API de
  agropecuaria y que defina que quiere medir —si es por vendedor, especie o
  cliente en vez de por punto de venta, el modelo actual no sirve—.

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
   found`. Es el mismo 404 de Traefik que tuvimos en SIGREP —el
   servicio no es de tipo Stack y el proxy no lo ve—, no un fallo de la
   aplicación.
2. `frontend/docker/nginx.conf` **pierde las cabeceras de seguridad** —CSP
   incluida— en `/index.html` y `/assets/`, porque `add_header` no se hereda en
   un `location` que declare cabeceras propias. Activo en producción.
3. `docker-compose.yml:25` monta el volumen de PostgreSQL en la ruta que la
   imagen 18 abandonó; con esa imagen el contenedor aborta.
