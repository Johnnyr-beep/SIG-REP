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

export type Rol = "ADMIN" | "GERENTE" | "ANALISTA" | "JEFE_PDV" | "CONSULTA";

export interface Usuario {
  id: number;
  usuario: string;
  nombre: string;
  rol: Rol;
  /**
   * Clave provisional pendiente de cambiar.
   *
   * La activan el alta de una cuenta y todo restablecimiento hecho por un
   * administrador. Mientras valga `true` la aplicación no deja abrir ninguna
   * otra pantalla: sin ese bloqueo la marca no significaría nada y la clave que
   * un tercero escribió en un papel seguiría sirviendo indefinidamente.
   */
  debe_cambiar_password: boolean;
  /** Puntos de venta visibles para el usuario; vacío en los roles globales. */
  puntos_venta: ReferenciaSimple[];
}

/** Cuerpo de `POST /auth/cambiar-clave`. */
export interface CambioClave {
  clave_actual: string;
  clave_nueva: string;
}

/** Mínimo de caracteres de `clave_nueva`; se valida antes de enviar. */
export const LARGO_MINIMO_CLAVE = 12;

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

/** Presupuesto diario derivado de un período, indexado por código de C.O. */
export type PresupuestoDiarioPorPdv = Record<string, string | null>;

/**
 * La fila de totales del reporte diario.
 *
 * Viaja en un **campo propio** y no como una fila más de `filas`, a propósito:
 * mezclada habría que reconocerla por su nombre (`punto_venta === "TOTAL"`) y
 * esa convención se rompe el día que alguien bautice así un punto de venta.
 *
 * `presupuesto_diario` es `Σ (presupuesto_i ÷ días hábiles_i)` —la suma de las
 * líneas de referencia de las filas que están encima—, no el presupuesto
 * agregado partido por unos días ponderados. Es `null` cuando el término de
 * algún punto es incalculable: publicar la suma del resto daría una referencia
 * más baja que la real con pinta de completa.
 */
export interface TotalesVentaDiaria {
  /** Un valor por cada fecha de `fechas`. `null` = ningún punto registró venta. */
  valores: (string | null)[];
  total: string | null;
  /** Referencia diaria del período de la petición. */
  presupuesto_diario: string | null;
  /** Referencia diaria de cada período que el rango toca. */
  presupuesto_diario_por_periodo: Record<string, string | null>;
}

export interface RespuestaVentaDiaria {
  /** Período de referencia de la petición: de él salen `parametros_calculo`. */
  periodo: string;
  /** Primer día del rango. Viaja en los dos modos: la respuesta es autodescriptiva. */
  desde: string;
  /** Último día del rango. Coincide siempre con `fecha_corte`. */
  hasta: string;
  /** Períodos que el rango toca, en orden. Uno solo en el modo de siempre. */
  periodos: string[];
  fechas: string[];
  /**
   * Referencia del **período de la petición**, indexada por código de C.O.
   *
   * Equivale a `presupuesto_diario_por_periodo[periodo]`. No sirve para pintar
   * las celdas de un rango que cruza meses: daría la referencia de agosto a los
   * días de julio. Para eso está el campo de abajo.
   */
  presupuesto_diario_por_pdv: PresupuestoDiarioPorPdv;
  /**
   * Referencia de cada período tocado, indexada por período y por código de C.O.
   *
   * El período de una fecha es su prefijo `YYYY-MM`, así que cruzar un día con
   * su referencia no necesita nada más. Un período que el rango toca y que no
   * está abierto en el sistema publica sus referencias en `null`.
   */
  presupuesto_diario_por_periodo: Record<string, PresupuestoDiarioPorPdv>;
  filas: FilaVentaDiaria[];
  totales: TotalesVentaDiaria;
  fecha_corte?: string;
  medida?: Medida;
  parametros_calculo?: ParametrosCalculo | null;
}

/** Tope de días del reporte diario. Inclusivo: 92 entran, 93 no. */
export const MAXIMO_DIAS_VENTA_DIARIA = 92;

/** Los dos rechazos propios del rango, con el código que los distingue. */
export const CODIGO_RANGO_INVERTIDO = "rango_invertido";
export const CODIGO_RANGO_EXCESIVO = "rango_excesivo";

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

// ── Usuarios · administración de cuentas ─────────────────────────────────────

/**
 * Ficha completa de una cuenta, tal como la devuelve `GET /usuarios`.
 *
 * Extiende la del perfil con lo que solo ve un `ADMIN`. El hash no aparece aquí
 * porque no aparece en ninguna respuesta: es la regla 6 del contrato.
 */
export interface UsuarioAdministrado extends Usuario {
  email: string | null;
  activo: boolean;
  /** Bloqueo por intentos fallidos; se levanta restableciendo la clave. */
  bloqueado: boolean;
  ultimo_acceso: string | null;
  creado_en: string | null;
}

/**
 * Formato del nombre de acceso que exige el backend.
 *
 * Minúsculas, dígitos, punto, guion y guion bajo; entre 3 y 50 caracteres y sin
 * empezar por signo. Se replica aquí para avisar mientras se escribe en lugar de
 * dejar que el alta termine en un 422 con el formulario ya lleno.
 */
export const PATRON_USUARIO = /^[a-z0-9][a-z0-9._-]{2,49}$/;

/** Largo mínimo del nombre visible. Lo mismo: mejor avisar que recibir un 422. */
export const LARGO_MINIMO_NOMBRE = 3;

/** Cuerpo de `POST /usuarios`. Los puntos de venta viajan por código C.O. */
export interface EntradaUsuario {
  usuario: string;
  nombre: string;
  email: string | null;
  rol: Rol;
  puntos_venta: string[];
}

/** Cuerpo de `PATCH /usuarios/{id}`: solo los tres campos editables. */
export interface CambioUsuario {
  nombre: string;
  email: string | null;
  rol: Rol;
}

/**
 * Respuesta del alta.
 *
 * `clave_provisional` es el único punto del sistema donde una clave en claro
 * cruza la red, y ocurre **una sola vez**: no vuelve en ninguna consulta
 * posterior. La interfaz que la recibe no la persiste en ningún sitio.
 */
export interface UsuarioCreado {
  usuario: UsuarioAdministrado;
  clave_provisional: string;
}

/** Respuesta de `POST /usuarios/{id}/restablecer-clave`. */
export interface ClaveRestablecida {
  id: number;
  usuario: string;
  clave_provisional: string;
}

/**
 * Una línea de `GET /usuarios/auditoria`: quién, sobre quién, qué y cuándo.
 *
 * El contrato nombra los campos `quien`, `sobre_quien` y `detalle`; el
 * serializador del backend los desglosa como `actor`, `usuario` y la terna
 * `campo`/`valor_anterior`/`valor_nuevo`. Se aceptan las dos formas por la misma
 * razón que en `ReferenciaSimple`: cuesta dos funciones de lectura y evita que
 * la tabla se quede en blanco el día que uno de los dos lados se alinee con el
 * otro.
 */
export interface EventoAuditoria {
  cuando: string;
  accion: string;
  /** Quien ejecutó la operación. */
  quien?: string | null;
  actor?: string | null;
  /** La cuenta administrada. */
  sobre_quien?: string | null;
  usuario?: string | null;
  /** Qué cambió, en una forma u otra. */
  detalle?: string | null;
  campo?: string | null;
  valor_anterior?: string | null;
  valor_nuevo?: string | null;
  ip_origen?: string | null;
}

// ── Salud ────────────────────────────────────────────────────────────────────

/** Unidad de negocio que sirve una instancia. `todas` es el caso de hoy. */
export type UnidadNegocio =
  "todas" | "carnes" | "agropecuaria" | "carnes-frias";

export interface Salud {
  estado: string;
  /**
   * La unidad que sirve **esta** instancia.
   *
   * `todas` mientras carnes y agropecuaria compartan base y despliegue, que es
   * el caso de hoy; fijada a una sola el día que alguna se lleve a su propio
   * servidor. No es una preferencia visual: decide qué pantallas tienen sentido.
   *
   * Opcional por la misma razón que `unidades`: un backend anterior a este
   * contrato responde sin los dos campos y la interfaz no debe romperse por eso.
   */
  unidad?: UnidadNegocio;
  /**
   * Las unidades que de verdad se pueden mirar.
   *
   * El selector desactiva las que no están aquí en lugar de dejar entrar a una
   * pantalla sin datos detrás: elegir una marca no puede hacer aparecer una
   * unidad que la instancia no sirve. Viaja en un endpoint **público** a
   * propósito, porque el selector va antes del acceso.
   *
   * Opcional en el tipo y no en el contrato: un backend anterior a este campo
   * responde sin él, y en ese caso la interfaz se queda con el censo local de
   * `marca/marcas.ts` en vez de dejar las tres marcas apagadas.
   */
  unidades?: string[];
  version: string;
  base_datos: string;
  ultima_ingesta: string | null;
}
