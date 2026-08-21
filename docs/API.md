# Contrato de API — SIGREP v1

Base: `/api/v1`. Autenticación JWT `Bearer`, igual que GSC ONE.
Este archivo es **vinculante** para backend y frontend. Ningún lado cambia un
nombre de campo sin actualizarlo aquí primero.

## Convenciones

- Fechas: `YYYY-MM-DD`. Períodos: `YYYY-MM`.
- **Los importes y cantidades viajan como `string`**, no como `number`:
  `"3278067652.00"`. `Decimal` no sobrevive a un `float` de JavaScript y estos
  son montos de mil millones. El frontend formatea; nunca opera aritmética
  sobre ellos.
- Los porcentajes viajan como fracción decimal en `string`: `"0.2885"` = 28.85 %.
- Un indicador indefinido (división por cero, sin dato) viaja como `null` y se
  pinta «—». Nunca `0`.
- Errores: `{ "detalle": "...", "codigo": "..." }` con el manejador de
  `core/errors.py` portado de GSC ONE.

## Autenticación

```
POST   /auth/acceso            {usuario, clave} -> {token_acceso, token_refresco, tipo}
POST   /auth/refrescar         {token_refresco} -> {token_acceso}
GET    /auth/yo                -> {id, usuario, nombre, rol, puntos_venta[]}
```

Roles: `ADMIN`, `GERENTE`, `ANALISTA`, `JEFE_PDV`, `CONSULTA`.

`ADMIN` es superusuario del negocio **y** el unico que administra cuentas; los
otros cuatro no entran en `/usuarios`. Ver la seccion Usuarios.

## Catálogos

```
GET    /catalogos/grupos                 -> [{id, codigo, nombre}]
GET    /catalogos/puntos-venta           -> [{id, codigo_co, nombre, grupo, zona, activo, presupuestado}]
GET    /catalogos/categorias             -> [{id, codigo, nombre, orden}]
GET    /catalogos/zonas                  -> [{id, nombre, puntos_venta[]}]
GET    /catalogos/mapeo-categorias       -> [{texto_siesa, categoria}]
POST   /catalogos/mapeo-categorias       (ANALISTA) crear/actualizar mapeo
```

## Calendario de días hábiles

```
GET    /calendario?periodo=2026-08
       -> [{zona, dias_habiles, dias_trabajados, ideal, fecha_corte}]
PUT    /calendario/{zona_id}?periodo=2026-08
       (ANALISTA) {dias_habiles, dias_trabajados?}   dias_trabajados null = derivado
```

`dias_habiles` y `dias_trabajados` son decimales con un decimal (`"27.5"`).

## Presupuesto

```
GET    /presupuesto?periodo=2026-08&punto_venta=405
       -> [{punto_venta, categoria, monto, kilos, actualizado_en, actualizado_por}]
PUT    /presupuesto  (ANALISTA)
       {periodo, punto_venta_id, categoria_id, monto, kilos, motivo}
POST   /presupuesto/carga-masiva  (ANALISTA)  multipart .xlsx/.csv
       -> {aceptadas, rechazadas, errores:[{fila, motivo}]}
GET    /presupuesto/historial?periodo=&punto_venta=
       -> [{cuando, quien, campo, valor_anterior, valor_nuevo, motivo}]
POST   /periodos/{periodo}/cerrar    (GERENTE)
GET    /periodos                     -> [{periodo, cerrado, cerrado_por, cerrado_en}]
```

## Reportes — el núcleo

Todos aceptan los mismos filtros:
`periodo` (obligatorio), `hasta` (fecha de corte, por defecto hoy),
`grupo`, `punto_venta`, `categoria`, `medida` = `valor` | `kilos`.

### `punto_venta` admite varios códigos

`?punto_venta=402,405,603` — códigos C.O. separados por coma. Vale en los
**cuatro** reportes (tablero, cumplimiento, venta diaria y clientes) y en
`/exportar`: es el mismo control de la misma barra de filtros, y sería raro que
se comportara distinto según la pantalla.

- **Un solo código y la ausencia se comportan exactamente como antes.**
  `?punto_venta=405` es la lista de uno. `?punto_venta=` y `?punto_venta=,,`
  equivalen a no enviar el filtro: una barra que se vacía no pide el punto de
  código «».
- Los espacios se recortan y los repetidos se descartan: `402,402` es `402`.
- Un código que no existe sencillamente no casa con ninguna fila. No es un
  validador de catálogo y no devuelve 404 por eso.
- **Estrecha, jamás ensancha.** El filtro se cruza con el alcance del usuario
  con `AND`. Un `JEFE_PDV` con alcance sobre 402 que pida `402,405,413` recibe
  **solo 402**; si pide `405,413`, recibe la respuesta vacía —consolidado en
  cero, sin filas—, nunca la compañía entera. Pedir puntos ajenos no es una
  forma de pedir permiso.

```
GET /reportes/tablero?periodo=2026-08
```
```json
{
  "periodo": "2026-08",
  "fecha_corte": "2026-08-09",
  "medida": "valor",
  "consolidado": {
    "presupuesto": "20000000000.00",
    "venta": "5396105548.00",
    "cumplimiento": "0.2698",
    "ideal": "0.2727",
    "brecha": "-0.0029",
    "semaforo": "AMARILLO",
    "proyeccion": "19787053234.00",
    "cumplimiento_proyectado": "0.9893",
    "venta_diaria_promedio": "599567283.00",
    "venta_diaria_requerida": "730494972.00",
    "venta_anio_anterior": "4200000000.00",
    "crecimiento": "0.2848",
    "margen_valor": "1830000000.00",
    "margen_porcentaje": "0.3391",
    "dias_habiles": "27.5",
    "dias_trabajados": "7.5"
  },
  "grupos": [ { "codigo": "001", "nombre": "GRUPO 1", ...mismos campos } ],
  "sin_presupuesto": [ { "codigo_co": "432", "nombre": "EVENTOS BUCARAMANGA", "venta": "..." } ]
}
```

El bloque de indicadores de `consolidado` se llama **`FilaIndicadores`** y se
repite idéntico en todos los niveles. Backend: un solo esquema Pydantic.
Frontend: un solo tipo y un solo componente de fila.

```
GET /reportes/cumplimiento?periodo=2026-08[&grupo=001]
    -> { fecha_corte, medida, filas: [ {punto_venta, ...FilaIndicadores,
                                        categorias: [ {categoria, ...FilaIndicadores} ]} ] }

GET /reportes/venta-diaria?periodo=2026-08[&desde=2026-07-25&hasta=2026-08-05]
    -> ver el bloque «Venta diaria» más abajo

GET /reportes/clientes?periodo=2026-08&por=cliente|vendedor|canal|condicion_pago
    -> { filas: [ {clave, nombre, venta, kilos, margen_porcentaje, participacion} ] }

GET /reportes/{cualquiera}/exportar?...   -> .xlsx (mismos filtros)
```

`semaforo`: `VERDE` | `AMARILLO` | `ROJO` | `SIN_PRESUPUESTO`.

Toda respuesta de reporte incluye `parametros_calculo` con `dias_habiles`,
`dias_trabajados`, `fecha_corte` y `umbrales` — para que la pantalla pueda
mostrar de dónde sale cada número (§4.2 de la especificación).

### Venta diaria

```
GET /reportes/venta-diaria?periodo=2026-08
GET /reportes/venta-diaria?periodo=2026-08&desde=2026-07-25&hasta=2026-08-05
```

```json
{
  "periodo": "2026-08",
  "fecha_corte": "2026-08-05",
  "desde": "2026-07-25",
  "hasta": "2026-08-05",
  "medida": "valor",
  "periodos": ["2026-07", "2026-08"],
  "fechas": ["2026-07-25", "...", "2026-08-05"],
  "presupuesto_diario_por_pdv": { "405": "60000.00" },
  "presupuesto_diario_por_periodo": {
    "2026-07": { "405": "40000.00" },
    "2026-08": { "405": "60000.00" }
  },
  "filas": [
    { "punto_venta": "405", "nombre": "LA43",
      "valores": ["50200928.00", null, "..."], "total": "..." }
  ],
  "totales": {
    "valores": ["50200928.00", null, "..."],
    "total": "...",
    "presupuesto_diario": "60000.00",
    "presupuesto_diario_por_periodo": { "2026-07": "40000.00", "2026-08": "60000.00" }
  },
  "parametros_calculo": { "...": "..." }
}
```

#### La fila de totales

`totales` es la suma, día a día, de **las filas que la respuesta publica**, más
su total del período o del rango. Va en un **campo propio** y no como una fila
más de `filas`, a propósito: mezclada, la pantalla tendría que reconocerla por
su nombre (`punto_venta == "TOTAL"`) y esa convención se rompe el día que
alguien bautice así un punto de venta.

- Respeta el filtro: si se piden tres puntos, el total es el de esos tres.
- Respeta el alcance: un `JEFE_PDV` recibe el total de sus puntos.
- `valores[i]` es `null` en un día sin venta registrada en **ningún** punto —lo
  mismo que en las filas—, que no es lo mismo que un día que sumó cero.
- `presupuesto_diario` es `Σ (P_i / H_i)`: la suma de las líneas de referencia
  de las filas, **no** el presupuesto agregado partido por unos días
  ponderados. Cada punto tiene el calendario de su zona y la venta diaria
  esperada de la compañía es la suma de las de sus puntos; con cualquier otra
  fórmula la fila de totales no cuadraría con las que tiene encima.
  Es `null` si ningún punto tiene presupuesto parametrizado, y también si
  alguno lo tiene y su zona no tiene días hábiles: ahí el término es
  incalculable y sumar solo el resto publicaría una referencia más baja que la
  real con pinta de completa (§7).

#### El rango `desde` / `hasta`

Sin `desde` no cambia nada: manda `periodo`, las columnas van del día 1 a la
fecha de corte y `hasta` sigue siendo esa fecha de corte. Es el modo de
siempre.

Con `desde`, `hasta` pasa a ser el **último día del rango** y se toma tal cual,
sin recortarlo contra el mes de `periodo` —recortarlo cortaría en seco el rango
que cruza de mes, que es justo lo que esto viene a resolver—. Sin `hasta`, el
rango se cierra en hoy.

`desde`, `hasta`, `fechas` y `periodos` viajan **en los dos modos**, de manera
que la respuesta es autodescriptiva y la pantalla no necesita saber cuál se
usó. `fecha_corte` coincide siempre con `hasta`.

**El presupuesto es mensual (§3.3), y el rango puede no serlo.** Un rango del
25 de julio al 5 de agosto tiene **dos** líneas de referencia distintas y las
dos son correctas:

- `presupuesto_diario_por_periodo` trae una por período tocado. La referencia
  de un día sale de la entrada de **su propio mes**: un día de julio no se mide
  contra el presupuesto de agosto. El código de período de una fecha es su
  prefijo `YYYY-MM`, así que la pantalla no necesita nada más para cruzarlos.
- `presupuesto_diario_por_pdv` es la referencia del **período de la petición**
  y equivale siempre a `presupuesto_diario_por_periodo[periodo]`. Con el rango
  dentro de un solo mes —el caso normal— hay una única entrada y los dos
  campos dicen lo mismo.
- Un período que el rango toca y que **no está abierto** en el sistema publica
  sus referencias en `null`: sin período no hay presupuesto ni calendario, y un
  cero cómodo sería inventarlos. Sus columnas salen vacías, que es lo correcto:
  tampoco puede haber venta ingerida.

`periodo` sigue siendo obligatorio y es el **período de referencia**: de él
salen `parametros_calculo` y `presupuesto_diario_por_pdv`. Envíe como `periodo`
el mes al que pertenece `hasta`.

#### Los dos rechazos del rango

| Situación | HTTP | `codigo` |
|---|---|---|
| `desde` posterior a `hasta` | 422 | `rango_invertido` |
| más de **92 días** entre `desde` y `hasta` | 422 | `rango_excesivo` |

El rango invertido **se rechaza**; no devuelve la tabla vacía que saldría de
forma natural, porque eso haría pasar un error de captura por «no hubo ventas».

El tope son **92 días, un trimestre**, y el límite es inclusivo: 92 entran, 93
no. El reporte pinta un día por columna —31 ya llenan una pantalla y un año son
366—, así que el tope está donde deja de tener sentido dibujarlo, no donde deja
de poder calcularse. Un trimestre cubre el mes en curso más los dos anteriores,
que es el corte que el negocio pide de verdad. Para horizontes mayores están el
tablero y el cumplimiento, que agregan por período en lugar de por día.

El error dice el tope y los días pedidos, para no tener que adivinarlo a base
de reintentos:

```json
{
  "detalle": "El rango pedido son 365 días y el máximo del reporte de venta diaria es 92. ...",
  "codigo": "rango_excesivo",
  "detalles": { "dias_solicitados": 365, "maximo_dias": 92 }
}
```

## Ingesta

```
POST   /ingesta/ejecutar   (ANALISTA) {desde, hasta, fuente: "siesa"|"excel"}
POST   /ingesta/archivo    (ANALISTA) multipart .xlsx
GET    /ingesta/corridas   -> [{id, cuando, quien, fuente, desde, hasta, estado,
                                filas_leidas, aceptadas, rechazadas, duracion_ms}]
GET    /ingesta/corridas/{id}/rechazos -> [{fila, campo, valor, motivo}]
```

## Usuarios · administracion de cuentas

Solo el rol `ADMIN`. Los otros cuatro reciben 403 en todo este bloque, `GERENTE`
incluido: ve todas las cifras de la compania y no reparte accesos.

`ADMIN` es ademas **superusuario del negocio** — entra en reportes, presupuesto,
calendario e ingesta como `GERENTE`. Decision del 18-ago-2026: Sistemas necesita
diagnosticar por si mismo si un reporte muestra bien los datos, sin pedir
prestada una cuenta de gerencia.

```
GET    /usuarios[?rol=&activo=]
       -> [{id, usuario, nombre, email, rol, activo, debe_cambiar_password,
            bloqueado, ultimo_acceso, creado_en, puntos_venta[]}]

POST   /usuarios                    {usuario, nombre, email?, rol, puntos_venta[]}
       -> 201 {usuario: {...}, clave_provisional}

PATCH  /usuarios/{id}               {nombre?, email?, rol?}
PUT    /usuarios/{id}/puntos-venta  {puntos_venta: ["402", ...]}   REEMPLAZA la lista
POST   /usuarios/{id}/activar
POST   /usuarios/{id}/desactivar
POST   /usuarios/{id}/restablecer-clave  -> {id, usuario, clave_provisional}

GET    /usuarios/auditoria[?usuario_id=&limite=]
       -> [{cuando, accion, usuario, actor,
            campo, valor_anterior, valor_nuevo, ip_origen}]
```

En la auditoria, `usuario` es **la cuenta administrada** y `actor` **quien
ejecuto la operacion**. Se nombran asi y no `quien`/`sobre_quien` —como decia
una version anterior de este archivo— porque es lo que devuelve el backend; la
divergencia la detecto el frontend al tipar la tabla y dejarla en blanco.
`campo`, `valor_anterior` y `valor_nuevo` recomponen el cambio concreto
(«rol: GERENTE -> ANALISTA»); van vacios en las acciones que no modifican un
campo, como activar o restablecer la clave.

### Las seis reglas, y por que existen

1. **Nadie se administra a si mismo** — 403 `sin_autoadministracion`. Un `ADMIN`
   no cambia su rol, no se desactiva y no se amplia el alcance. Sin esto el rol
   es decorativo: cualquiera se otorga lo que quiera.
2. **Siempre queda un `ADMIN` activo** — 409 `ultimo_admin_activo` al desactivar
   o degradar al ultimo. Es la proteccion contra quedarse fuera del sistema sin
   ninguna cuenta capaz de volver a crear administradores.
3. **No hay borrado, hay baja.** Las acciones de un usuario estan referenciadas
   en `presupuesto_historial` y en `corridas_ingesta`; borrarlo destruiria el
   rastro que §3.3 existe para conservar.
4. **Toda operacion queda registrada** con quien, sobre quien, que y cuando.
   Un permiso concedido sin rastro no se puede auditar.
5. **La clave provisional se muestra una sola vez.** La genera el servidor, se
   guarda solo como hash Argon2id, no vuelve a aparecer en ninguna respuesta ni
   en ningun log, y obliga a cambiarla en el siguiente acceso. Si se pierde
   antes de entregarla, el remedio es `restablecer-clave`.
6. **Ninguna respuesta devuelve el hash**, ni siquiera al `ADMIN`.

`PUT /usuarios/{id}/puntos-venta` **reemplaza** el alcance completo: lo que se
envia es lo que queda. Asignar es mandar la lista con el codigo de mas; quitar,
con el codigo de menos; y `[]` deja al usuario sin ninguno. Sin reemplazo, quitar
un punto seria imposible.

## Agropecuaria — `/agro`

La unidad agropecuaria (compañía 3) tiene su propio bloque y no es una variante
de los reportes de arriba: mide otras dimensiones —centro de operación, especie,
tipo comercial, tipo de ítem, grupo, vendedor, cliente y producto— y presupuesta
de otra forma. Las convenciones generales (§ Convenciones) se aplican tal cual y
no se repiten aquí.

Todos los reportes aceptan los mismos filtros:
`periodo` (obligatorio), `hasta` (fecha de corte, por defecto hoy), `desde`,
`centro` (varios códigos separados por coma) y `medida` = `valor` | `kilos`.

`centro` se comporta como `punto_venta` en carnes: **estrecha, jamás ensancha**,
y vacío equivale a no filtrar —una barra que se limpia no pide el centro de
código vacío—.

### Cuatro cosas que hay que entender antes de consumirlo

**1. El presupuesto no tiene un total global, y es deliberado.** Las cuatro
dimensiones presupuestables —`vendedor`, `centro_operacion`, `especie`,
`tipo_comercial`— son **cuatro repartos del mismo dinero**, no cuatro metas.
Sumar dos daría el doble de la meta; sumar las cuatro, el cuádruple. Una
pantalla que necesite el presupuesto de la compañía **elige una dimensión**, que
es justo la operación correcta. Por eso `GET /agro/presupuesto` devuelve una
entrada por dimensión, cada una con **su** total, y no existe ningún campo por
encima que las agregue.

Cuando los cuatro repartos no coinciden, hay un error de captura, y eso es lo
que publica `GET /agro/presupuesto/cuadre`. **El sistema no lo corrige**:
repartir la diferencia sería inventarse la meta de alguien. La publica —ahí y
dentro de `parametros_calculo` de *todos* los reportes— y quien la capturó la
arregla. Va en todos los reportes porque un descuadre invalida la lectura de
cualquiera de ellos, y quien mire un cumplimiento tiene derecho a saberlo sin ir
a buscarlo a otra pantalla.

**2. `lineas_facturadas` son líneas, no documentos ni tiquetes.** Una venta de
ocho productos son ocho líneas y **un** documento, y la fuente no entrega el
documento. El nombre es literal: no se aproxima y no se renombra. Ver
`INTEGRACION-SIESA §4.4`.

**3. `TipoItem = IMPUESTO` se ingiere, se guarda marcado y se excluye de todo.**
De todo total, de todo porcentaje y de toda comparación contra presupuesto: no
es venta, es recaudo a nombre de terceros. Se guarda —no se descarta— para poder
conciliar con el origen, y lo que se excluyó se publica en `conciliacion` de
cada reporte. Sumado a la venta publicada da el total bruto del origen.

**4. Los indicadores que dependen del presupuesto viajan vacíos en los ejes que
no se presupuestan** —`cliente`, `grupo` y `tipo_item`—. Eso es información, no
un hueco por cargar: dice que ahí no hay meta contra la que medir.

### Reportes

```
GET    /agro/resumen?por=<eje>&periodo=&hasta=&desde=&centro=&medida=
       -> {periodo, fecha_corte, medida, por,
           consolidado: <indicadores>,
           filas: [{clave, nombre, ...<indicadores>}],
           parametros_calculo}

GET    /agro/cruce?por=<cruce>&...
       -> {..., ejes: ["vendedor","cliente"],
           consolidado, filas: [{claves:[], nombres:[], ...<indicadores>}],
           truncado, limite, parametros_calculo}

GET    /agro/venta-diaria?periodo=&desde=&hasta=&centro=&medida=
       -> {..., desde, hasta, fechas: [],
           presupuesto_diario_por_centro: {"301": "…"|null},
           filas: [{centro, nombre, valores:[], total}],
           totales: {valores:[], total, presupuesto_diario},
           parametros_calculo}

GET    /agro/exportar/{resumen|cruce|venta-diaria}?por=<eje>&<mismos filtros>
       -> libro .xlsx  (RBAC: cualquier rol autenticado)
```

El reporte va **al final** de la ruta de exportación —`/agro/exportar/resumen`,
no `/agro/{reporte}/exportar`— porque un comodín en la primera posición también
capturaría `/agro/presupuesto/cuadre` y `/agro/ingesta/corridas`, que existen. Un
`por` que no pertenezca al enumerado del reporte pedido es **404 con su motivo**,
no 500.

El bloque `<indicadores>` es el mismo en los siete ejes, en los dos cruces y en
el consolidado:

| Campo | Qué es |
|---|---|
| `venta` | La venta en la medida del reporte (pesos o kilos). |
| `venta_valor` | La venta **siempre en pesos**, aunque se mire en kilos: el margen y la participación son conceptos monetarios. |
| `kilos`, `cantidad` | Magnitudes físicas. |
| `lineas_facturadas` | `int`. Líneas, no documentos (ver arriba). |
| `participacion` | Fracción de la venta total del corte. Recalculada sobre totales, nunca promediada. |
| `margen_valor`, `margen_porcentaje` | `null` si alguna línea no tiene costo. **Puede ser negativo**: la venta a otra compañía del grupo sale así. |
| `presupuesto`, `cumplimiento`, `ideal`, `brecha`, `semaforo`, `proyeccion`, `cumplimiento_proyectado`, `venta_diaria_promedio`, `venta_diaria_requerida`, `dias_habiles`, `dias_trabajados` | Vacíos en los ejes sin meta. `semaforo` viaja como `SIN_PRESUPUESTO`. |

`parametros_calculo` acompaña a **todo** reporte —un número sin origen es el
problema que este proyecto viene a resolver— y trae `fecha_corte`,
`dias_habiles`, `dias_trabajados`, `umbrales`, `dimension_presupuesto`,
`formulas`, `cuadre` y `conciliacion`:

```
conciliacion: {impuesto_valor, impuesto_kilos, impuesto_lineas, nota}
```

**`impuesto_lineas` es `SUM(LineasFacturadas)`, no un conteo de filas**, y por
eso no tiene por qué coincidir con el campo `impuesto` de una corrida de
ingesta, que sí cuenta filas del origen. En la primera carga real fueron **170
filas y 180 líneas**. Se dice aquí porque los dos números se leen juntos al
conciliar contra el ERP, y sin esta nota la diferencia parece diez filas
perdidas.

#### Los cruces cuadran con el total; las filas publicadas, no

La suma de las filas de un cruce es exactamente la venta del corte, porque las
tres dimensiones son obligatorias en la línea: lo que llega sin vendedor, sin
cliente o sin producto entra con su miembro visible —`SIN VENDEDOR`,
`SIN CLIENTE`, `SIN PRODUCTO`— y sigue sumando. Un cruce que descartara los
nulos publicaría menos venta que el resumen y nadie sabría por qué.

Otra cosa es lo que se **publica**. `truncado: true` avisa de que la respuesta
trae solo las primeras `limite` filas por venta. **El consolidado no se trunca**:
es el total del corte entero, para que la participación siga siendo cierta. Por
tanto, con `truncado: true` la suma de la columna de venta **es menor** que el
consolidado, y la diferencia es exactamente la venta de las filas que no
viajaron. En una carga real de siete días, el cruce de tres ejes dejó 198
millones fuera de las 500 filas publicadas: no es una nota al pie.

#### La fila de totales de la venta diaria

Viaja en `totales`, en un campo propio y **no** como una fila más. Mezclada
entre las filas, el consumidor tendría que reconocerla por su nombre, y esa
convención se rompe el día que alguien bautice así un centro.

`totales.presupuesto_diario` es `Σ (Pᵢ / Hᵢ)` sobre los centros —la suma de las
líneas de referencia—, no el presupuesto agregado partido por unos días
ponderados. Es `null` si ningún centro tiene presupuesto, y **también** si alguno
lo tiene y no tiene días hábiles: ahí el término es incalculable, y sumar solo el
resto publicaría una referencia más baja que la real con pinta de completa.

### Presupuesto

```
GET    /agro/presupuesto?periodo=2026-08[&dimension=<dim>]
       -> [{dimension, etiqueta, definido, total_monto, total_kilos,
            filas: [{dimension, clave, nombre, monto, kilos}]}]
PUT    /agro/presupuesto  (ANALISTA)
       {periodo, dimension, clave, etiqueta?, monto, kilos, motivo}
GET    /agro/presupuesto/cuadre?periodo=2026-08
       -> {periodo, cuadra, diferencia_monto, diferencia_kilos, mensaje,
           dimensiones: [{dimension, etiqueta, total_monto, total_kilos}]}
POST   /agro/presupuesto/carga-masiva  (ANALISTA)  multipart .xlsx/.xlsm/.csv
       -> {aceptadas, rechazadas, errores:[{fila, motivo}], cuadre}
GET    /agro/presupuesto/historial?periodo=&dimension=
       -> [{cuando, quien, dimension, clave, campo,
            valor_anterior, valor_nuevo, motivo}]
```

`dimension` es **obligatoria** en el `PUT` y está tipada: sin ella no se sabe en
cuál de los cuatro repartos va la cifra, y ponerla en el que no es descuadra los
dos. El archivo de la carga masiva trae una columna `dimension` **por fila**: las
cuatro en una sola carga. El `cuadre` viaja en la respuesta de la carga a
propósito —el momento de ver que las cuatro descomposiciones no dan lo mismo es
justo después de subirlas, cuando quien lo hizo todavía tiene el archivo
abierto—.

`motivo` es obligatorio y de 5 a 400 caracteres: todo cambio de presupuesto queda
con autor, fecha y motivo (§7), y «ajuste» no sirve para evaluar a nadie seis
meses después.

`definido: false` significa que **nadie ha capturado nada** en esa dimensión. No
es lo mismo que un presupuesto de cero: aquel es una afirmación del negocio y
este es la ausencia de la parametrización.

### Calendario

```
GET    /agro/calendario?periodo=2026-08[&hasta=]
       -> [{centro, nombre, dias_habiles, dias_trabajados, ideal,
            fecha_corte, derivado}]
PUT    /agro/calendario/{codigo_centro}?periodo=2026-08  (ANALISTA)
       {dias_habiles, dias_trabajados?}
```

La unidad de calendario de agropecuaria es el **centro de operación** —`301`
Planta y `302` Montería—, no una zona: son dos y pueden abrir días distintos.
**Los días admiten media jornada**, así que son decimales (`"27.5"`).

`dias_trabajados: null` significa **derivado** de la fecha de corte; `derivado`
dice cuál de los dos casos es. Un número escrito por un usuario es una afirmación
sobre la realidad —«ese sábado no abrimos»— y manda sobre lo que el sistema
calcularía solo.

### Ingesta

```
POST   /agro/ingesta/ejecutar?desde=&hasta=  (ANALISTA)
       -> {id, cuando, quien, fuente, desde, hasta, estado,
           filas_leidas, aceptadas, rechazadas, impuesto, duracion_ms}
GET    /agro/ingesta/corridas?limite=50
GET    /agro/ingesta/corridas/{id}/rechazos  (GERENTE)
       -> [{fila, campo, valor, motivo}]
```

**Los dos extremos del rango se incluyen**, y reprocesar un rango lo
**reemplaza**: no duplica. El campo `impuesto` cuenta filas que van **dentro** de
`aceptadas` —se guardan marcadas— y que no van a aparecer en ningún total; sin
ese número, conciliar la corrida contra el origen daría una diferencia sin
explicación.

Los rechazos exigen `GERENTE` y no es burocracia: llevan valores crudos de filas
reales de facturación.

### Enumerados

| Parámetro | Valores literales |
|---|---|
| `por` en `/agro/resumen` (`EjeResumen`) | `centro_operacion`, `tipo_item`, `especie`, `tipo_comercial`, `grupo`, `vendedor`, `cliente` |
| `por` en `/agro/cruce` (`EjeCruce`) | `vendedor-cliente`, `vendedor-cliente-producto` |
| `dimension` (`DimensionPresupuesto`) | `vendedor`, `centro_operacion`, `especie`, `tipo_comercial` |
| `medida` | `valor`, `kilos` |

El catálogo que devuelve la fuente, comprobado sobre una carga real: los
**cortes son un `tipo_comercial`**, no una especie; las especies son `RES` y
`CERDO`. `BIENES` y `SERVICIOS` son `tipo_item`, no `tipo_comercial`.

**En el eje `cliente`, `clave` y `nombre` son la misma cadena.** La fuente no
entrega NIT ni código de tercero —es la única dimensión sin identificador
propio—, así que la clave es el nombre. Un consumidor no debe pintar una columna
de código para ese eje. Está pedido a la API en `INTEGRACION-SIESA §4.5`.

---

## Salud

```
GET    /salud     -> {estado: "operativo"|"degradado",
                      unidad: "todas"|"carnes"|"agropecuaria"|"carnes-frias",
                      unidades: ["carnes","agropecuaria"],
                      version, base_datos: "disponible"|"no disponible",
                      ultima_ingesta}
```

**Es público a propósito**: el selector de unidad de negocio va *antes* del
acceso, así que tiene que poder preguntar qué marcas ofrecer sin sesión.

`unidad` es lo que sirve esta instancia. `todas` es el caso de hoy —carnes y
agropecuaria comparten base y despliegue, y el selector elige cuál se mira—;
fijada a una sola el día que alguna se lleve a su propio servidor.

`unidades` son las que se pueden mirar **de verdad**. El consumidor desactiva
las que no estén ahí en lugar de dejar entrar a unas pantallas sin datos
detrás: hoy le toca a `carnes-frias`, que es una marca sin módulo. Elegir una
marca no puede hacer aparecer una unidad que la instancia no sirve.

---

## Precisiones al contrato inicial

Aclaraciones incorporadas después de implementar ambos lados. El contrato de
arriba ya las refleja; se listan porque resolvieron ambigüedades que habían
hecho divergir al backend y al frontend.

1. **Las referencias de catálogo viajan planas, nunca anidadas.** En las filas de
   reporte, `punto_venta` es el **código C.O.** (`"402"`) y el nombre va en un
   campo hermano `nombre` (`"MALAMBO"`). Igual `categoria`, que es directamente
   el nombre de la categoría SIGREP (`"RES"`).

   ```json
   { "punto_venta": "402", "nombre": "MALAMBO", "categorias": [ { "categoria": "RES" } ] }
   ```

   Se eligió plano y no `{codigo, nombre}` por coherencia con
   `presupuesto_diario_por_pdv`, que ya venía indexado por código de C.O.
   Consecuencia práctica: la pantalla debe pintar `nombre`; pintar `punto_venta`
   deja la tabla llena de códigos.

2. `GET /reportes/cumplimiento` devuelve también `periodo` y `sin_presupuesto`,
   igual que el tablero.

3. `PuntoVentaSinPresupuesto` incluye `kilos` además de `venta`.

4. El historial de presupuesto devuelve `valor_anterior` y `valor_nuevo` con la
   escala de los kilos (3 decimales) para ambos campos, porque una sola columna
   sirve a `monto` y a `kilos` y así ningún valor pierde precisión al historiar.

5. **No hay número de documentos, y no lo va a haber mientras la fuente no lo
   entregue.** El negocio lo pidió para el reporte de venta diaria y la API de
   consulta no lo publica: ni `costos-razon-social` ni `ventas-razon-social`
   traen número ni conteo de documentos —los dos vienen ya agregados por
   centro, categoría, ítem y fecha, así que la identidad del documento se
   pierde antes de llegar—, y `venta_lineas` tampoco tiene esa columna.

   **No se aproxima contando líneas.** Una venta de ocho productos son ocho
   líneas y **un** documento; publicar ese conteo como «documentos» daría una
   cifra ocho veces mayor que la real en la pantalla de la gerencia. Está
   pedido al administrador de la API en `docs/INTEGRACION-SIESA.md` §4.4. Hasta
   entonces, la pantalla no debe reservar la columna ni pintarla vacía: no es
   un dato que falte cargar, es un dato que la fuente no da.
