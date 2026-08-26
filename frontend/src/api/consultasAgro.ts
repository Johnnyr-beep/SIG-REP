/**
 * Hooks de datos de la unidad Agropecuaria (`/api/v1/agro`).
 *
 * Mismo trato que `consultas.ts`: los componentes no conocen rutas ni verbos,
 * solo hooks con nombre de negocio. Van en un archivo aparte porque el contrato
 * también lo está —`api/v1/agro.py`— y porque las claves de caché de las dos
 * unidades no deben cruzarse: invalidar un reporte de carnes no puede tirar la
 * caché de agropecuaria ni al revés.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { UseMutationResult, UseQueryResult } from "@tanstack/react-query";

import { descargar, enviarArchivo, peticion } from "./cliente";
import type { ValorParametro } from "./cliente";
import type { Medida } from "./tipos";
import type {
  BloqueMensual,
  CalendarioAgro,
  CanalMapeoMensual,
  CorridaAgro,
  CuadrePresupuestoAgro,
  DimensionPresupuestoAgro,
  EjeCruceAgro,
  EjeResumenAgro,
  EntradaCalendarioAgro,
  EntradaCanalMapeoMensual,
  EntradaDetalleMensual,
  EntradaMapeoMensual,
  EntradaPresupuestoAgro,
  EntradaServicioMensual,
  HistorialAgro,
  MapeoMensual,
  MiembroDimensionAgro,
  PresupuestoDimensionAgro,
  RechazoAgro,
  ResumenPresupuestoMensual,
  RespuestaCruceAgro,
  RespuestaInteligencia,
  RespuestaResumenAgro,
  RespuestaVentaDiariaAgro,
  RespuestaVentasComercialesAgro,
  ResultadoCargaAgro,
  ResultadoImportacionComercial,
  ServicioMensual,
} from "./tiposAgro";

/**
 * Filtros comunes a los tres reportes de agropecuaria.
 *
 * Son los del router: `periodo` obligatorio, `hasta` como fecha de corte,
 * `desde` solo para el rango de la venta diaria, `centro` como lista separada
 * por comas y `medida`.
 *
 * **No hay `limite`.** El tope de filas del cruce es una opción del servidor
 * (`max_filas_reporte_agro`) y no un parámetro de la petición: la pantalla lo
 * lee de la respuesta para poder explicarlo, pero no lo puede subir.
 */
export interface FiltrosAgro {
  periodo: string;
  /** Primer día del rango. **Solo lo entiende `venta-diaria`.** */
  desde?: string;
  /** Fecha de corte. Ausente = hoy. */
  hasta?: string;
  /**
   * Códigos de centro separados por coma: `"301,302"`.
   *
   * **Ausente significa «todos»**, igual que `punto_venta` en carnes: el
   * backend trata `?centro=` como no filtrar, así que una selección vacía borra
   * el parámetro en lugar de enviarlo en blanco. Estrecha, jamás ensancha.
   */
  centro?: string;
  medida: Medida;
}

function comoParametros(filtros: FiltrosAgro): Record<string, ValorParametro> {
  return {
    periodo: filtros.periodo,
    desde: filtros.desde,
    hasta: filtros.hasta,
    centro: filtros.centro,
    medida: filtros.medida,
  };
}

/** Los mismos más `desde`, que solo declara el reporte diario. */
function comoParametrosDiarios(
  filtros: FiltrosAgro,
): Record<string, ValorParametro> {
  return { ...comoParametros(filtros), desde: filtros.desde };
}

/**
 * Claves de caché, todas bajo el prefijo `agro`.
 *
 * El prefijo es lo que permite invalidar «todos los reportes de agropecuaria»
 * sin tocar los de carnes: las dos unidades comparten instancia de TanStack
 * Query y un `["reporte"]` común las mezclaría.
 */
export const clavesAgro = {
  resumen: (filtros: FiltrosAgro, por: EjeResumenAgro) =>
    ["agro", "reporte", "resumen", por, filtros] as const,
  cruce: (filtros: FiltrosAgro, por: EjeCruceAgro) =>
    ["agro", "reporte", "cruce", por, filtros] as const,
  ventaDiaria: (filtros: FiltrosAgro) =>
    ["agro", "reporte", "venta-diaria", filtros] as const,
  ventasComerciales: (filtros: FiltrosAgro) =>
    ["agro", "reporte", "ventas-comerciales", filtros] as const,
  presupuesto: (periodo: string, dimension: string) =>
    ["agro", "presupuesto", periodo, dimension] as const,
  cuadre: (periodo: string) =>
    ["agro", "presupuesto", "cuadre", periodo] as const,
  historial: (periodo: string, dimension: string) =>
    ["agro", "presupuesto", "historial", periodo, dimension] as const,
  calendario: (periodo: string) => ["agro", "calendario", periodo] as const,
  inteligencia: (periodo: string) => ["agro", "inteligencia", periodo] as const,
  corridas: ["agro", "ingesta", "corridas"] as const,
  rechazos: (id: number) => ["agro", "ingesta", "rechazos", id] as const,
  // Presupuesto mensual configurable: rutas bajo /agro/presupuesto-mensual.
  // Claves aparte de las de /agro/presupuesto porque son módulos distintos:
  // invalidar una no debe tirar la caché de la otra.
  presupuestoMensual: (periodo: string) =>
    ["agro", "presupuesto-mensual", periodo] as const,
  mapeosMensual: (bloque?: string) =>
    ["agro", "presupuesto-mensual", "mapeos", bloque ?? "todos"] as const,
  servicioMensual: (periodo: string) =>
    ["agro", "presupuesto-mensual", "servicio", periodo] as const,
  // Mapeos de canal del Excel comercial: configuración aparte de los mapeos de
  // bloque, porque mapean canales del Excel y no combinaciones de bloque.
  canalesMapeosMensual: ["agro", "presupuesto-mensual", "canales", "mapeos"] as const,
};

export function useInteligenciaAgro(periodo: string): UseQueryResult<RespuestaInteligencia> {
  return useQuery({
    queryKey: clavesAgro.inteligencia(periodo),
    queryFn: () =>
      peticion<RespuestaInteligencia>("/agro/inteligencia", {
        parametros: { periodo },
      }),
    staleTime: 5 * 60_000,
  });
}

// ── Reportes ─────────────────────────────────────────────────────────────────

export function useResumenAgro(
  filtros: FiltrosAgro,
  por: EjeResumenAgro,
): UseQueryResult<RespuestaResumenAgro> {
  return useQuery({
    queryKey: clavesAgro.resumen(filtros, por),
    queryFn: () =>
      peticion<RespuestaResumenAgro>("/agro/resumen", {
        parametros: { ...comoParametros(filtros), por },
      }),
    staleTime: 60_000,
  });
}

export function useVentasComercialesAgro(
  filtros: FiltrosAgro,
): UseQueryResult<RespuestaVentasComercialesAgro> {
  return useQuery({
    queryKey: clavesAgro.ventasComerciales(filtros),
    queryFn: () =>
      peticion<RespuestaVentasComercialesAgro>("/agro/ventas-comerciales", {
        parametros: comoParametros(filtros),
      }),
    staleTime: 60_000,
  });
}

export function useCruceAgro(
  filtros: FiltrosAgro,
  por: EjeCruceAgro,
): UseQueryResult<RespuestaCruceAgro> {
  return useQuery({
    queryKey: clavesAgro.cruce(filtros, por),
    queryFn: () =>
      peticion<RespuestaCruceAgro>("/agro/cruce", {
        parametros: { ...comoParametros(filtros), por },
      }),
    staleTime: 60_000,
  });
}

/**
 * Matriz diaria por centro.
 *
 * `habilitado` existe para que la pantalla pueda **no lanzar** la consulta
 * cuando ya sabe que el rango es inválido —invertido o por encima del tope de
 * 92 días—: un 422 que el usuario no puede provocar es mejor que uno bien
 * explicado. El backend usa los mismos dos códigos de error que carnes,
 * `rango_invertido` y `rango_excesivo`, a propósito.
 */
export function useVentaDiariaAgro(
  filtros: FiltrosAgro,
  habilitado = true,
): UseQueryResult<RespuestaVentaDiariaAgro> {
  return useQuery({
    queryKey: clavesAgro.ventaDiaria(filtros),
    queryFn: () =>
      peticion<RespuestaVentaDiariaAgro>("/agro/venta-diaria", {
        parametros: comoParametrosDiarios(filtros),
      }),
    enabled: habilitado,
    staleTime: 60_000,
  });
}

/**
 * Exporta a `.xlsx` lo mismo que muestra la pantalla, con sus filtros.
 *
 * La ruta lleva el reporte al final (`/agro/exportar/resumen`) y no en medio
 * como en carnes: un `/agro/{reporte}/exportar` chocaría con
 * `/agro/presupuesto/cuadre`, que ya existe.
 */
export function useExportarAgro(): UseMutationResult<
  void,
  Error,
  {
    reporte: "resumen" | "cruce" | "venta-diaria";
    filtros: FiltrosAgro;
    por?: string;
  }
> {
  return useMutation({
    mutationFn: ({ reporte, filtros, por }) =>
      descargar(
        `/agro/exportar/${reporte}`,
        {
          ...(reporte === "venta-diaria"
            ? comoParametrosDiarios(filtros)
            : comoParametros(filtros)),
          por,
        },
        `sigrep-agro-${reporte}-${filtros.periodo}.xlsx`,
      ),
  });
}

// ── Presupuesto ──────────────────────────────────────────────────────────────

/**
 * El presupuesto del período, **de una dimensión a la vez**.
 *
 * El endpoint devuelve una lista de dimensiones, cada una con su total, y no
 * existe ningún total global: las cuatro son repartos del mismo dinero y
 * sumarlas daría cuatro veces la meta. Pedir siempre una dimensión concreta es
 * lo que hace que la pantalla no tenga dónde cometer ese error.
 */
export function usePresupuestoAgro(
  periodo: string,
  dimension: DimensionPresupuestoAgro,
): UseQueryResult<PresupuestoDimensionAgro[]> {
  return useQuery({
    queryKey: clavesAgro.presupuesto(periodo, dimension),
    queryFn: () =>
      peticion<PresupuestoDimensionAgro[]>("/agro/presupuesto", {
        parametros: { periodo, dimension },
      }),
    staleTime: 60_000,
  });
}

/** ¿Cuadran las cuatro descomposiciones entre sí? */
/**
 * El catálogo de una dimensión, para poder elegir a quién se le fija la meta.
 *
 * Lo crea la ingesta, no esta consulta: si viene vacío no es un fallo, es que
 * todavía no se ha cargado venta de la que deducirlo.
 */
export function useDimensionesAgro(tipo: string): UseQueryResult<MiembroDimensionAgro[]> {
  return useQuery({
    queryKey: ["agro", "dimensiones", tipo],
    queryFn: () =>
      peticion<MiembroDimensionAgro[]>("/agro/dimensiones", { parametros: { tipo } }),
    staleTime: 5 * 60_000,
  });
}

export function useCuadreAgro(
  periodo: string,
): UseQueryResult<CuadrePresupuestoAgro> {
  return useQuery({
    queryKey: clavesAgro.cuadre(periodo),
    queryFn: () =>
      peticion<CuadrePresupuestoAgro>("/agro/presupuesto/cuadre", {
        parametros: { periodo },
      }),
    staleTime: 60_000,
  });
}

export function useHistorialAgro(
  periodo: string,
  dimension: DimensionPresupuestoAgro,
): UseQueryResult<HistorialAgro[]> {
  return useQuery({
    queryKey: clavesAgro.historial(periodo, dimension),
    queryFn: () =>
      peticion<HistorialAgro[]>("/agro/presupuesto/historial", {
        parametros: { periodo, dimension },
      }),
    staleTime: 30_000,
  });
}

/**
 * Invalida todo lo que un cambio de presupuesto puede haber movido.
 *
 * El cuadre entra en la lista sin excepción: cambiar una meta de una sola
 * dimensión es exactamente la operación que puede descuadrar las cuatro, y ese
 * aviso no puede quedarse mostrando el estado anterior.
 */
function useInvalidarPresupuestoAgro() {
  const cliente = useQueryClient();
  return () => {
    void cliente.invalidateQueries({ queryKey: ["agro", "presupuesto"] });
    // El presupuesto es el denominador del cumplimiento: los reportes que estén
    // en pantalla ya no valen.
    void cliente.invalidateQueries({ queryKey: ["agro", "reporte"] });
  };
}

export function useGuardarPresupuestoAgro(): UseMutationResult<
  unknown,
  Error,
  EntradaPresupuestoAgro
> {
  const invalidar = useInvalidarPresupuestoAgro();
  return useMutation({
    mutationFn: (datos) =>
      peticion("/agro/presupuesto", { metodo: "PUT", cuerpo: datos }),
    onSuccess: invalidar,
  });
}

export function useEliminarPresupuestoAgro(): UseMutationResult<
  unknown,
  Error,
  { periodo: string; dimension: DimensionPresupuestoAgro; clave: string }
> {
  const invalidar = useInvalidarPresupuestoAgro();
  return useMutation({
    mutationFn: ({ periodo, dimension, clave }) =>
      peticion("/agro/presupuesto", {
        metodo: "DELETE",
        parametros: { periodo, dimension, clave },
      }),
    onSuccess: invalidar,
  });
}

/**
 * Carga masiva: el archivo trae una columna `dimension` por fila.
 *
 * La respuesta incluye el cuadre recién calculado, y la pantalla lo enseña ahí
 * mismo: el momento de ver que las cuatro descomposiciones no dan lo mismo es
 * justo después de subirlas, con el archivo todavía abierto.
 */
export function useCargaMasivaAgro(
  periodo: string,
): UseMutationResult<
  ResultadoCargaAgro,
  Error,
  { archivo: File; motivo: string }
> {
  const invalidar = useInvalidarPresupuestoAgro();
  return useMutation({
    mutationFn: ({ archivo, motivo }) =>
      enviarArchivo<ResultadoCargaAgro>(
        "/agro/presupuesto/carga-masiva",
        archivo,
        {
          periodo,
          motivo,
        },
      ),
    onSuccess: invalidar,
  });
}

// ── Calendario ───────────────────────────────────────────────────────────────

/**
 * Días hábiles por centro de operación.
 *
 * Se consulta también desde la barra de filtros, y no solo desde su pantalla:
 * es la **única** respuesta de la API que publica el código y el nombre de los
 * dos centros juntos, así que es de donde sale el selector de centro. No hay
 * catálogo de dimensiones expuesto (`MiembroDimensionSalida` existe en el
 * esquema pero ningún endpoint lo devuelve), y el resumen solo trae los centros
 * que **vendieron** en el corte, que no es lo mismo que los que existen.
 */
export function useCalendarioAgro(
  periodo: string,
): UseQueryResult<CalendarioAgro[]> {
  return useQuery({
    queryKey: clavesAgro.calendario(periodo),
    queryFn: () =>
      peticion<CalendarioAgro[]>("/agro/calendario", {
        parametros: { periodo },
      }),
    staleTime: 5 * 60_000,
  });
}

export function useGuardarCalendarioAgro(
  periodo: string,
): UseMutationResult<
  unknown,
  Error,
  { centro: string; datos: EntradaCalendarioAgro }
> {
  const cliente = useQueryClient();
  return useMutation({
    mutationFn: ({ centro, datos }) =>
      peticion(`/agro/calendario/${encodeURIComponent(centro)}`, {
        metodo: "PUT",
        parametros: { periodo },
        cuerpo: datos,
      }),
    onSuccess: () => {
      void cliente.invalidateQueries({
        queryKey: clavesAgro.calendario(periodo),
      });
      // Los días hábiles son el denominador del ideal: cambiarlos mueve el
      // semáforo y la proyección de todas las pantallas de la unidad.
      void cliente.invalidateQueries({ queryKey: ["agro", "reporte"] });
    },
  });
}

// ── Ingesta ──────────────────────────────────────────────────────────────────

export function useCorridasAgro(): UseQueryResult<CorridaAgro[]> {
  return useQuery({
    queryKey: clavesAgro.corridas,
    queryFn: () => peticion<CorridaAgro[]>("/agro/ingesta/corridas"),
    staleTime: 30_000,
  });
}

/**
 * Los rechazos de una corrida. **Rol restringido a gerencia.**
 *
 * `habilitado` evita disparar la consulta —y con ella un 403 en la consola— en
 * las sesiones que no lo tienen: los rechazos llevan valores crudos de filas
 * reales, y por eso el backend los cierra con `GerenteDep` y no con `LecturaDep`.
 */
export function useRechazosAgro(
  id: number | null,
  habilitado = true,
): UseQueryResult<RechazoAgro[]> {
  return useQuery({
    queryKey: clavesAgro.rechazos(id ?? 0),
    queryFn: () =>
      peticion<RechazoAgro[]>(`/agro/ingesta/corridas/${id}/rechazos`),
    enabled: id !== null && habilitado,
  });
}

/** Reprocesar un rango lo reemplaza; no duplica. Los dos extremos se incluyen. */
export function useEjecutarIngestaAgro(): UseMutationResult<
  CorridaAgro,
  Error,
  { desde: string; hasta: string }
> {
  const cliente = useQueryClient();
  return useMutation({
    mutationFn: ({ desde, hasta }) =>
      peticion<CorridaAgro>("/agro/ingesta/ejecutar", {
        metodo: "POST",
        parametros: { desde, hasta },
      }),
    onSuccess: () => {
      void cliente.invalidateQueries({ queryKey: ["salud"] });
      // Una ingesta no solo cambia la venta: **crea el catálogo**. Los centros,
      // las especies y los vendedores nacen ahí, así que después de correrla ya
      // no vale nada de lo que hubiera en pantalla —ni los reportes, ni el
      // calendario, ni el presupuesto—.
      //
      // Se invalida el bloque `agro` entero y no una lista de claves. Invalidar
      // por partes es cómo pasó esto: la ingesta avisaba a los reportes y a la
      // sonda, y el calendario seguía sirviendo durante cinco minutos la lista
      // vacía que había pedido *antes* de que existieran los centros. El usuario
      // cargaba 7.037 líneas y la pantalla de días hábiles seguía diciendo «no
      // hay centros registrados todavía».
      void cliente.invalidateQueries({ queryKey: ["agro"] });
    },
  });
}

// ── Presupuesto mensual configurable ──────────────────────────────────────────
//
// Cuatro bloques independientes —comercial, agro distribución, servicio y
// nacional— que **sí se suman** para dar el total mensual. Es lo opuesto al
// presupuesto por dimensiones de arriba, donde las cuatro descomposiciones
// describen el mismo dinero y no se suman. Por eso las claves y las rutas viven
// aparte: `/agro/presupuesto-mensual` y no `/agro/presupuesto`.

/**
 * El presupuesto mensual completo: los cuatro bloques y el total sumado.
 *
 * El total **es la suma de los cuatro bloques**, porque cada bloque es una
 * meta independiente. Esto es lo opuesto al presupuesto por dimensiones, donde
 * las cuatro descomposiciones describen el mismo dinero y no se suman.
 */
export function usePresupuestoMensual(
  periodo: string,
): UseQueryResult<ResumenPresupuestoMensual> {
  return useQuery({
    queryKey: clavesAgro.presupuestoMensual(periodo),
    queryFn: () =>
      peticion<ResumenPresupuestoMensual>("/agro/presupuesto-mensual", {
        parametros: { periodo },
      }),
    staleTime: 60_000,
  });
}

/**
 * Las asignaciones configurables de bloque → vendedor / cliente / categoría.
 *
 * Opcionalmente filtradas por bloque. Es la configuración que hace que la
 * captura sea configurable en lugar de codificada: el negocio decide qué
 * vendedor atiende a qué cliente, en qué bloque y con qué categoría (A–F).
 */
export function useMapeosMensual(
  bloque?: BloqueMensual,
): UseQueryResult<MapeoMensual[]> {
  return useQuery({
    queryKey: clavesAgro.mapeosMensual(bloque),
    queryFn: () =>
      peticion<MapeoMensual[]>("/agro/presupuesto-mensual/mapeos", {
        parametros: { bloque },
      }),
    staleTime: 60_000,
  });
}

/**
 * Crea o actualiza una asignación de bloque.
 *
 * Si `mapeoId` se envía, el backend actualiza la asignación existente; si no,
 * crea una nueva. La unicidad (bloque, vendedor, cliente, categoría) la
 * garantiza la restricción de la tabla y se traduce a 409 por el manejador
 * global.
 */
export function useGuardarMapeoMensual(): UseMutationResult<
  MapeoMensual,
  Error,
  { datos: EntradaMapeoMensual; mapeoId?: number }
> {
  const cliente = useQueryClient();
  return useMutation({
    mutationFn: ({ datos, mapeoId }) =>
      peticion<MapeoMensual>("/agro/presupuesto-mensual/mapeos", {
        metodo: "PUT",
        cuerpo: datos,
        parametros: { mapeo_id: mapeoId },
      }),
    onSuccess: () => {
      void cliente.invalidateQueries({
        queryKey: ["agro", "presupuesto-mensual", "mapeos"],
      });
    },
  });
}

/**
 * Crea o actualiza una fila de presupuesto de commercial, agro_distribucion o
 * nacional.
 *
 * El bloque de servicio no se captura aquí: tiene su propio endpoint porque es
 * un solo valor mensual sin descomposición.
 */
export function useGuardarDetalleMensual(
  periodo: string,
): UseMutationResult<unknown, Error, EntradaDetalleMensual> {
  const cliente = useQueryClient();
  return useMutation({
    mutationFn: (datos) =>
      peticion("/agro/presupuesto-mensual/detalle", {
        metodo: "PUT",
        parametros: { periodo },
        cuerpo: datos,
      }),
    onSuccess: () => {
      void cliente.invalidateQueries({
        queryKey: clavesAgro.presupuestoMensual(periodo),
      });
    },
  });
}

/** Lee el valor mensual del bloque de servicio. */
export function useServicioMensual(
  periodo: string,
): UseQueryResult<ServicioMensual> {
  return useQuery({
    queryKey: clavesAgro.servicioMensual(periodo),
    queryFn: () =>
      peticion<ServicioMensual>("/agro/presupuesto-mensual/servicio", {
        parametros: { periodo },
      }),
    staleTime: 60_000,
  });
}

/** Fija el valor mensual del bloque de servicio: un solo importe por período. */
export function useGuardarServicioMensual(
  periodo: string,
): UseMutationResult<unknown, Error, EntradaServicioMensual> {
  const cliente = useQueryClient();
  return useMutation({
    mutationFn: (datos) =>
      peticion("/agro/presupuesto-mensual/servicio", {
        metodo: "PUT",
        parametros: { periodo },
        cuerpo: datos,
      }),
    onSuccess: () => {
      void cliente.invalidateQueries({
        queryKey: clavesAgro.servicioMensual(periodo),
      });
      void cliente.invalidateQueries({
        queryKey: clavesAgro.presupuestoMensual(periodo),
      });
    },
  });
}

// ── Importación configurable del Excel comercial ──────────────────────────────
//
// El libro anual trae una hoja `RESUMEN (MES)` con los canales como filas y los
// meses `ENE..DIC` como columnas. La importación lee el valor del mes del
// período **tal cual está almacenado** (sin escalar por 1 000) y lo vuelca en
// el bloque **commercial**, mapeando cada canal a vendedor, cliente y categoría
// A–F mediante la configuración de canales. Los canales sin mapeo se rechazan
// con su motivo.

/**
 * Los mapeos de canal del Excel → vendedor / cliente / categoría A–F.
 *
 * Es la configuración que hace que la importación sea configurable en lugar de
 * codificada: el negocio decide a qué vendedor, cliente y categoría pertenece
 * cada canal del Excel.
 */
export function useCanalesMapeosMensual(): UseQueryResult<CanalMapeoMensual[]> {
  return useQuery({
    queryKey: clavesAgro.canalesMapeosMensual,
    queryFn: () =>
      peticion<CanalMapeoMensual[]>(
        "/agro/presupuesto-mensual/canales/mapeos",
      ),
    staleTime: 60_000,
  });
}

/**
 * Crea o actualiza un mapeo de canal.
 *
 * Si `mapeoId` se envía, el backend actualiza el mapeo existente; si no, crea
 * uno nuevo. La unicidad del canal la garantiza la restricción de la tabla y
 * se traduce a 409 por el manejador global.
 */
export function useGuardarCanalMapeoMensual(): UseMutationResult<
  CanalMapeoMensual,
  Error,
  { datos: EntradaCanalMapeoMensual; mapeoId?: number }
> {
  const cliente = useQueryClient();
  return useMutation({
    mutationFn: ({ datos, mapeoId }) =>
      peticion<CanalMapeoMensual>(
        "/agro/presupuesto-mensual/canales/mapeos",
        {
          metodo: "PUT",
          cuerpo: datos,
          parametros: { mapeo_id: mapeoId },
        },
      ),
    onSuccess: () => {
      void cliente.invalidateQueries({
        queryKey: clavesAgro.canalesMapeosMensual,
      });
    },
  });
}

/**
 * Importa el libro anual al bloque **commercial** del período.
 *
 * Lee la hoja `RESUMEN (MES)`, toma el valor del mes del período tal cual está
 * almacenado y, por cada canal del Excel, lo vuelca en una fila de detalle del
 * bloque comercial usando el mapeo configurado. Los canales sin mapeo se
 * rechazan con su motivo. El resultado lista aceptados y rechazados.
 */
export function useImportarComercial(
  periodo: string,
): UseMutationResult<
  ResultadoImportacionComercial,
  Error,
  { archivo: File; motivo: string }
> {
  const cliente = useQueryClient();
  return useMutation({
    mutationFn: ({ archivo, motivo }) =>
      enviarArchivo<ResultadoImportacionComercial>(
        "/agro/presupuesto-mensual/importar-comercial",
        archivo,
        { periodo, motivo },
      ),
    onSuccess: () => {
      // La importación escribe filas del bloque comercial: el resumen mensual
      // entero ya no vale.
      void cliente.invalidateQueries({
        queryKey: clavesAgro.presupuestoMensual(periodo),
      });
    },
  });
}
