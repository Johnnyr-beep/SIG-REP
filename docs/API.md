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

GET /reportes/venta-diaria?periodo=2026-08
    -> { fechas: ["2026-08-01", ...],
         presupuesto_diario_por_pdv: {"405": "..."},
         filas: [ {punto_venta, valores: ["50200928.00", ...], total: "..."} ] }

GET /reportes/clientes?periodo=2026-08&por=cliente|vendedor|canal|condicion_pago
    -> { filas: [ {clave, nombre, venta, kilos, margen_porcentaje, participacion} ] }

GET /reportes/{cualquiera}/exportar?...   -> .xlsx (mismos filtros)
```

`semaforo`: `VERDE` | `AMARILLO` | `ROJO` | `SIN_PRESUPUESTO`.

Toda respuesta de reporte incluye `parametros_calculo` con `dias_habiles`,
`dias_trabajados`, `fecha_corte` y `umbrales` — para que la pantalla pueda
mostrar de dónde sale cada número (§4.2 de la especificación).

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
       -> [{cuando, quien, sobre_quien, accion, detalle}]
```

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

## Salud

```
GET    /salud     -> {estado: "operativo"|"degradado",
                      version, base_datos: "disponible"|"no disponible",
                      ultima_ingesta}
```

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
