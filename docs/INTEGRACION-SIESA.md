# Integración con la API de consulta

Hallazgos de la validación del **12 de agosto de 2026** contra
`https://apiconsulta.grupo-santacruz.com`. Documento para llevar a quien
administra la API: **hay tres asuntos que solo se pueden resolver de ese lado**.

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

## 2. `fecha_fin` es EXCLUSIVA

Lo declara el propio contrato: *«Fecha final (exclusiva)»*.

Para cargar agosto hay que pedir `fecha_inicio=2026-08-01&fecha_fin=2026-09-01`.
Pedir `fecha_fin=2026-08-31` **pierde el día 31 sin avisar**, y el cumplimiento
del mes saldría corto justo en el cierre, que es cuando se mira.

## 3. Qué endpoint es la fuente correcta

Se compararon los dos candidatos contra la hoja `VENTA` del libro que el
negocio usa hoy, sumando `Valor subtotal` por centro de operación del
**1 de agosto de 2026**:

| C.O. | Excel (hoy) | `poscarnes` | `agropecuaria` |
|---|---:|---:|---:|
| 402 MALAMBO | 28 458 475 | 28 485 988 | 39 609 522 |
| 403 LA GRANJA | 21 413 829 | **26 633 877** | 49 184 637 |
| 405 LA 43 | 90 157 657 | **60 968 886** | 146 243 868 |
| 406 SIMON | 66 470 122 | 66 519 595 | 119 696 234 |
| 407 LA 70 | 107 371 024 | 107 862 160 | 173 309 900 |
| **409 PEREIRA** | **101 453 550** | **0** | **0** |
| 412 BUCARAMANGA | 106 242 616 | 106 408 976 | 163 039 676 |
| 413 LA 93 | 66 931 088 | 67 038 110 | 103 227 017 |
| 414 CENTRO | 35 782 706 | 35 854 918 | 37 507 982 |
| **415 CARTAGENA** | **32 577 346** | **0** | **780 000** |
| 603 CONCORDE | 39 927 917 | 39 942 389 | — |
| 605 ALAMEDA 1 | 50 200 928 | 50 200 928 | — |
| 606 ALAMEDA 2 | 28 133 598 | 28 338 636 | — |
| 701 SAN FELIPE | 40 562 440 | 40 562 440 | — |
| 702 OLAYA | 45 727 676 | 45 828 109 | — |
| **TOTAL** | **861 410 972** | **704 645 012** | — |

**`GET /ventas/poscarnes` es la fuente correcta para SIGREP.** Reproduce el
Excel dentro del 0,5 % en 10 de 13 puntos, y en dos de ellos —ALAMEDA 1 y
SAN FELIPE— al peso exacto.

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
> exclusivamente el POS de carnes y consume solo `poscarnes`. No hay que
> conciliar las dos cifras ni sumarlas: son negocios distintos.

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

## 4. Los tres asuntos abiertos — para el administrador de la API

### 4.1 PEREIRA reporta por otro módulo de POS · **bloqueante**

> **Corrección de una versión anterior de este documento**, que afirmaba que
> PEREIRA «no existe en la API». Era falso: no estaba en los dos endpoints que
> se habían mirado. **Sí está en `GET /ventas/pos-vendedor-detalle`.**

`409 PEREIRA` devuelve cero filas en `poscarnes` (t9930) y en `agropecuaria`
(t470), también consultando `id_co=409` en un rango de diez días y sin filtro de
compañía. Pero `pos-vendedor-detalle` —**t9830/t9820, otro módulo de POS**— el
1 de agosto devuelve 6671 filas y **todas son PEREIRA**: ningún otro punto de
venta aparece ahí, en ninguna compañía (se probó 3, 4, 5, 6, 7 y 8).

Es decir: los 13 puntos restantes registran en `t9930` y **PEREIRA registra en
`t9830/t9820`**. Dos módulos de punto de venta conviviendo.

Dos cosas que siguen sin cuadrar:

- **El importe no coincide.** `pos-vendedor-detalle` da 135 201 210 y el Excel
  101 453 550 para el mismo día: **33 747 660 de más, un 33 %**.
- **No trae costo.** `costo_promedio` viene nulo en **el 100 %** de las 6671
  filas, así que por ese endpoint no se puede calcular el margen (§4.4 de la
  especificación), que sí se calcula para los demás puntos.

`415 CARTAGENA` sigue sin aparecer: 32 577 346 en el Excel, cero en `poscarnes`,
cero en `pos-vendedor-detalle` y una única fila de 780 000 en `agropecuaria`.

**Las preguntas:**

1. ¿Por qué PEREIRA registra en otro módulo? ¿Es definitivo o está en migración?
2. ¿Puede `poscarnes` incluir también `t9830/t9820`, de modo que un solo
   endpoint devuelva los 14 puntos?
3. ¿Se puede exponer el costo en `pos-vendedor-detalle`? Sin él, PEREIRA no
   tiene margen.
4. ¿Dónde registra CARTAGENA?

### 4.2 Dos puntos no cuadran · **bloqueante**

- **405 LA 43**: la API reporta 60 968 886 y el Excel 90 157 657. Faltan
  **29 188 771**, un 32 %.
- **403 LA GRANJA**: la API reporta 26 633 877 y el Excel 21 413 829. La API da
  **5 220 048 de más**, un 24 %.

No es redondeo ni diferencia de zona horaria: son los dos únicos puntos con
desviación grande, y en direcciones opuestas. Sumando esto y el punto 4.1, la
API queda **156 765 960 por debajo del Excel en un solo día: un 18 %**.

Conectar SIGREP a esta fuente hoy produciría un reporte que subestima a la
compañía en esa proporción.

### 4.3 `poscarnes` no trae categoría ni kilos limpios · **bloqueante**

SIGREP reporta por punto de venta **y categoría** (RES, CERDO, POLLO,
VÍSCERAS, EMBUTIDOS, PESCADO, ASADERO, OTROS), en pesos **y en kilos**.

- **No hay categoría.** `poscarnes` entrega `referencia` y
  `descripcion_producto`, no el `0001 - RES` que trae el Excel.

  Y sin embargo **la categoría existe en Siesa y la API ya la publica en otros
  dos endpoints, en el formato exacto del Excel**: `pos-vendedor-detalle`
  devuelve `categoria: "0001 - RES"` para PEREIRA, y `agropecuaria` devuelve
  `TipoItem_Id`/`TipoItem`. También `subproductos` da el par
  (`referencia`, `categoria`), aunque solo para 133 referencias de subproducto.

  Así que no falta el dato: falta exponerlo en el endpoint que sirve a los otros
  trece puntos. **¿Puede `poscarnes` devolver la categoría, como ya hace
  `pos-vendedor-detalle`?** Es, con diferencia, lo más barato de resolver de
  esta lista, y desbloquea la mitad del reporte.
- **Los kilos vienen mezclados.** `total_cantidad` convive con `unidad`, que
  toma los valores `KG`, `U` y `UN`. Sumar esa columna mezcla kilos con
  unidades y corrompe la mitad del reporte. Se necesita o bien un campo de
  kilos separado —`agropecuaria` sí tiene `KilosTotal` aparte de
  `CantidadInv`—, o el factor de conversión por referencia.

### 4.4 Menor: campos que el Excel tiene y `poscarnes` no

`Cliente`, `Condición de pago`, `Domicilio` y `Clase de cliente`. Afectan solo
a la pantalla de clientes y vendedores, no al reporte de cumplimiento.
`agropecuaria` sí trae `Cliente`, `CodigoVendedor` y `NombreVendedor`, y
existen `/clientes-por-cia` y `/ventas/canales-vendedor`.

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
