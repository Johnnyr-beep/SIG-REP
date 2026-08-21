# Donde vamos — 21 de agosto de 2026

Nota de continuidad. Lo que esta hecho, lo que falta y de quien depende.

> **SIGREP esta EN PRODUCCION** en https://sigrep.grupo-santacruz.com
> API operativa, base conectada, certificado valido. Cuentas `admin` y `gerente`
> creadas. **La base de produccion no tiene datos todavia**: `ultima_ingesta: null`.
> Lo que se cargo estos dias fue en una base **local**, para probar la cadena.

## Hecho

| | |
|---|---|
| Backend | FastAPI · **482 pruebas en verde** · ruff y mypy limpios · migraciones hasta `0007` |
| Frontend | React + TS · **17 pantallas** · typecheck y build limpios |
| Integración SIESA carnes | `FuenteVentaSiesa` sobre `costos-razon-social`, validada contra el Excel: **14 de 15 puntos al peso exacto** |
| **Unidad agropecuaria** | **Completa**: 13 endpoints, 6 pantallas, exportacion a Excel, ingesta probada contra la API real |
| Contrato | `docs/API.md` documenta las 13 rutas de `/agro` y los tres enumerados |
| Repositorio | `github.com/Johnnyr-beep/SIG-REP` (privado), 26 commits |
| **Produccion** | **Desplegada y respondiendo**, dominio con TLS de Let's Encrypt |
| Usuarios | Modulo completo: rol ADMIN, alta, roles, alcances, auditoria y cambio de clave |
| Marcas | Selector de unidad, ahora dirigido por `unidades` de `GET /salud` |

---

## Agropecuaria: la primera carga real

Siete dias de julio de 2026, compania 3, contra la API de verdad:

```
2.706 lineas leidas · 2.706 aceptadas · 0 rechazos · 3 segundos
```

Los siete ejes dan **el mismo total, 3.147.729.924,39**, que es exactamente el
invariante que se buscaba: la misma venta cortada de siete formas.

| Eje | Filas |
|---|---|
| Centro de operacion | 2 — `301` AGROPECUARIA SANTACRUZ LTDA (2.890 M) · `302` DISTRIBUCION SANTACRUZ MONTERIA (257 M) |
| Tipo de item | 2 — BIENES (margen 15,64 %) · SERVICIOS (98,72 %) |
| Tipo comercial | 13 — CORTE, CANAL, SUBPRODUCTO, SACRIFICIO, DESPOSTE, LOGISTICA, VIVERES, CHORIZO… |
| Especie | 5 — RES, CERDO, CARNES FRIAS, VIVERES, ÑAN ÑAN |
| Grupo | 9 — letras sueltas, mas un `SIN GRUPO` de 396 M |
| Vendedor | 23 |
| Cliente | 686 |

**Ojo con el catalogo**: los **cortes son un tipo comercial, no una especie**, y
`BIENES`/`SERVICIOS` es `tipo_item`, no `tipo_comercial`. Es al reves de como
suena, y el que lo asuma de memoria se equivoca.

---

## Lo primero cuando se retome

1. **Cargar un mes en produccion y cuadrar contra el Excel.** Sigue siendo lo
   unico que falta para que el sistema sirva. Las dos unidades estan
   construidas; carnes esta validada punto por punto contra el libro, pero
   **nadie ha cerrado un mes completo con el sistema**.

2. **Desplegar.** Lo de agropecuaria esta en GitHub, no en el contenedor. El
   paso «Desplegar en Dokploy» del CI sale rojo siempre: falta el secreto
   `DOKPLOY_WEBHOOK_URL` y el webhook rechaza con `Branch Not Match` porque
   tiene otra rama configurada. Arreglarlo es lo que hara que dejen de hacer
   falta clics.

3. **Parametrizar el presupuesto de agropecuaria.** Hoy no hay ninguna de las
   cuatro dimensiones capturada, asi que todos los reportes de la unidad salen
   sin cumplimiento, sin semaforo y sin proyeccion. La pantalla lo dice, pero
   dicho no es resuelto.

---

## Pendiente de decision del negocio

- Dias habiles reales de las 7 zonas de carnes (se corre con el supuesto de 28).
- Dias habiles de los dos centros de agropecuaria.
- Umbrales del semaforo y regla de comision.
- Confirmar el presupuesto redistribuido de 616 M tras retirar `OTROS`.
- Fuente del historico de 2025.

## Pendiente del administrador de la API SIESA

Los tres estan escritos con detalle en `docs/INTEGRACION-SIESA.md`:

| | Que se pide | Estado |
|---|---|---|
| §4.1 | Costo en el modulo `SIN ACUMULAR` | **Bloqueante** para el margen de PEREIRA |
| §4.4 | `COUNT(DISTINCT documento)` por centro y fecha | Sin el, no hay numero de documentos ni tiquete promedio |
| §4.5 | **Identificador del cliente en `/ventas/agropecuaria`** | Nuevo. Hoy el cliente solo llega por nombre |

El §4.5 salio de esta carga: es la unica dimension del endpoint sin clave
propia. Dos clientes con la misma razon social se funden en uno y no hay forma
de cruzar con el ERP ni con la instancia de carnes, que si recibe NIT.

---

## Deuda conocida

- **Modo de ejemplos sin agro.** `VITE_SIGREP_EJEMPLOS=1` no tiene datos de la
  unidad: las pantallas de agro responden «Sin datos de ejemplo para…». No
  afecta a produccion —la variable no se define alli— pero impide ensenar la
  maqueta sin backend.
- **Tres credenciales pasaron por el chat y siguen sin rotar**: el token de
  SIESA, la clave de la base y la URL del webhook de Dokploy.
- **El panel de Dokploy esta expuesto en HTTP plano** en el puerto 3000.
- La semilla no admite `--forzar-clave`.
