# Integración con la API de consulta

Validación contra `https://apiconsulta.grupo-santacruz.com`, 12 y 13 de agosto
de 2026. Documento para llevar a quien administra la API.

> **Estado: la integración está implementada y funcionando.** `FuenteVentaSiesa`
> consume `vendedor-acumulada` y `pos-vendedor-detalle`. Se activa con
> `SIGREP_FUENTE_VENTA=siesa`.
>
> **Queda un solo asunto que solo se resuelve del lado de la API**, más una
> consulta menor: ver §4.

## Resumen para quien tenga prisa

| | |
|---|---|
| **Fuente de SIGREP** | `GET /ventas/vendedor-acumulada` (t461/t470), + `GET /ventas/pos-vendedor-detalle` solo para PEREIRA |
| **Validación** | 13 de 15 puntos de venta cuadran **al peso exacto** con el Excel del negocio el 1-ago-2026 |
| **Autenticación** | Cabecera `Authorization`, token pelado, **sin el prefijo `1-`** |
| **Fechas** | `fecha_fin` **INCLUSIVA** en estos dos endpoints. Es lo contrario de lo que documenta `poscarnes` |
| **Pendiente** | `415 CARTAGENA` no aparece en ningún endpoint · `pos-vendedor-detalle` no entrega costo |

---

## 1. El token

Se entrega con el formato `1-<64 caracteres hexadecimales>`. **El prefijo `1-`
no se envía**: es un identificador de clave, no parte del secreto. Enviarlo
completo devuelve `401 {"detail":"Token invalido."}`.

Se envía como cabecera `Authorization` con el valor pelado —sin `Bearer`—, o
como `X-API-Key`. Ambas funcionan. `Authorization: Bearer <token>` y
`Authorization: Token <token>` **no** funcionan, pese a que el mensaje de error
de la propia API sugiere `Bearer`.

Los dos mensajes de error se distinguen y conviene conocerlos:
`«Falta el token»` = no llegó ninguno; `«Token invalido»` = llegó y se rechazó.

Vive en `SIGREP_SIESA_TOKEN` dentro de `.env`, que nunca se versiona.

## 2. `fecha_fin` NO significa lo mismo en todos los endpoints

**Esta es la trampa más peligrosa de la API y conviene que la conozca cualquiera
que la consuma, no solo SIGREP.**

| Endpoint | `fecha_fin` |
|---|---|
| `poscarnes` | **exclusiva** — lo declara su contrato: *«Fecha final (exclusiva)»* |
| `vendedor-acumulada` | **INCLUSIVA** — medido |
| `pos-vendedor-detalle` | **INCLUSIVA** — medido |

Cómo se detectó: al comparar `vendedor-acumulada` contra el Excel pidiendo
`2026-08-01` a `2026-08-02`, casi todos los puntos salían un 42 % por encima. La
diferencia de ALAMEDA 1 era 32 820 028, que es **exactamente su venta del 2 de
agosto** en la hoja `Hoja1` del libro. Lo mismo en ALAMEDA 2 (18 701 584) y en
CONCORD (21 288 119). Repitiendo la consulta con `fecha_fin = fecha_inicio`,
todo cuadró al peso.

Consecuencia práctica: quien asuma la semántica de `poscarnes` al consumir
`vendedor-acumulada` **carga un día de más en cada extracción**, y el error es
invisible salvo que alguien cuadre a mano.

SIGREP lo tiene fijado con una prueba (`test_fuente_siesa.py`).

**Consulta para el administrador:** ¿es deliberado o es un descuido? Unificar el
criterio en todos los endpoints ahorraría este error a todos los consumidores.

## 3. Qué endpoint es la fuente correcta

> **Corrección.** Una versión anterior de este documento daba por buena
> `poscarnes`, que reproducía el Excel dentro del 0,5 % en 10 de 13 puntos pero
> no traía categoría, mezclaba kilos con unidades y descuadraba en LA 43.
> **`vendedor-acumulada` es mejor en todo eso y cuadra al peso.**

Comparación contra la hoja `VENTA` del libro que el negocio usa hoy, sumando
`Valor subtotal` por centro de operación del **1 de agosto de 2026**, pidiendo
`fecha_inicio = fecha_fin = 2026-08-01`:

| C.O. | Excel (hoy) | `vendedor-acumulada` | `poscarnes` |
|---|---:|---:|---:|
| 402 MALAMBO | 28 458 475 | **= exacto** | 28 485 988 |
| 403 LA GRANJA | 21 413 829 | 26 633 877 | 26 633 877 |
| 405 LA 43 | 90 157 657 | **= exacto** | 60 968 886 |
| 406 SIMON | 66 470 122 | **= exacto** | 66 519 595 |
| 407 LA 70 | 107 371 024 | **= exacto** | 107 862 160 |
| **409 PEREIRA** | 101 453 550 | **0** *(ver §4.1)* | 0 |
| 412 BUCARAMANGA | 106 242 616 | **= exacto** | 106 408 976 |
| 413 LA 93 | 66 931 088 | **= exacto** | 67 038 110 |
| 414 CENTRO | 35 782 706 | **= exacto** | 35 854 918 |
| 415 CARTAGENA | 32 577 346 | **= exacto** | 0 |
| 603 CONCORDE | 39 927 917 | **= exacto** | 39 942 389 |
| 605 ALAMEDA 1 | 50 200 928 | **= exacto** | 50 200 928 |
| 606 ALAMEDA 2 | 28 133 598 | **= exacto** | 28 338 636 |
| 701 SAN FELIPE | 40 562 440 | **= exacto** | 40 562 440 |
| 702 OLAYA | 45 727 676 | **= exacto** | 45 828 109 |

**`GET /ventas/vendedor-acumulada` (t461/t470) es la fuente de SIGREP.**
Trece de quince puntos coinciden **al peso**, no aproximadamente. Y a diferencia
de `poscarnes`, trae los tres campos que faltaban:

- **`categoria`** en el formato exacto del Excel (`"0001 - RES"`), incluidas las
  dos variantes ortográficas de `0006`. La tabla `mapeo_categorias` ya sembrada
  lo resuelve tal cual.
- **`costo_promedio`** diligenciado en el 100 % de las filas → hay margen.
- **`codigo_vendedor` / `nombre_vendedor`** → habilita el reporte por vendedor.

Y `cantidad` son kilos limpios, sin la mezcla `KG`/`U`/`UN` de `poscarnes`.

### LA GRANJA: aquí el que se desvía es el Excel

Es la única fila que no cuadra, y merece una lectura al revés de la evidente:
`vendedor-acumulada` y `poscarnes` dan **el mismo número** (26 633 877) y el
Excel da 21 413 829. **Los dos endpoints de la API coinciden entre sí**, así que
lo más probable es que sea el libro el que se queda corto, no la API.

SIGREP carga lo que dice la API y **no compensa nada**. Conviene que alguien del
negocio revise por qué el Excel pierde 5 220 048 en ese punto en un solo día.

### `agropecuaria` no es la misma venta mal contada: es otro canal

Conviene no leer la tercera columna como un error. Las descripciones de la
propia API nombran la tabla de Siesa que hay detrás de cada endpoint, y ahí está
la explicación:

| Endpoint | Tabla | Qué es |
|---|---|---|
| `poscarnes` | `t9930` | **POS**, venta de mostrador |
| `agropecuaria` | `t470` | Módulo agropecuario: **facturación** |
| `pos-vendedor-detalle` | `t9830`/`t9820` | POS línea a línea |
| `vendedor-acumulada` | `t461`/`t470` | Ventas **facturadas** |
| `canales-vendedor` | `t460`/`t470` | **Remisiones** de venta |

Las `t98xx` son punto de venta; las `t46x`/`t47x`, documentos de facturación.
Por eso `agropecuaria` trae `Cliente`, `CodigoVendedor`, `NombreVendedor`,
`TipoItem`, `Especie` y `Grupo` —una factura va a un cliente con nombre y
vendedor asignado— y `poscarnes` no trae nada de eso: la venta de mostrador es
anónima. El nombre del endpoint viene de `id_cia=3`, `AGROPECUARIA SANTACRUZ
LTDA`, la empresa que estrenó el módulo; hoy sirve a las compañías 3, 4, 6, 7 y 8.

> **DECISIÓN DEL NEGOCIO (13-ago-2026): la venta agropecuaria se reporta en una
> instancia aparte, con sus propios reportes.** Esta instancia de SIGREP cubre
> exclusivamente el negocio de carnes, y por eso consulta `vendedor-acumulada`
> y `pos-vendedor-detalle` filtrando por las compañías 4, 6 y 7 — nunca la 3 ni
> la 8. No hay que conciliar las dos cifras ni sumarlas: son negocios distintos.

### Centros de operación fuera del alcance de esta instancia

`agropecuaria` expone centros que el presupuesto de SIGREP no contempla y que
pertenecen a la otra instancia:

| C.O. | Compañía | Venta 1-ago |
|---|---|---:|
| 301 | AGROPECUARIA SANTACRUZ LTDA (cia 3) | 684 907 232 |
| 302 | DISTRIBUCIÓN SANTACRUZ MONTERÍA (cia 3) | 5 267 052 |
| 801 | MALAMBO (cia 8) | 115 766 314 |

Ojo con el 801: **hay dos MALAMBO**, el `402` de la compañía 4 —el que sí
presupuesta esta instancia— y el `801` de la compañía 8. Son puntos distintos y
no deben sumarse.

### El C.O. lleva la compañía en el primer dígito

Confirmado: `id_cia=4 → 4xx`, `id_cia=6 → 6xx`, `id_cia=7 → 7xx`, sin
solapamiento. **El código de centro de operación sigue siendo llave única entre
compañías**, así que el modelo de datos de SIGREP no necesita una dimensión de
compañía. `id_cia=5` devuelve cero filas.

Omitir `id_cia` devuelve las tres compañías en una sola consulta, que es lo que
SIGREP hará.

---

## 4. Lo que queda para el administrador de la API

De los tres asuntos que abrió la primera validación, **dos se resolvieron solos
al encontrar el endpoint correcto**: la categoría y el descuadre de LA 43. Queda
uno bloqueante y una consulta.

### 4.1 CARTAGENA no aparece en ningún endpoint · **bloqueante**

`415 CARTAGENA` vendió **32 577 346** el 1 de agosto según el Excel.

Aquí hay que ser preciso, porque el dato es contradictorio:
`vendedor-acumulada` **sí devuelve CARTAGENA y cuadra al peso** con el Excel
—está en la tabla de §3—. Lo que no aparece es en `poscarnes` (cero) ni en
`pos-vendedor-detalle` (cero), y en `agropecuaria` sale una única fila de
780 000.

Es decir: **para SIGREP, CARTAGENA está resuelto**, porque la fuente que usa lo
trae correctamente. Lo que queda es la duda de fondo: ¿por qué ese punto no
registra en el módulo de POS como los demás? Si mañana alguien construye otro
reporte sobre `poscarnes`, le faltará CARTAGENA entera y no lo sabrá.

**La pregunta:** ¿es correcto que CARTAGENA no tenga movimiento en el POS?

### 4.2 `pos-vendedor-detalle` no entrega el costo · **bloqueante para el margen**

`costo_promedio` viene **nulo en el 100 %** de las 6671 filas de PEREIRA del
1 de agosto. Es el único endpoint donde ese punto registra, así que **no hay
forma de calcular su margen**.

Consecuencia en SIGREP, y es visible: el margen de PEREIRA, el de su grupo y el
**consolidado de toda la compañía** se publican como «—». No se rellena con
cero: `(venta − 0) / venta` daría un **100 % de margen que nadie ha ganado**, y
un número falso en la pantalla de la gerencia es peor que un hueco. El resto de
indicadores de PEREIRA —cumplimiento, ideal, proyección, crecimiento— se
calculan con toda normalidad.

**La pregunta:** ¿puede `pos-vendedor-detalle` devolver el costo, como ya hace
`vendedor-acumulada`?

### 4.3 El importe de PEREIRA no coincide · **a revisar**

`pos-vendedor-detalle` da 135 201 210 y el Excel 101 453 550 para el mismo día:
**33 747 660 de más, un 33 %**.

No se pudo determinar de qué lado está la diferencia, porque PEREIRA no aparece
en ningún otro endpoint contra el que contrastar. Conviene revisarlo antes de
que el reporte de ese punto se use para tomar decisiones.

### 4.4 Consulta: unificar la semántica de `fecha_fin`

Ver §2. `poscarnes` la trata como exclusiva y `vendedor-acumulada` y
`pos-vendedor-detalle` como inclusiva. Cualquiera que consuma varios endpoints
va a cargar un día de más o de menos sin enterarse.

### 4.5 Menor: campos que el Excel tiene y la API no

NIT de cliente, condición de pago, domicilio y clase de cliente. Afectan solo a
la pantalla de clientes, no al reporte de cumplimiento. `vendedor-acumulada` sí
trae vendedor, y existen `/clientes-por-cia` y `/ventas/canales-vendedor`.

---

## 5. Qué queda hecho en SIGREP

Nada de esto bloquea el resto del sistema: la ingesta desde el Excel funciona y
está probada. `FuenteVentaSiesa` **no se implementa hasta resolver 4.1, 4.2 y
4.3**, porque hacerlo antes sería publicar cifras que sabemos incompletas.

Cuando se resuelvan, el trabajo es rellenar `obtener_ventas` en
`backend/app/infrastructure/fuentes/siesa.py` y cambiar
`SIGREP_FUENTE_VENTA=siesa`. Lo demás ya está:

- Paginación: `total`, `limit`, `offset`, `has_more`, `next_offset`.
  Máximo 5000 por página; `format=csv` descarga completa en streaming.
- Volumen medido: 2159 filas/día las tres compañías juntas en `poscarnes`
  —agregado por producto—, frente a las ~14 600 filas/día del Excel.
- Mapeo de campos ya identificado: `id_co` → punto de venta, `fecha` → fecha,
  `total_subtotal` → venta contra presupuesto, `total_costo` → costo del
  margen, `total_cantidad` → kilos *(sujeto a 4.3)*.
