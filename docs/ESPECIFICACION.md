# SIGREP — Sistema Gerencial de Reportes

**Grupo Santa Cruz · Reportes gerenciales de venta contra presupuesto**

Documento de especificación. Es la fuente de verdad para todos los agentes que
trabajan en este repositorio. Antes de escribir código, léalo completo.

---

## 1. Qué resuelve

Hoy el seguimiento de venta contra presupuesto vive en un libro de Excel de
18 MB (`VENTA X PUNTO PRESUPUESTO.xlsx`) que se arma a mano cada mes: se exporta
la venta de SIESA, se pega en una hoja, se recalculan tablas dinámicas y se
reparten capturas de pantalla.

SIGREP reemplaza ese proceso por una aplicación web donde:

1. El presupuesto se **parametriza** una vez por mes, por punto de venta y
   categoría, en pesos y en kilos.
2. La venta se **ingiere automáticamente** desde SIESA.
3. El cumplimiento, la proyección y el semáforo se **calculan solos**, con las
   fórmulas escritas y visibles, no escondidas en una celda.

**SIGREP no reemplaza a SIESA.** SIESA es la fuente de verdad de la venta.
SIGREP es la capa de lectura gerencial: presupuesto, comparación y análisis.

---

## 2. Decisiones ya tomadas

| Decisión | Valor | Motivo |
|---|---|---|
| Ubicación | Aplicación separada en `Documents/SIGREP` | Decisión del usuario. Independiente de GSC ONE. |
| Parametrización del presupuesto | Mensual por PDV y categoría; el diario se **deriva** de los días hábiles de la zona | Replica el modelo que el negocio ya usa (`DIAS HABILES` / `DIAS TRABAJADOS` / `IDEAL`). |
| Stack | Idéntico a GSC ONE | El equipo ya lo domina y hay código probado que se puede portar. |

### Stack

```
Backend    Python 3.12 · FastAPI · SQLAlchemy 2.0 · Alembic · Pydantic v2
Base       PostgreSQL (SQL Server soportado por tipos genéricos)
Frontend   React 18 · TypeScript · Vite · TanStack Query · React Router
Infra      Docker Compose · Nginx · GitHub Actions
Idioma     Todo el código, los identificadores y la interfaz en español
Dinero     `Decimal` siempre. Nunca `float`.
```

Código reutilizable desde `../gsc-one/backend/app/`: `core/config.py`,
`core/db.py`, `core/security.py`, `core/errors.py`, `core/deps.py`,
`core/logging.py` y el patrón de `api/v1/auth.py`. Portarlo, no reinventarlo.
El prefijo de variables de entorno cambia de `GSC_` a `SIGREP_`.

---

## 3. El modelo del negocio

### 3.1 Jerarquía

```
GRUPO (4)  ──►  PUNTO DE VENTA (16)  ──►  CATEGORÍA (8)
```

**Grupos comerciales** — agrupación para el reporte consolidado:

| Código | Nombre | Puntos de venta |
|---|---|---|
| 001 | GRUPO 1 | MALAMBO, CONCORDE, LAGRANJA, SIMON |
| 002 | GRUPO 2 | BUCARAMANGA, PEREIRA, CARTAGENA |
| 003 | GRUPO 3 | CENTRO, SANFELIPE, OLAYA, LA43 |
| 004 | GRUPO 4 | LA70, LA93, ALAMEDA, ALAMEDA2 |

**Puntos de venta** — el código es el **C.O. (centro de operación) de SIESA**.
Es la llave de integración y no se inventa: viene de SIESA.

| C.O. | Nombre SIGREP | Descripción en SIESA |
|---|---|---|
| 402 | MALAMBO | PDV MALAMBO |
| 603 | CONCORDE | CONCORD |
| 403 | LAGRANJA | PDV LA GRANJA |
| 406 | SIMON | PDV SIMON |
| 412 | BUCARAMANGA | PDV BUCARMANGA *(sic, así viene de SIESA)* |
| 409 | PEREIRA | PDV PEREIRA |
| 415 | CARTAGENA | PDV CARTAGENA |
| 414 | CENTRO | PDV CENTRO |
| 701 | SANFELIPE | SAN FELIPE |
| 702 | OLAYA | OLAYA |
| 405 | LA43 | PDV LA 43 |
| 407 | LA70 | PDV LA 70 |
| 413 | LA93 | PDV LA 93 |
| 605 | ALAMEDA | ALAMEDA 1 |
| 606 | ALAMEDA2 | ALAMEDA 2 |
| 432 | EVENTOS BUCARAMANGA | EVENTOS BUCARMANGA — aparece en la venta, **no tiene presupuesto** |

> `432 EVENTOS BUCARAMANGA` vende pero no está presupuestado. El sistema debe
> mostrarlo y **no** debe romperse ni descuadrar el consolidado por eso.
> Regla: la venta de un PDV sin presupuesto se reporta aparte, nunca se
> descarta en silencio.

**Categorías** — la agrupación gerencial. SIESA entrega categorías crudas que se
mapean a ocho categorías de negocio (columna `NUEVA CATEGORIA` del Excel):

| Categoría SIESA | Categoría SIGREP |
|---|---|
| `0001 - RES` | RES |
| `0002 - CERDO` | CERDO |
| `0003 - POLLO` | POLLO |
| `0004 - PESCADO` | PESCADO |
| `0005 - EMBUTIDOS` | EMBUTIDOS |
| `0009 - VISCERAS` | VISCERAS |
| `0010 - RESTAURANTE` | ASADERO |
| `0006 - QUESO Y LACTEOS` | OTROS |
| `0006 - QUESOS Y LACTEOS` *(variante con typo)* | OTROS |
| `0007 - HUEVOS` | OTROS |
| `0008 - VIVERES` | OTROS |
| `0014 - DOMICILIOS` | OTROS |
| *(vacío / desconocido)* | OTROS + registro en bitácora de ingesta |

El mapeo es **una tabla en base de datos**, no un `dict` en el código: SIESA
añade categorías y el negocio las reclasifica sin esperar un despliegue.
Nótese que existen dos códigos `0006` con distinta ortografía; el mapeo debe
ser por texto exacto y ambos deben estar sembrados.

No todos los PDV manejan las ocho categorías: LA43 y ALAMEDA no tienen ASADERO.
El presupuesto por categoría es opcional; su ausencia no es un error.

### 3.2 Zonas y calendario — el corazón de la parametrización

Cada zona tiene su propio calendario de días hábiles, porque no todos los
puntos abren los mismos días.

| Zona | Puntos de venta | Días hábiles (ago-2026, del Excel) |
|---|---|---|
| BUCARAMANGA Y CENTRO | BUCARAMANGA, CENTRO | 27.5 |
| CARTAGENA | CARTAGENA | 24 |
| PEREIRA | PEREIRA | 27.5 |
| LA 70 / LA 43 / SIMON / LA GRANJA | LA70, LA43, SIMON, LAGRANJA | 28.5 |
| *(resto — pendiente de confirmar con el usuario)* | MALAMBO, CONCORDE, SANFELIPE, OLAYA, LA93, ALAMEDA, ALAMEDA2 | por definir |

**Los días hábiles admiten media jornada** (27.5, 28.5): un domingo o festivo
que abre medio día cuenta 0.5. Por tanto `dias_habiles` es `Decimal`, no `int`.

Parámetros por zona y período:

- `dias_habiles` — total del mes. Lo fija el usuario.
- `dias_trabajados` — transcurridos al corte. Se calcula desde el calendario y
  la fecha de corte, y el usuario puede sobrescribirlo.
- `ideal = dias_trabajados / dias_habiles` — el porcentaje de cumplimiento que
  *debería* llevarse hoy. Es la vara contra la que se mide todo.

### 3.3 Presupuesto

Se parametriza por **(período, punto de venta, categoría)** con dos medidas:

- `monto` — presupuesto en pesos.
- `kilos` — presupuesto en kilos.

El presupuesto del PDV es la suma de sus categorías; el del grupo, la suma de
sus PDV. **Se calcula, no se captura por duplicado.**

Presupuesto **diario derivado**:

```
presupuesto_diario = presupuesto_mensual / dias_habiles(zona, periodo)
```

Requisitos:

- **Versionado.** Cada cambio de presupuesto queda con autor, fecha y motivo.
  Un presupuesto que cambia sin rastro no sirve para evaluar a nadie.
- **Carga masiva** desde Excel/CSV, porque hoy así lo arman.
- **Cierre de período**: un período cerrado no admite cambios de presupuesto.

### 3.4 Venta

Grano de almacenamiento: **detalle de transacción**, tal como lo entrega SIESA.
Los agregados se calculan sobre ese detalle; guardar solo el total impide el
análisis por cliente y por categoría que el negocio ya hace.

Campos que entrega SIESA hoy (hoja `VENTA`, 131 819 filas para 9 días):

| Campo SIESA | Tipo | Notas |
|---|---|---|
| `C.O.` | texto | Código de PDV. **Llega como texto con ceros a la izquierda y a veces como número** (`'606'` y `606` conviven). Normalizar a texto de 3 posiciones. |
| `Desc. C.O.` | texto | Descriptivo, no es llave. |
| `Fecha` | fecha | Día de la venta. |
| `Cliente POS` / `Cliente factura` | texto | NIT. **Llega con espacios de relleno a la derecha.** Hacer `strip()`. |
| `Razón social cliente POS` / `... factura` | texto | |
| `Costo promedio` | decimal | Costo de la línea. |
| `Cantidad inv.` | decimal | **Kilos.** Admite decimales (370.83). |
| `Valor subtotal` | decimal | **Venta.** Es la medida contra presupuesto. |
| `MARGEN` | decimal | Porcentaje que envía SIESA. Ver §4.4. |
| `Domicilio` | texto | `Si` / `No`. |
| `CLASES DE CLIENTES` | texto | **Columna sucia.** Ver aviso abajo. |
| `Condición de pago` | texto | `CON` (contado, 97 %), `15D`, `30D`, `03D`, `08D`, `01D`, `60D`, `A`. |
| `CATEGORIA` | texto | Categoría cruda de SIESA. |
| `NUEVA CATEGORIA` | texto | Reclasificación manual. En SIGREP la produce la tabla de mapeo. |

> **Aviso de calidad de dato.** `CLASES DE CLIENTES` viene corrupta en el
> archivo actual: 95 907 filas vacías y valores que no son clases de cliente
> (`johana.muñoz`, marcas de tiempo como `2026-08-03 16:29:02`). La ingesta
> debe aceptar únicamente valores del catálogo (`001 - EMPLEADOS`,
> `002 - CLIENTES NACIONALES`, `CONSUMIDOR FINAL PDV ...`) y registrar el resto
> como `SIN CLASIFICAR` dejando constancia en la bitácora de ingesta.
> Igual criterio para `Domicilio`: hay 28 filas en blanco.

Catálogo de clientes (hoja `CLIENTES`, 451 registros): NIT, razón social,
**canal** (`HORECA`) y **vendedor asignado**. Esto habilita el reporte por
vendedor, que hoy no existe en el Excel y el negocio claramente quiere.

---

## 4. Los indicadores

Cada indicador se implementa en el dominio, con prueba unitaria, y la interfaz
**muestra la fórmula y los parámetros usados**. Nada de números sin origen.

Sea, para un corte `(período, agrupación)`:

| Símbolo | Significado |
|---|---|
| `P` | Presupuesto del mes |
| `V` | Venta acumulada del mes al corte |
| `H` | Días hábiles del mes (zona) |
| `T` | Días trabajados al corte (zona) |

### 4.1 Cumplimiento

```
cumplimiento = V / P
ideal        = T / H
brecha       = cumplimiento − ideal
```

`brecha ≥ 0` es verde. Los umbrales del semáforo son parámetro del sistema, no
constantes en el código. Propuesta inicial, a confirmar con el usuario:

| Estado | Condición |
|---|---|
| Verde | `cumplimiento ≥ ideal` |
| Amarillo | `ideal × 0.90 ≤ cumplimiento < ideal` |
| Rojo | `cumplimiento < ideal × 0.90` |

### 4.2 Venta diaria y proyección

```
venta_diaria_promedio = V / T
proyeccion            = venta_diaria_promedio × H
cumplimiento_proyectado = proyeccion / P
```

**Venta diaria requerida** — lo que hay que vender cada día que queda para
llegar al presupuesto. Es el número accionable del reporte y hoy el Excel no lo
tiene bien:

```
venta_diaria_requerida = (P − V) / (H − T)      si H > T
                       = 0                       si V ≥ P
                       = indefinido (mostrar «—») si H = T
```

> **Hallazgo del Excel actual.** Las columnas `PROYECCION` y `VENTA DIARIA` del
> libro vigente no son consistentes: para MALAMBO, `proyeccion / venta_diaria`
> da 33.06, y en la hoja de julio da 38.1, cuando los días hábiles declarados
> son 24–28.5. Los divisores están desalineados entre hojas y hay valores
> arrastrados de un mes al anterior (la venta de julio de MALAMBO es idéntica a
> la de agosto). **No replicar esas fórmulas.** SIGREP define las de arriba,
> explícitas y probadas, y muestra `H` y `T` junto al resultado para que
> cualquiera pueda verificar el cálculo a mano.

### 4.3 Crecimiento contra el año anterior

```
crecimiento = V_actual / V_año_anterior − 1
```

Requiere historia. La ingesta debe poder cargar períodos pasados; sin 2025
cargado, el indicador se muestra vacío, nunca en cero.

### 4.4 Margen

```
margen_valor      = Σ valor_subtotal − Σ costo_promedio
margen_porcentaje = margen_valor / Σ valor_subtotal
```

Se calcula **ponderado sobre los totales**, nunca promediando el porcentaje
`MARGEN` que envía SIESA línea a línea: promediar porcentajes de líneas de
distinto tamaño da un número falso. El campo `MARGEN` de SIESA se conserva solo
para conciliación.

### 4.5 Kilos

Los mismos indicadores de §4.1 y §4.2 con `Cantidad inv.` contra `PPTO EN KILO`.
El negocio mide en pesos **y** en kilos; un mes puede cumplir en pesos por
precio y fallar en kilos por volumen, y esa diferencia es justamente lo que la
gerencia necesita ver.

### 4.6 Comisión

El Excel tiene una columna `COMISION` diligenciada solo para algunos PDV
(MALAMBO 2 150 000). **Regla de cálculo pendiente de definir con el usuario.**
Modelar el campo, no inventar la fórmula.

---

## 5. Integración con SIESA

**La API de SIESA todavía no se ha entregado.** El usuario la pasará.

Diseñar contra un **puerto** (interfaz), no contra la API concreta:

```python
class FuenteVenta(Protocol):
    def obtener_ventas(
        self, desde: date, hasta: date, centros: Sequence[str] | None = None
    ) -> Iterable[LineaVenta]: ...
```

Implementaciones:

1. `FuenteVentaExcel` — lee el libro actual. **Es la que se construye ahora** y
   permite tener el sistema funcionando y validado contra el Excel antes de que
   llegue la API.
2. `FuenteVentaSiesa` — se implementa cuando llegue la especificación. Cambiar
   de una a otra debe ser una variable de entorno, no un refactor.

La ingesta es **idempotente**: reprocesar un día reemplaza ese día completo, no
duplica. Cada corrida deja registro de filas leídas, aceptadas, rechazadas y el
motivo de cada rechazo.

---

## 6. Las pantallas

| Pantalla | Contenido |
|---|---|
| **Tablero gerencial** | Consolidado compañía: cumplimiento, ideal, proyección, semáforo. Comparativo de los 4 grupos. Es la pantalla de la gerencia. |
| **Cumplimiento por PDV** | La tabla del Excel, viva: PPTO, venta, %, proyección, %, venta diaria, venta diaria requerida, año anterior, crecimiento, margen — en pesos y en kilos. Expandible a categorías. |
| **Venta diaria** | Detalle día por día del mes por PDV (equivale a `Hoja1`), con el presupuesto diario derivado como línea de referencia. |
| **Parametrización de presupuesto** | Captura y carga masiva por período, PDV y categoría. Historial de cambios. |
| **Calendario de días hábiles** | Días hábiles y trabajados por zona y período. Admite medias jornadas. |
| **Clientes y vendedores** | Venta por canal, cliente y vendedor. Cruce con el catálogo de clientes. |
| **Ingesta** | Estado de la última carga desde SIESA, filas rechazadas y su motivo. |

Todas las pantallas: filtro de período, grupo, PDV y categoría; exportación a
Excel; y **la fecha de corte visible siempre**, porque un reporte sin fecha de
corte es un reporte que alguien va a malinterpretar.

---

## 7. Reglas que el sistema hace cumplir

- Un período cerrado no admite cambios de presupuesto.
- La venta de un PDV sin presupuesto se reporta aparte; nunca se descarta.
- Reprocesar una fecha reemplaza el día completo; no duplica.
- Todo cambio de presupuesto queda con autor, fecha y motivo.
- Los porcentajes nunca se promedian: se recalculan sobre los totales.
- Una división por cero se muestra como «—», nunca como 0 ni como error.
- Los importes son `Decimal` de extremo a extremo.

---

## 8. Preguntas abiertas para el usuario

Trabajar bajo el supuesto indicado y **marcarlas visiblemente** en la entrega:

1. **Días hábiles de las zonas faltantes** (MALAMBO, CONCORDE, SANFELIPE,
   OLAYA, LA93, ALAMEDA, ALAMEDA2). *Supuesto: se parametrizan en pantalla; se
   siembra 28 como valor inicial.*
2. **Regla de comisión** (§4.6). *Supuesto: campo modelado, cálculo pendiente.*
3. **Umbrales del semáforo** (§4.1). *Supuesto: 90 % del ideal.*
4. **Roles y permisos**: ¿quién parametriza presupuesto y quién solo consulta?
   *Supuesto: GERENTE (todo), ANALISTA (parametriza), JEFE_PDV (consulta su
   propio PDV).*
5. **Historia 2025** para el indicador de crecimiento: ¿de dónde se carga?
   *Supuesto: se cargará por la misma ingesta cuando esté disponible la API.*
6. **API de SIESA**: pendiente de entrega.
