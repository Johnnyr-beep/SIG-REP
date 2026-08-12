/**
 * Tipos del contrato de API (`docs/API.md`).
 *
 * Regla que atraviesa todo el archivo: **importes, cantidades y porcentajes son
 * `string`**. No es una omisión ni una comodidad —es el contrato— y tipar esos
 * campos como `number` haría que TypeScript bendijera precisamente la operación
 * que corrompe los datos. Un indicador indefinido llega como `null` y se pinta
 * «—».
 */

// ── Sesión ───────────────────────────────────────────────────────────────────

export type Rol = "GERENTE" | "ANALISTA" | "JEFE_PDV" | "CONSULTA";

export interface Usuario {
  id: number;
  usuario: string;
  nombre: string;
  rol: Rol;
  /** Puntos de venta visibles para el usuario; vacío en los roles globales. */
  puntos_venta: ReferenciaSimple[];
}

export interface TokensAcceso {
  token_acceso: string;
  token_refresco: string;
  tipo: string;
}

export interface TokenRenovado {
  token_acceso: string;
}

export interface CuerpoError {
  detalle?: string;
  codigo?: string;
}

// ── Referencias ──────────────────────────────────────────────────────────────

/**
 * Referencia a una entidad de catálogo dentro de una fila de reporte.
 *
 * El contrato escribe `{punto_venta, categoria, ...}` sin fijar si viaja el
 * nombre a secas o un objeto con código y nombre. Aceptar ambas formas cuesta
 * una función de dos líneas y evita que la interfaz se rompa el día que el
 * backend cierre esa ambigüedad en un sentido o en otro.
 */
export type ReferenciaSimple =
  | string
  | {
      id?: number | null;
      codigo?: string | null;
      codigo_co?: string | null;
      nombre?: string | null;
    };

// ── Catálogos ────────────────────────────────────────────────────────────────

export interface Grupo {
  id: number;
  codigo: string;
  nombre: string;
}

export interface PuntoVenta {
  id: number;
  /** Centro de operación de SIESA. Es la llave de integración. */
  codigo_co: string;
  nombre: string;
  grupo: ReferenciaSimple;
  zona: ReferenciaSimple;
  activo: boolean;
  /** `false` en los PDV que venden sin presupuesto (p. ej. 432 EVENTOS). */
  presupuestado: boolean;
}

export interface Categoria {
  id: number;
  codigo: string;
  nombre: string;
  orden: number;
}

export interface Zona {
  id: number;
  nombre: string;
  puntos_venta: ReferenciaSimple[];
}

export interface MapeoCategoria {
  texto_siesa: string;
  categoria: ReferenciaSimple;
}

// ── Calendario ───────────────────────────────────────────────────────────────

export interface FilaCalendario {
  zona: ReferenciaSimple;
  /** Decimal con una posición: admite media jornada (`"27.5"`). */
  dias_habiles: string | null;
  dias_trabajados: string | null;
  /** `dias_trabajados / dias_habiles`, como fracción. */
  ideal: string | null;
  fecha_corte: string;
}

export interface EntradaCalendario {
  dias_habiles: string;
  /** `null` deja que el backend lo derive del calendario y la fecha de corte. */
  dias_trabajados: string | null;
}

// ── Presupuesto ──────────────────────────────────────────────────────────────

export interface FilaPresupuesto {
  punto_venta: ReferenciaSimple;
  categoria: ReferenciaSimple;
  monto: string | null;
  kilos: string | null;
  actualizado_en: string | null;
  actualizado_por: string | null;
}

export interface EntradaPresupuesto {
  periodo: string;
  punto_venta_id: number;
  categoria_id: number;
  monto: string;
  kilos: string;
  motivo: string;
}

export interface CambioPresupuesto {
  cuando: string;
  quien: string;
  campo: string;
  valor_anterior: string | null;
  valor_nuevo: string | null;
  motivo: string | null;
}

export interface ErrorDeFila {
  fila: number;
  motivo: string;
}

export interface ResultadoCargaMasiva {
  aceptadas: number;
  rechazadas: number;
  errores: ErrorDeFila[];
}

export interface Periodo {
  periodo: string;
  cerrado: boolean;
  cerrado_por: string | null;
  cerrado_en: string | null;
}

// ── Reportes ─────────────────────────────────────────────────────────────────

export type Medida = "valor" | "kilos";

export type Semaforo = "VERDE" | "AMARILLO" | "ROJO" | "SIN_PRESUPUESTO";

/**
 * El bloque de indicadores de §4, idéntico en todos los niveles de agregación.
 *
 * Un solo tipo y un solo componente de fila, como pide el contrato: si mañana
 * se añade un indicador, entra una vez y aparece en compañía, grupo, punto de
 * venta y categoría a la vez.
 */
export interface FilaIndicadores {
  presupuesto: string | null;
  venta: string | null;
  cumplimiento: string | null;
  ideal: string | null;
  brecha: string | null;
  semaforo: Semaforo;
  proyeccion: string | null;
  cumplimiento_proyectado: string | null;
  venta_diaria_promedio: string | null;
  venta_diaria_requerida: string | null;
  venta_anio_anterior: string | null;
  crecimiento: string | null;
  margen_valor: string | null;
  margen_porcentaje: string | null;
  dias_habiles: string | null;
  dias_trabajados: string | null;
}

/**
 * De dónde sale cada número.
 *
 * La gerencia tiene que poder verificar el cálculo a mano; sin estos parámetros
 * junto al resultado, el indicador es un número sin origen. Los umbrales se
 * tipan abiertos porque el contrato no fija sus claves y esta pantalla los
 * enumera tal como lleguen.
 */
export interface ParametrosCalculo {
  dias_habiles: string | null;
  dias_trabajados: string | null;
  fecha_corte: string;
  umbrales: Record<string, string> | null;
}

export interface FilaGrupo extends FilaIndicadores {
  codigo: string;
  nombre: string;
}

export interface VentaSinPresupuesto {
  codigo_co: string;
  nombre: string;
  venta: string | null;
  kilos?: string | null;
}

export interface RespuestaTablero {
  periodo: string;
  fecha_corte: string;
  medida: Medida;
  consolidado: FilaIndicadores;
  grupos: FilaGrupo[];
  /** Venta de PDV no presupuestados: se reporta aparte, nunca se descarta. */
  sin_presupuesto: VentaSinPresupuesto[];
  parametros_calculo?: ParametrosCalculo | null;
}

export interface FilaCategoriaReporte extends FilaIndicadores {
  /** Nombre de la categoría SIGREP: `RES`, `CERDO`, `POLLO`, … */
  categoria: string;
}

/**
 * Fila de punto de venta del reporte.
 *
 * La referencia viaja **plana**, no anidada: `punto_venta` es el código C.O. de
 * SIESA y `nombre` la etiqueta que lee la gerencia. Mostrar `punto_venta` donde
 * corresponde `nombre` deja la tabla llena de códigos como «402» en lugar de
 * «MALAMBO».
 */
export interface FilaPuntoVentaReporte extends FilaIndicadores {
  /** Código C.O. de SIESA: `402`, `405`, … */
  punto_venta: string;
  nombre: string;
  categorias: FilaCategoriaReporte[] | null;
}

export interface RespuestaCumplimiento {
  periodo: string;
  fecha_corte: string;
  medida: Medida;
  filas: FilaPuntoVentaReporte[];
  sin_presupuesto?: VentaSinPresupuesto[];
  parametros_calculo?: ParametrosCalculo | null;
}

export interface FilaVentaDiaria {
  /** Código C.O. de SIESA. Es la llave de `presupuesto_diario_por_pdv`. */
  punto_venta: string;
  nombre: string;
  /** Un valor por cada fecha de `fechas`, en el mismo orden. */
  valores: (string | null)[];
  total: string | null;
}

export interface RespuestaVentaDiaria {
  fechas: string[];
  /** Presupuesto diario derivado, indexado por código de C.O. */
  presupuesto_diario_por_pdv: Record<string, string | null>;
  filas: FilaVentaDiaria[];
  fecha_corte?: string;
  medida?: Medida;
  parametros_calculo?: ParametrosCalculo | null;
}

export type CorteClientes = "cliente" | "vendedor" | "canal" | "condicion_pago";

export interface FilaClientes {
  clave: string;
  nombre: string;
  venta: string | null;
  kilos: string | null;
  margen_porcentaje: string | null;
  participacion: string | null;
}

export interface RespuestaClientes {
  filas: FilaClientes[];
  fecha_corte?: string;
  medida?: Medida;
  parametros_calculo?: ParametrosCalculo | null;
}

// ── Ingesta ──────────────────────────────────────────────────────────────────

export type FuenteIngesta = "siesa" | "excel";

export interface CorridaIngesta {
  id: number;
  cuando: string;
  quien: string;
  fuente: string;
  desde: string;
  hasta: string;
  estado: string;
  filas_leidas: number;
  aceptadas: number;
  rechazadas: number;
  duracion_ms: number;
}

export interface RechazoIngesta {
  fila: number;
  campo: string;
  valor: string;
  motivo: string;
}

export interface EntradaIngesta {
  desde: string;
  hasta: string;
  fuente: FuenteIngesta;
}

// ── Salud ────────────────────────────────────────────────────────────────────

export interface Salud {
  estado: string;
  version: string;
  base_datos: string;
  ultima_ingesta: string | null;
}
