# Integración con la API de consulta

Validación contra `https://apiconsulta.grupo-santacruz.com`, 12 y 13 de agosto
de 2026. Documento para llevar a quien administra la API.

> **Estado: la integración está implementada y funcionando.** `FuenteVentaSiesa`
> consume **un solo endpoint**, `GET /ventas/costos-razon-social`. Se activa con
> `SIGREP_FUENTE_VENTA=siesa`.
>
> **Quedan dos asuntos que solo se resuelven del lado de la API** —el costo de
> PEREIRA y el número de documentos, que el negocio pidió y la fuente no
> entrega— más una consulta menor: ver §4.

## Resumen para quien tenga prisa

| | |
|---|---|
| **Fuente de SIGREP** | `GET /ventas/costos-razon-social` — un solo endpoint, los 15 puntos |
| **Validación** | **14 de 15** puntos de venta cuadran **al peso exacto** con el Excel del negocio el 1-ago-2026 |
| **Autenticación** | Cabecera `Authorization`, token pelado, **sin el prefijo `1-`** |
| **Fechas** | `fecha_fin` **INCLUSIVA**, declarada así en su contrato. Es lo contrario de `poscarnes` |
| **Pendiente** | El módulo `SIN ACUMULAR` —PEREIRA— no entrega costo, así que su margen es «—» |
| **Pendiente** | Ningún endpoint entrega el **número de documentos**; el indicador no se publica (§4.4) |

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

> **Se corrigió dos veces, y conviene saber por qué.** Primero se dio por buena
> `poscarnes` —reproducía el Excel dentro del 0,5 % en 10 de 13 puntos, pero sin
> categoría, con los kilos mezclados con unidades y descuadrando LA 43—. Después
> `vendedor-acumulada`, que cuadraba al peso pero no traía PEREIRA y obligaba a
> unir un segundo endpoint a mano. **La buena es `costos-razon-social`.**

Comparación contra la hoja `VENTA` del libro que el negocio usa hoy, sumando
`Valor subtotal` por centro de operación del **1 de agosto de 2026**, pidiendo
`fecha_inicio = fecha_fin = 2026-08-01`:

| C.O. | Excel (hoy) | `costos-razon-social` | `poscarnes` |
|---|---:|---:|---:|
| 402 MALAMBO | 28 458 475 | **= exacto** | 28 485 988 |
| 403 LA GRANJA | 21 413 829 | 26 633 877 | 26 633 877 |
| 405 LA 43 | 90 157 657 | **= exacto** | 60 968 886 |
| 406 SIMON | 66 470 122 | **= exacto** | 66 519 595 |
| 407 LA 70 | 107 371 024 | **= exacto** | 107 862 160 |
| **409 PEREIRA** | 101 453 550 | **= exacto** | 0 |
| 412 BUCARAMANGA | 106 242 616 | **= exacto** | 106 408 976 |
| 413 LA 93 | 66 931 088 | **= exacto** | 67 038 110 |
| 414 CENTRO | 35 782 706 | **= exacto** | 35 854 918 |
| 415 CARTAGENA | 32 577 346 | **= exacto** | 0 |
| 603 CONCORDE | 39 927 917 | **= exacto** | 39 942 389 |
| 605 ALAMEDA 1 | 50 200 928 | **= exacto** | 50 200 928 |
| 606 ALAMEDA 2 | 28 133 598 | **= exacto** | 28 338 636 |
| 701 SAN FELIPE | 40 562 440 | **= exacto** | 40 562 440 |
| 702 OLAYA | 45 727 676 | **= exacto** | 45 828 109 |

**`GET /ventas/costos-razon-social` es la fuente de SIGREP.** Catorce de quince
puntos coinciden **al peso**, no aproximadamente.

### El campo `Origen` es la clave

El endpoint hace por sí solo la unión de los dos módulos de venta, y marca cada
fila con su procedencia:

| `Origen` | Filas | Venta 1-ago | Costo | Qué es |
|---|---:|---:|---:|---|
| `ACUMULADO` | 2 289 | 765 177 470 | 545 228 758 | Los 14 puntos. Idéntico a lo que devuelve `vendedor-acumulada` |
| `SIN ACUMULAR` | 203 | 101 453 550 | **0** | **Solo PEREIRA** |

**Los dos son complementarios y no se solapan: hay que sumar los dos.** Que el
total cuadre al peso con el Excel lo demuestra.

Esto resolvió de golpe el descuadre de PEREIRA: `pos-vendedor-detalle` la daba a
**135 201 210** y aquí sale a **101 453 550**, que es lo que dice el libro. Un
33 % de diferencia —33 747 660 en un solo día— en el segundo punto de venta más
grande de la compañía.

### Lo que trae, y lo que no

Trae `Categoria` en el formato exacto del Excel (`"0001 - RES"`, con las dos
variantes de `0006`, que la tabla `mapeo_categorias` resuelve tal cual),
`CostoPromedio`, `CantidadInv` en kilos limpios, `UtilidadBruta` y
`PorcRentabilidad`.

**No trae vendedor.** `vendedor-acumulada` sí entregaba `CodigoVendedor` y
`NombreVendedor`. Hoy no se pierde nada —SIGREP no persiste todavía el vendedor
y el reporte por vendedor sale del catálogo de clientes—, pero el reporte por
vendedor **del POS**, donde la venta es anónima y no hay cliente al que
colgarla, queda bloqueado mientras la fuente sea esta. Si hiciera falta, se
resuelve con una segunda consulta a `vendedor-acumulada` o a `canales-vendedor`.

### LA GRANJA: aquí el que se desvía es el Excel

Es la única fila que no cuadra, y merece la lectura contraria a la evidente:
**los tres endpoints de la API dan el mismo número** (26 633 877) y el Excel da
21 413 829. Tres fuentes independientes coincidiendo entre sí señalan al libro,
no a la API.

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
> exclusivamente el negocio de carnes, y por eso consulta `costos-razon-social`
> con `id_cia` 4, 6 y 7 — nunca la 3 ni la 8. No hay que conciliar las dos
> cifras ni sumarlas: son negocios distintos.

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

De los tres asuntos que abrió la primera validación **no queda ninguno**: la
categoría, el descuadre de LA 43 y la ausencia de CARTAGENA y PEREIRA se
resolvieron al encontrar el endpoint correcto. Quedan **dos asuntos** —el costo
de PEREIRA (§4.1) y el número de documentos (§4.4)— y una consulta.

### 4.1 El módulo `SIN ACUMULAR` no entrega el costo · **único bloqueante**

Las 203 filas de PEREIRA del 1 de agosto traen `CostoPromedio` en **cero**,
frente a 545 228 758 de costo real en el resto. No es que PEREIRA venda sin
costo: es que ese módulo no lo publica.

Consecuencia en SIGREP, y es visible a propósito: el margen de PEREIRA, el de su
grupo y el **consolidado de toda la compañía** se publican como «—». No se
rellena con cero, porque `(venta − 0) / venta` daría un **100 % de margen que
nadie ha ganado**, y un número falso en la pantalla de la gerencia es peor que
un hueco. El resto de indicadores de PEREIRA —cumplimiento, ideal, proyección,
crecimiento— se calculan con toda normalidad.

Nótese que SIGREP **no deduce esto del cero**: se apoya en `Origen = SIN
ACUMULAR`, que es una afirmación sobre el módulo. Un costo de cero en
`ACUMULADO` sí se toma como costo cero, porque ahí es un dato legítimo.

**La pregunta:** ¿puede el módulo `SIN ACUMULAR` devolver el costo, como ya hace
`ACUMULADO` en el mismo endpoint?

### 4.2 Consulta: unificar la semántica de `fecha_fin`

Ver §2. `poscarnes` la trata como exclusiva; `costos-razon-social`,
`vendedor-acumulada` y `pos-vendedor-detalle` como inclusiva. Cualquiera que
consuma varios endpoints cargará un día de más o de menos sin enterarse.

### 4.3 Menor: campos que el Excel tiene y esta fuente no

NIT de cliente, condición de pago, domicilio y clase de cliente. Afectan solo a
la pantalla de clientes, no al reporte de cumplimiento. Existen
`/clientes-por-cia` y `/ventas/canales-vendedor` si hicieran falta.

### 4.4 Petición nueva: el **número de documentos** por centro y fecha

**Qué pide el negocio.** En el reporte de venta diaria, junto a la venta de cada
día, cuántos documentos se hicieron: facturas o tiquetes. Es la medida del
tráfico del punto de venta y, dividiendo, la del tiquete promedio. Hoy no sale
de ninguna parte.

**Por qué no se puede hoy.** Se verificaron los dos endpoints candidatos y
**ninguno de los dos entrega el dato**:

| Endpoint | ¿Número de documento? | ¿Conteo de documentos? |
|---|---|---|
| `GET /ventas/costos-razon-social` — la fuente de SIGREP | no | no |
| `GET /ventas/ventas-razon-social` | no | no |

Los dos llegan **ya agregados por centro de operación, categoría, ítem y
fecha**. La agregación ocurre del lado de la API, así que la identidad del
documento se pierde antes de que SIGREP vea la primera fila: no es que SIGREP la
descarte, es que no llega. `venta_lineas`, en consecuencia, tampoco tiene esa
columna.

**Y no se aproxima contando líneas.** Conviene dejarlo escrito porque es la
tentación evidente y el error sería grave: contar líneas **no** es contar
documentos. Una venta de ocho productos son ocho líneas y **un solo documento**.
Publicar ese conteo como «documentos» pondría en la pantalla de la gerencia una
cifra ocho veces mayor que la real, y con pinta de exacta. Es el mismo criterio
que en §4.1 con el costo de PEREIRA: **un número creíble y falso es peor que un
hueco visible**. Mientras la fuente no lo entregue, SIGREP no publica el
indicador —ni siquiera vacío— y la pantalla no reserva la columna.

**La pregunta:** ¿puede alguno de los dos endpoints devolver, dentro de la misma
agregación que ya hace, una columna de **conteo distinto de documentos** por
centro y fecha? Bastaría algo del estilo `NumDocumentos`, un
`COUNT(DISTINCT documento)` del lado de Siesa, donde la identidad del documento
todavía existe. **No hace falta el número de documento en sí**, y de hecho es
preferible que no venga: el detalle documento a documento multiplicaría el
volumen de la extracción sin que SIGREP lo necesite para nada.

Si el conteo no fuera posible en esos dos, la alternativa sería indicar cuál de
los demás endpoints lo publica y con qué grano; SIGREP lo uniría por
(centro, fecha) con una segunda consulta, como ya se planteó en su día con
`vendedor-acumulada`.

### 4.5 Petición nueva: el **identificador del cliente** en `/ventas/agropecuaria`

**Qué falta.** `GET /ventas/agropecuaria` entrega el cliente **solo por nombre**.
Es la única dimensión del endpoint sin identificador: todas las demás traen el
suyo —`tipoitem_id`, `especie_id`, `tipocomercial_id`, `grupo_id`, `item_ref`,
`codigovendedor`— y el cliente no.

**Qué consecuencias tiene**, comprobadas sobre una carga real de siete días
(compañía 3, 2.706 líneas, 686 clientes):

1. **Dos clientes distintos con el mismo nombre registrado se funden en uno.**
   Sin clave, SIGREP agrupa por la única cosa que recibe, que es el texto. No
   hay forma de detectarlo desde este lado: la venta de los dos aparece sumada
   en una fila y con pinta de correcta.
2. **No se puede cruzar con nada.** Ni con el ERP, ni con la cartera, ni con la
   instancia de carnes —que sí recibe NIT en `costos-razon-social`—. Un cliente
   que le compra a las dos unidades no se puede ver junto.
3. **El nombre no es estable.** El día que alguien corrija una razón social en
   SIESA, el histórico de SIGREP se parte en dos clientes: el de antes de la
   corrección y el de después, sin aviso.

**La pregunta:** ¿puede `/ventas/agropecuaria` añadir el NIT o el código
interno del tercero, junto al nombre que ya envía, como hace
`costos-razon-social`? Es un campo por fila y no cambia el grano de la
agregación.

**Qué está esperando a este campo.** El escalafón de clientes de agropecuaria
publica hoy el ranking, el importe y la última venta del corte, y **no** la
pestaña de «clientes que dejaron de comprar», que era lo que pedía el negocio.
Decir que alguien dejó de comprar exige emparejar al mismo cliente entre dos
períodos, y por nombre eso convierte una razón social corregida en SIESA en una
alerta falsa: «uno dejó de comprar y apareció otro nuevo». Se decidió dejarla
fuera antes que publicarla aproximada. Con el NIT se construye en una tarde.

**Mientras tanto**, SIGREP usa el nombre como clave y lo dice: es la lectura
correcta de lo que llega, no una aproximación disfrazada. Pero el reporte por
cliente y el cruce vendedor × cliente valen lo que valga la unicidad de los
nombres en el maestro de terceros, y eso no se puede verificar desde aquí.

---

## 5. Cómo está implementado en SIGREP

`FuenteVentaSiesa` (`backend/app/infrastructure/fuentes/siesa.py`) está detrás
del puerto `FuenteVenta` (§5 de la especificación). Se activa con
`SIGREP_FUENTE_VENTA=siesa`; el resto del sistema no se entera de cuál es la
fuente.

- **Un solo endpoint**, `costos-razon-social`, recorriendo `id_cia` 4, 6 y 7
  —aquí `id_cia` es obligatorio, a diferencia de otros endpoints—.
- **Descarga con `format=csv`**, en streaming. Un mes son cientos de miles de
  filas y no caben en memoria de golpe.
- **`fecha_fin` viaja tal cual**, sin sumarle un día, porque es inclusiva. Hay
  una prueba que lo fija: es la trampa que más fácil se reintroduce.
- **Las dos `Origen` se suman**, y cada corrida anota en la bitácora cuántas
  filas vinieron de cada una. Esa cuenta es la señal que avisará el día que
  `SIN ACUMULAR` empiece a traer costo o cambie de módulo.
- **`Origen` es columna obligatoria**: sin ella no se puede saber qué filas
  carecen de costo, así que la carga falla en vez de degradarse en silencio y
  publicar el 100 % de margen que §4.1 describe.
- **Ninguna prueba llama a la red**: se simula el CSV con las columnas reales.
- El token nunca aparece en un log, en un error ni en una traza.

La ingesta es **idempotente** (§5): reprocesar un rango lo reemplaza, no
duplica. La carga desde el Excel sigue disponible y probada como alternativa.
