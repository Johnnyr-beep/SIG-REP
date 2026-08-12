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

**`GET /ventas/poscarnes` es la fuente correcta.** Reproduce el Excel dentro
del 0,5 % en 10 de 13 puntos, y en dos de ellos —ALAMEDA 1 y SAN FELIPE— al
peso exacto. `agropecuaria` mide otra cosa: infla entre 1,4 y 1,6 veces y no
cuadra con el reporte del negocio en ningún punto.

### El C.O. lleva la compañía en el primer dígito

Confirmado: `id_cia=4 → 4xx`, `id_cia=6 → 6xx`, `id_cia=7 → 7xx`, sin
solapamiento. **El código de centro de operación sigue siendo llave única entre
compañías**, así que el modelo de datos de SIGREP no necesita una dimensión de
compañía. `id_cia=5` devuelve cero filas.

Omitir `id_cia` devuelve las tres compañías en una sola consulta, que es lo que
SIGREP hará.

---

## 4. Los tres asuntos abiertos — para el administrador de la API

### 4.1 PEREIRA no existe en la API · **bloqueante**

`409 PEREIRA` vendió 101 453 550 el 1 de agosto según el Excel y devuelve
**cero filas** en los dos endpoints, también consultando por `id_co=409` en un
rango de diez días y sin filtro de compañía. En el mes lleva 497 438 844 de
venta y 1 968 185 977 de presupuesto: es el segundo punto más grande.

`415 CARTAGENA` está en el mismo caso: 32 577 346 en el Excel, cero en
`poscarnes` y una única fila de 780 000 en `agropecuaria`.

**Juntos son el 15,5 % del presupuesto de la compañía.** ¿En qué compañía o
endpoint viven? ¿Operan sobre otro ERP?

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
  `descripcion_producto`, no el `0001 - RES` que trae el Excel. Hace falta una
  tabla `referencia → categoría`. `GET /ventas/subproductos` devuelve
  exactamente ese par (`referencia`, `categoria`, `descripcion_criterio_mayor`)
  pero solo para 133 referencias de subproducto: **¿existe el mapeo completo
  para todas las referencias?** Es lo que falta para cerrar la integración.
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
