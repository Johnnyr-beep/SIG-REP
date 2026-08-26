/**
 * Tipos del contrato de `/api/v1/agro` — la unidad Agropecuaria.
 *
 * Van en un archivo aparte de `tipos.ts` por la misma razón por la que el
 * backend tiene `schemas/agro.py` aparte de `schemas/reportes.py`: es otro
 * negocio. Carnes mide **punto de venta × categoría**; agropecuaria mide
 * vendedor, cliente, especie, tipo comercial y centro de operación. Meter las
 * dos en el mismo archivo obligaría a que un lector decidiera, campo a campo,
 * de cuál de las dos unidades está leyendo.
 *
 * Se hereda sin cambios la regla que atraviesa `tipos.ts`: **importes,
 * cantidades y porcentajes son `string`**, los porcentajes son fracción
 * (`"0.2885"` = 28,85 %) y lo indefinido llega `null` para pintarse «—», nunca
 * `0`. Tipar cualquiera de estos campos como `number` sería pedirle a
 * TypeScript que bendijera la operación que corrompe las cifras.
 *
 * Fuente: `backend/app/schemas/agro.py` y
 * `backend/app/infrastructure/models/agro_vocabulario.py`.
 */

import type { Medida, Semaforo } from "./tipos";

export interface AlertaComercial {
  tipo: string;
  cliente: string;
  producto: string | null;
  venta_anterior: string;
  venta_actual: string;
  variacion: string | null;
  detalle: string;
}

export interface OportunidadComercial {
  cliente: string;
  producto: string;
  venta_producto: string;
  detalle: string;
}

export interface RecomendacionComercial {
  prioridad: string;
  titulo: string;
  detalle: string;
}

export interface RespuestaInteligencia {
  periodo: string;
  periodo_anterior: string;
  disponible: boolean;
  mensaje: string | null;
  alertas: AlertaComercial[];
  productos_no_solicitados: AlertaComercial[];
  oportunidades: OportunidadComercial[];
  recomendaciones: RecomendacionComercial[];
}

export interface FilaVentaComercialAgro {
  tipo_comercial: string;
  especie: string;
  venta_valor: string;
  kilos: string;
}

export interface RespuestaVentasComercialesAgro {
  periodo: string;
  fecha_corte: string;
  filas: FilaVentaComercialAgro[];
}

// ── Vocabulario ──────────────────────────────────────────────────────────────

/**
 * Los siete ejes de lectura del resumen (`EjeResumen`).
 *
 * Cuatro de ellos coinciden con una dimensión de presupuesto y tres no. Esa
 * diferencia no es una casualidad de nombres: decide qué columnas de la fila
 * traen dato y cuáles vienen vacías, así que la pantalla la consulta con
 * `dimensionDeEje` en lugar de deducirla mirando si `presupuesto` es `null`.
 */
export type EjeResumenAgro =
  | "centro_operacion"
  | "tipo_item"
  | "especie"
  | "tipo_comercial"
  | "grupo"
  | "vendedor"
  | "cliente";

/**
 * Los dos cruces, y solo esos dos.
 *
 * El backend los declara como un enum cerrado y no como ejes componibles: un
 * cruce de tres dimensiones sobre 686 clientes y sus productos ya es una tabla
 * de decenas de miles de filas, y dejar componer cinco produciría una consulta
 * que nadie quiso pedir.
 */
export type EjeCruceAgro = "vendedor-cliente" | "vendedor-cliente-producto";

/**
 * Las cuatro descomposiciones por las que el negocio fija presupuesto.
 *
 * **Son cuatro vistas del mismo total, no cuatro totales.** El presupuesto por
 * vendedor y el presupuesto por especie describen el mismo dinero; sumarlos da
 * el doble de la meta. Por eso ninguna pantalla suma dos dimensiones y ningún
 * tipo de este archivo ofrece un campo donde esa suma cupiera.
 */
export type DimensionPresupuestoAgro =
  "vendedor" | "centro_operacion" | "especie" | "tipo_comercial";

// ── Indicadores ──────────────────────────────────────────────────────────────

/**
 * El bloque de indicadores de una fila, sea cual sea el eje.
 *
 * Un solo tipo para los siete ejes de resumen, los dos cruces y el consolidado,
 * igual que `FilaIndicadores` en carnes: así un indicador nuevo entra una vez y
 * aparece en todas partes a la vez.
 *
 * **Las filas de `TipoItem = IMPUESTO` no están en ninguno de estos números.**
 * Se ingieren y se guardan marcadas —para poder conciliar con el origen— y se
 * excluyen de todo total, todo porcentaje y toda comparación contra
 * presupuesto: no es venta, es recaudo a nombre de terceros. Cuánto se excluyó
 * se publica aparte, en `ConciliacionAgro`.
 */
export interface IndicadoresAgro {
  /** La venta en la medida del reporte: pesos o kilos. */
  venta: string;
  /**
   * La venta **siempre en pesos**, aunque el reporte se mire en kilos.
   *
   * El margen y la participación son conceptos monetarios: sin este campo, una
   * pantalla en kilos no podría contrastar el margen contra la venta que lo
   * produjo sin volver a pedir el reporte en la otra medida.
   */
  venta_valor: string;
  kilos: string;
  cantidad: string;
  /**
   * `LineasFacturadas`. **Líneas, no documentos ni tickets.**
   *
   * Una venta de ocho productos son ocho líneas y **un** documento, y la fuente
   * no entrega el documento. La pantalla lo nombra «líneas» por eso mismo: es
   * el único nombre que no induce a leer un conteo de ventas.
   */
  lineas_facturadas: number;
  /** Fracción de la venta total del corte que representa esta fila. */
  participacion: string | null;

  /** Puede ser **negativo**: hay venta entre compañías del grupo bajo costo. */
  margen_valor: string | null;
  margen_porcentaje: string | null;

  /**
   * Los siete campos que dependen del presupuesto.
   *
   * Vienen `null` —y `semaforo` en `SIN_PRESUPUESTO`— en los tres ejes que no
   * se presupuestan: cliente, grupo y tipo de ítem. No es un hueco por cargar:
   * es que ahí no hay meta contra la que medir, y la pantalla lo dice con
   * palabras en lugar de dejar una columna de guiones sin motivo.
   */
  presupuesto: string | null;
  cumplimiento: string | null;
  ideal: string | null;
  brecha: string | null;
  semaforo: Semaforo;
  proyeccion: string | null;
  cumplimiento_proyectado: string | null;
  venta_diaria_promedio: string | null;
  venta_diaria_requerida: string | null;
  dias_habiles: string | null;
  dias_trabajados: string | null;
}

/**
 * Una fila del resumen: el miembro y sus indicadores.
 *
 * En el eje **cliente** `clave` y `nombre` traen el mismo texto, porque la
 * fuente no entrega NIT ni código de cliente: es la única dimensión sin
 * identificador propio. La pantalla no pinta columna de código en ese eje —sería
 * la misma cadena repetida al lado—; ver `ejeSinClavePropia`.
 */
export interface FilaResumenAgro extends IndicadoresAgro {
  clave: string;
  nombre: string;
  /**
   * Último día **dentro del corte** con venta de este miembro.
   *
   * Acotado al corte, no es la última venta histórica: filtrar por julio y leer
   * «12 de julio» significa que fue su último día *en julio*. Se llama venta y
   * no compra porque el mismo campo, en el eje de vendedor, no describe la
   * compra de nadie; la pantalla lo rotula según el eje.
   */
  ultima_venta?: string | null;
}

// ── Trazabilidad del cálculo ─────────────────────────────────────────────────

/**
 * Lo que se dejó fuera de los totales, y por qué.
 *
 * Existe para que la cifra del reporte se pueda conciliar con el origen sin
 * adivinar la diferencia. No se esconde en una pista: va escrito al pie de cada
 * reporte.
 */
export interface ConciliacionAgro {
  impuesto_valor: string;
  impuesto_kilos: string;
  /**
   * Suma de `LineasFacturadas` de las filas de impuesto: **líneas, no filas**.
   *
   * No tiene por qué coincidir con el campo `impuesto` de una corrida de
   * ingesta, que cuenta filas del origen —una fila puede traer varias líneas
   * facturadas—. En una carga real de siete días fueron 170 filas y 180 líneas.
   * Las dos cifras son correctas y cuentan cosas distintas; la interfaz las
   * separa donde aparecen juntas, o la diferencia se lee como diez filas
   * perdidas.
   */
  impuesto_lineas: number;
  /** Redactada por el backend; se publica tal cual, no se reescribe aquí. */
  nota: string;
}

/** El total de una dimensión de presupuesto, para contrastarlo con las demás. */
export interface CuadreDimensionAgro {
  dimension: string;
  etiqueta: string;
  total_monto: string;
  total_kilos: string;
}

/**
 * ¿Las cuatro descomposiciones dan el mismo total?
 *
 * Si el presupuesto por vendedor suma distinto que el presupuesto por especie,
 * uno de los dos repartos está mal, porque los dos describen el mismo dinero.
 * **El sistema no lo corrige** —repartir la diferencia sería inventarse la meta
 * de alguien—: lo publica, y quien lo capturó lo arregla.
 */
export interface CuadrePresupuestoAgro {
  periodo: string;
  cuadra: boolean;
  /** Diferencia entre el total más alto y el más bajo. Cero cuando cuadra. */
  diferencia_monto: string;
  diferencia_kilos: string;
  mensaje: string;
  dimensiones: CuadreDimensionAgro[];
}

/**
 * De dónde sale cada número, y qué se dejó fuera.
 *
 * Viaja en toda respuesta de reporte. `cuadre` va aquí y no solo en la pantalla
 * de presupuesto porque un descuadre entre descomposiciones invalida la lectura
 * de cualquier reporte, y quien mire un cumplimiento tiene derecho a enterarse
 * sin ir a buscarlo a otra pantalla.
 */
export interface ParametrosCalculoAgro {
  fecha_corte: string;
  dias_habiles: string | null;
  dias_trabajados: string | null;
  umbrales: Record<string, string>;
  /** La dimensión contra la que se midió, o `null` si el eje no tiene meta. */
  dimension_presupuesto: string | null;
  cuadre: CuadrePresupuestoAgro | null;
  conciliacion: ConciliacionAgro;
  /** Las fórmulas tal como están escritas en la especificación. */
  formulas: Record<string, string>;
}

// ── Reportes ─────────────────────────────────────────────────────────────────

export interface RespuestaResumenAgro {
  periodo: string;
  fecha_corte: string;
  medida: Medida;
  por: EjeResumenAgro;
  consolidado: IndicadoresAgro;
  filas: FilaResumenAgro[];
  parametros_calculo: ParametrosCalculoAgro;
}

/**
 * Una fila de un cruce: las claves de sus dos o tres ejes.
 *
 * `claves` y `nombres` son listas alineadas con `ejes` en vez de campos con
 * nombre fijo, y es deliberado: los dos cruces tienen distinto número de ejes y
 * con campos fijos el de dos tendría uno vacío. La pantalla recorre `ejes` y
 * pinta una columna por cada uno.
 */
export interface FilaCruceAgro extends IndicadoresAgro {
  claves: string[];
  nombres: string[];
}

export interface RespuestaCruceAgro {
  periodo: string;
  fecha_corte: string;
  medida: Medida;
  por: EjeCruceAgro;
  /** Los ejes del cruce, en orden. `claves` y `nombres` van alineados con él. */
  ejes: string[];
  /**
   * El total del corte entero, **sin truncar**, aunque `filas` sí lo esté.
   *
   * Es lo que mantiene cierta la participación: con la suma del top-N como
   * denominador, las participaciones sumarían 100 % por construcción y un
   * cliente que es el 19 % de la compañía se publicaría como 20,3 %.
   */
  consolidado: IndicadoresAgro;
  filas: FilaCruceAgro[];
  /**
   * `true` si la respuesta trae solo las primeras `limite` filas por venta.
   *
   * Pasa de verdad y con diferencias grandes: en un corte real, las 500 filas
   * publicadas de vendedor × cliente × producto sumaban 2.949 M contra un
   * consolidado de 3.147 M. Casi 200 millones fuera de la vista no caben en una
   * nota al pie.
   */
  truncado: boolean;
  /** Tope de filas del servidor. **No es un parámetro de la petición.** */
  limite: number;
  parametros_calculo: ParametrosCalculoAgro;
}

export interface FilaVentaDiariaAgro {
  /** Código de centro de operación: `301`, `302`. */
  centro: string;
  nombre: string;
  /** Un valor por fecha, en el orden de `fechas`. `null` = sin venta registrada. */
  valores: (string | null)[];
  total: string;
}

/**
 * La fila de totales, en un campo propio y no como una fila más.
 *
 * Mezclada entre las filas habría que reconocerla por su nombre, y esa
 * convención se rompe el día que alguien bautice así un centro.
 */
export interface TotalesVentaDiariaAgro {
  valores: (string | null)[];
  total: string;
  /**
   * `Σ (P_i / H_i)` sobre los centros: la suma de las líneas de referencia de
   * las filas, no el presupuesto agregado partido por unos días ponderados.
   *
   * `null` si ningún centro tiene presupuesto, y también si alguno lo tiene y no
   * tiene días hábiles: ahí el término es incalculable y sumar solo el resto
   * publicaría una referencia más baja que la real con pinta de completa.
   */
  presupuesto_diario: string | null;
}

export interface RespuestaVentaDiariaAgro {
  periodo: string;
  fecha_corte: string;
  desde: string;
  hasta: string;
  medida: Medida;
  fechas: string[];
  /**
   * `presupuesto_mensual / H` por centro, indexado por código de C.O.
   *
   * Sale de la dimensión `centro_operacion`, la única de las cuatro que reparte
   * la meta por la unidad que tiene calendario. Hoy llega `{"301": null,
   * "302": null}` mientras nadie capture presupuesto, y ese estado se explica en
   * pantalla en vez de dejar la columna de referencia en blanco.
   */
  presupuesto_diario_por_centro: Record<string, string | null>;
  filas: FilaVentaDiariaAgro[];
  totales: TotalesVentaDiariaAgro;
  parametros_calculo: ParametrosCalculoAgro;
}

// ── Presupuesto ──────────────────────────────────────────────────────────────

/** La meta de un miembro dentro de una dimensión. */
export interface MiembroDimensionAgro {
  tipo: string;
  clave: string;
  nombre: string;
  activo: boolean;
}

export interface MetaAgro {
  dimension: string;
  clave: string;
  nombre: string;
  monto: string;
  kilos: string;
}

/**
 * El presupuesto del período **visto por una dimensión**, con su total.
 *
 * `total_monto` es el presupuesto de la compañía repartido por esta dimensión,
 * no el de un trozo. Por eso no existe ningún total por encima de este: sumar
 * los de dos dimensiones contaría el mismo dinero dos veces.
 */
export interface PresupuestoDimensionAgro {
  dimension: string;
  etiqueta: string;
  /**
   * `false` cuando nadie ha capturado nada en esta dimensión.
   *
   * No es lo mismo que un presupuesto de cero: aquel es una afirmación del
   * negocio y este es la ausencia de la parametrización.
   */
  definido: boolean;
  total_monto: string;
  total_kilos: string;
  filas: MetaAgro[];
}

/** Cuerpo de `PUT /agro/presupuesto`. */
export interface EntradaPresupuestoAgro {
  periodo: string;
  /** Obligatoria: sin ella no se sabe en cuál de los cuatro repartos va la cifra. */
  dimension: DimensionPresupuestoAgro;
  clave: string;
  etiqueta?: string | null;
  monto: string;
  kilos: string;
  /** Mínimo cinco caracteres; el backend rechaza «ajuste» a secas. */
  motivo: string;
}

export interface HistorialAgro {
  cuando: string;
  quien: string | null;
  dimension: string;
  clave: string;
  campo: string;
  valor_anterior: string | null;
  valor_nuevo: string | null;
  motivo: string;
}

export interface ErrorFilaAgro {
  fila: number;
  motivo: string;
}

/**
 * Resultado de la carga masiva, con el cuadre recién calculado.
 *
 * El cuadre viaja aquí a propósito: el momento de ver que las cuatro
 * descomposiciones no dan lo mismo es justo después de subirlas, cuando quien
 * lo hizo todavía tiene el archivo abierto.
 */
export interface ResultadoCargaAgro {
  aceptadas: number;
  rechazadas: number;
  errores: ErrorFilaAgro[];
  cuadre: CuadrePresupuestoAgro;
}

// ── Calendario ───────────────────────────────────────────────────────────────

/**
 * Días hábiles y trabajados de un centro de operación.
 *
 * La unidad de calendario de agropecuaria es el **centro** —301 y 302—, no una
 * zona: son dos y pueden abrir días distintos. Admiten media jornada, así que
 * son decimales (`"27.5"`).
 */
export interface CalendarioAgro {
  centro: string;
  nombre: string;
  dias_habiles: string;
  dias_trabajados: string | null;
  ideal: string | null;
  fecha_corte: string | null;
  /**
   * `true` si los días trabajados los derivó el sistema de la fecha de corte;
   * `false` si los escribió el usuario, cuya afirmación manda.
   */
  derivado: boolean;
}

/** `dias_trabajados` nulo significa **derivado** de la fecha de corte. */
export interface EntradaCalendarioAgro {
  dias_habiles: string;
  dias_trabajados: string | null;
}

// ── Ingesta ──────────────────────────────────────────────────────────────────

export interface CorridaAgro {
  id: number;
  cuando: string;
  quien: string | null;
  fuente: string;
  desde: string | null;
  hasta: string | null;
  estado: string;
  filas_leidas: number;
  aceptadas: number;
  rechazadas: number;
  /**
   * Filas de impuesto cargadas. Van **dentro** de `aceptadas` —se guardan— y se
   * cuentan aparte porque son las que no van a aparecer en ningún total.
   *
   * Cuenta **filas del origen**, no líneas facturadas: es otra cifra que
   * `conciliacion.impuesto_lineas`, y las dos son correctas. Sin este número,
   * conciliar la corrida contra el origen daría una diferencia sin explicación.
   */
  impuesto: number;
  duracion_ms: number | null;
}

export interface RechazoAgro {
  fila: number | null;
  campo: string | null;
  valor: string | null;
  motivo: string;
}

// ── Presupuesto mensual configurable ──────────────────────────────────────────
//
// Este módulo es **distinto** del presupuesto por dimensiones de arriba. Aquí
// hay cuatro bloques independientes —comercial, agro distribución, servicio y
// nacional— y el total mensual **es la suma de los cuatro**, porque cada bloque
// es una meta distinta. En el presupuesto por dimensiones, las cuatro
// descomposiciones describen el mismo dinero y no se suman; aquí sí.
//
// Fuente: `backend/app/schemas/agro.py` (clases `*Mensual*`) y
// `backend/app/api/v1/agro.py` (rutas bajo `/agro/presupuesto-mensual`).

/** Los cuatro bloques del presupuesto mensual. Son independientes y se suman. */
export type BloqueMensual =
  | "commercial"
  | "agro_distribucion"
  | "servicio"
  | "nacional";

/**
 * Los tres bloques que se capturan como filas de detalle.
 *
 * El bloque de servicio se captura aparte —un solo valor mensual— y no
 * admite filas de detalle.
 */
export type BloqueDetalleMensual =
  | "commercial"
  | "agro_distribucion"
  | "nacional";

/** Categorías A–F que se asignan a los vendedores del bloque comercial. */
export type CategoriaMensual = "A" | "B" | "C" | "D" | "E" | "F";

/** Una fila de presupuesto mensual de un bloque de detalle. */
export interface DetalleMensual {
  id: number | null;
  bloque: BloqueMensual;
  cliente_clave: string | null;
  vendedor_clave: string | null;
  categoria: string | null;
  cliente_etiqueta: string | null;
  vendedor_etiqueta: string | null;
  monto: string;
  kilos: string;
}

/**
 * Cuerpo de `PUT /agro/presupuesto-mensual/detalle?periodo=`.
 *
 * El bloque de servicio no se captura aquí: tiene su propio endpoint porque es
 * un solo valor mensual sin descomposición.
 *
 * Los bloques `agro_distribucion` y `nacional` tienen vendedor fijo en el
 * backend (`AGROPECUARIA` y `JUAN SIERRA`): si no se envía, el backend lo fija;
 * si se envía con otro valor, lo rechaza. La pantalla no lo envía para esos
 * bloques.
 */
export interface EntradaDetalleMensual {
  bloque: BloqueDetalleMensual;
  cliente_clave?: string | null;
  vendedor_clave?: string | null;
  categoria?: string | null;
  cliente_etiqueta?: string | null;
  vendedor_etiqueta?: string | null;
  monto: string;
  kilos: string;
}

/** El bloque de servicio: un solo valor mensual. */
export interface ServicioMensual {
  monto: string;
  kilos: string;
}

/** Cuerpo de `PUT /agro/presupuesto-mensual/servicio?periodo=`. */
export interface EntradaServicioMensual {
  monto: string;
  kilos: string;
}

/**
 * Una asignación configurable: bloque → vendedor / cliente / categoría.
 *
 * `vendedor_clave`, `cliente_clave` y `categoria` son opcionales porque no
 * todos los bloques los usan: el bloque de servicio no tiene vendedor ni
 * cliente, y la categoría A–F solo aplica al bloque comercial.
 */
export interface MapeoMensual {
  id: number;
  bloque: BloqueMensual;
  vendedor_clave: string | null;
  cliente_clave: string | null;
  categoria: string | null;
  activo: boolean;
}

/**
 * Cuerpo de `PUT /agro/presupuesto-mensual/mapeos`.
 *
 * Si `mapeo_id` se envía como parámetro de consulta, el backend actualiza la
 * asignación existente; si no, crea una nueva.
 */
export interface EntradaMapeoMensual {
  bloque: BloqueMensual;
  vendedor_clave?: string | null;
  cliente_clave?: string | null;
  categoria?: string | null;
  activo: boolean;
}

/** El total de un bloque en el período, con sus filas de detalle. */
export interface BloqueMensualResumen {
  bloque: BloqueMensual;
  total_monto: string;
  total_kilos: string;
  filas: DetalleMensual[];
}

/**
 * El presupuesto mensual completo: los cuatro bloques y el total.
 *
 * A diferencia del presupuesto por dimensiones, aquí `total_monto` **es la
 * suma de los cuatro bloques**, porque cada bloque es una meta independiente.
 */
export interface ResumenPresupuestoMensual {
  periodo: string;
  bloques: BloqueMensualResumen[];
  total_monto: string;
  total_kilos: string;
}
