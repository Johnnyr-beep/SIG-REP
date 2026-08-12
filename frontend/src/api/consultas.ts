/**
 * Hooks de datos sobre TanStack Query.
 *
 * Toda llamada a la API pasa por aquí: los componentes no conocen rutas ni
 * verbos HTTP, solo hooks con nombre de negocio. Cambiar un endpoint es tocar
 * este archivo, no ocho pantallas.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { UseMutationResult, UseQueryResult } from "@tanstack/react-query";

import { descargar, enviarArchivo, peticion } from "./cliente";
import type { ValorParametro } from "./cliente";
import type {
  CambioPresupuesto,
  Categoria,
  CorridaIngesta,
  CorteClientes,
  EntradaCalendario,
  EntradaIngesta,
  EntradaPresupuesto,
  FilaCalendario,
  FilaPresupuesto,
  Grupo,
  MapeoCategoria,
  Medida,
  Periodo,
  PuntoVenta,
  RechazoIngesta,
  RespuestaClientes,
  RespuestaCumplimiento,
  RespuestaTablero,
  RespuestaVentaDiaria,
  ResultadoCargaMasiva,
  Salud,
  Usuario,
  Zona,
} from "./tipos";

/** Filtros comunes a todos los reportes (§ «Reportes» del contrato). */
export interface FiltrosReporte {
  /** Obligatorio. `YYYY-MM`. */
  periodo: string;
  /** Fecha de corte. Ausente = hoy, según el contrato. */
  hasta?: string;
  grupo?: string;
  punto_venta?: string;
  categoria?: string;
  medida: Medida;
}

function comoParametros(filtros: FiltrosReporte): Record<string, ValorParametro> {
  return {
    periodo: filtros.periodo,
    hasta: filtros.hasta,
    grupo: filtros.grupo,
    punto_venta: filtros.punto_venta,
    categoria: filtros.categoria,
    medida: filtros.medida,
  };
}

/** Claves de caché centralizadas para poder invalidar con precisión. */
export const claves = {
  perfil: ["perfil"] as const,
  salud: ["salud"] as const,
  grupos: ["catalogo", "grupos"] as const,
  puntosVenta: ["catalogo", "puntos-venta"] as const,
  categorias: ["catalogo", "categorias"] as const,
  zonas: ["catalogo", "zonas"] as const,
  mapeoCategorias: ["catalogo", "mapeo-categorias"] as const,
  calendario: (periodo: string) => ["calendario", periodo] as const,
  presupuesto: (periodo: string, puntoVenta: string) =>
    ["presupuesto", periodo, puntoVenta] as const,
  historialPresupuesto: (periodo: string, puntoVenta: string) =>
    ["presupuesto-historial", periodo, puntoVenta] as const,
  periodos: ["periodos"] as const,
  tablero: (filtros: FiltrosReporte) => ["reporte", "tablero", filtros] as const,
  cumplimiento: (filtros: FiltrosReporte) => ["reporte", "cumplimiento", filtros] as const,
  ventaDiaria: (filtros: FiltrosReporte) => ["reporte", "venta-diaria", filtros] as const,
  clientes: (filtros: FiltrosReporte, por: CorteClientes) =>
    ["reporte", "clientes", por, filtros] as const,
  corridas: ["ingesta", "corridas"] as const,
  rechazos: (id: number) => ["ingesta", "rechazos", id] as const,
};

// ── Sesión y salud ───────────────────────────────────────────────────────────

export function usePerfil(habilitado: boolean): UseQueryResult<Usuario> {
  return useQuery({
    queryKey: claves.perfil,
    queryFn: () => peticion<Usuario>("/auth/yo"),
    enabled: habilitado,
    staleTime: 5 * 60_000,
    retry: false,
  });
}

export function useSalud(): UseQueryResult<Salud> {
  return useQuery({
    queryKey: claves.salud,
    queryFn: () => peticion<Salud>("/salud"),
    staleTime: 60_000,
    retry: false,
  });
}

// ── Catálogos ────────────────────────────────────────────────────────────────

/** Los catálogos cambian de mes en mes, no de minuto en minuto. */
const CACHE_CATALOGO = 30 * 60_000;

export function useGrupos(): UseQueryResult<Grupo[]> {
  return useQuery({
    queryKey: claves.grupos,
    queryFn: () => peticion<Grupo[]>("/catalogos/grupos"),
    staleTime: CACHE_CATALOGO,
  });
}

export function usePuntosVenta(): UseQueryResult<PuntoVenta[]> {
  return useQuery({
    queryKey: claves.puntosVenta,
    queryFn: () => peticion<PuntoVenta[]>("/catalogos/puntos-venta"),
    staleTime: CACHE_CATALOGO,
  });
}

export function useCategorias(): UseQueryResult<Categoria[]> {
  return useQuery({
    queryKey: claves.categorias,
    queryFn: () => peticion<Categoria[]>("/catalogos/categorias"),
    staleTime: CACHE_CATALOGO,
  });
}

export function useZonas(): UseQueryResult<Zona[]> {
  return useQuery({
    queryKey: claves.zonas,
    queryFn: () => peticion<Zona[]>("/catalogos/zonas"),
    staleTime: CACHE_CATALOGO,
  });
}

export function useMapeoCategorias(habilitado = true): UseQueryResult<MapeoCategoria[]> {
  return useQuery({
    queryKey: claves.mapeoCategorias,
    queryFn: () => peticion<MapeoCategoria[]>("/catalogos/mapeo-categorias"),
    enabled: habilitado,
    staleTime: CACHE_CATALOGO,
  });
}

// ── Reportes ─────────────────────────────────────────────────────────────────

export function useTablero(filtros: FiltrosReporte): UseQueryResult<RespuestaTablero> {
  return useQuery({
    queryKey: claves.tablero(filtros),
    queryFn: () => peticion<RespuestaTablero>("/reportes/tablero", { parametros: comoParametros(filtros) }),
    staleTime: 60_000,
  });
}

export function useCumplimiento(filtros: FiltrosReporte): UseQueryResult<RespuestaCumplimiento> {
  return useQuery({
    queryKey: claves.cumplimiento(filtros),
    queryFn: () =>
      peticion<RespuestaCumplimiento>("/reportes/cumplimiento", { parametros: comoParametros(filtros) }),
    staleTime: 60_000,
  });
}

export function useVentaDiaria(filtros: FiltrosReporte): UseQueryResult<RespuestaVentaDiaria> {
  return useQuery({
    queryKey: claves.ventaDiaria(filtros),
    queryFn: () =>
      peticion<RespuestaVentaDiaria>("/reportes/venta-diaria", { parametros: comoParametros(filtros) }),
    staleTime: 60_000,
  });
}

export function useClientes(
  filtros: FiltrosReporte,
  por: CorteClientes,
): UseQueryResult<RespuestaClientes> {
  return useQuery({
    queryKey: claves.clientes(filtros, por),
    queryFn: () =>
      peticion<RespuestaClientes>("/reportes/clientes", {
        parametros: { ...comoParametros(filtros), por },
      }),
    staleTime: 60_000,
  });
}

/**
 * Exporta el reporte visible a `.xlsx` con los mismos filtros de la pantalla.
 *
 * No es una consulta: es un efecto que descarga un archivo, así que se modela
 * como mutación para tener estados de envío y error sin ensuciar la caché.
 */
export function useExportar(): UseMutationResult<
  void,
  Error,
  { reporte: string; filtros: FiltrosReporte; extra?: Record<string, ValorParametro> }
> {
  return useMutation({
    mutationFn: ({ reporte, filtros, extra }) =>
      descargar(
        `/reportes/${reporte}/exportar`,
        { ...comoParametros(filtros), ...extra },
        `sigrep-${reporte}-${filtros.periodo}.xlsx`,
      ),
  });
}

// ── Calendario ───────────────────────────────────────────────────────────────

export function useCalendario(periodo: string): UseQueryResult<FilaCalendario[]> {
  return useQuery({
    queryKey: claves.calendario(periodo),
    queryFn: () => peticion<FilaCalendario[]>("/calendario", { parametros: { periodo } }),
    staleTime: 5 * 60_000,
  });
}

export function useGuardarCalendario(
  periodo: string,
): UseMutationResult<void, Error, { zonaId: number; datos: EntradaCalendario }> {
  const cliente = useQueryClient();
  return useMutation({
    mutationFn: ({ zonaId, datos }) =>
      peticion<void>(`/calendario/${zonaId}`, {
        metodo: "PUT",
        parametros: { periodo },
        cuerpo: datos,
      }),
    onSuccess: () => {
      void cliente.invalidateQueries({ queryKey: claves.calendario(periodo) });
      // Los días hábiles son el denominador del ideal: cambiarlos mueve todos
      // los indicadores de todas las pantallas.
      void cliente.invalidateQueries({ queryKey: ["reporte"] });
    },
  });
}

// ── Presupuesto ──────────────────────────────────────────────────────────────

export function usePresupuesto(
  periodo: string,
  puntoVenta: string,
): UseQueryResult<FilaPresupuesto[]> {
  return useQuery({
    queryKey: claves.presupuesto(periodo, puntoVenta),
    queryFn: () =>
      peticion<FilaPresupuesto[]>("/presupuesto", {
        parametros: { periodo, punto_venta: puntoVenta },
      }),
    enabled: puntoVenta !== "",
    staleTime: 60_000,
  });
}

export function useHistorialPresupuesto(
  periodo: string,
  puntoVenta: string,
): UseQueryResult<CambioPresupuesto[]> {
  return useQuery({
    queryKey: claves.historialPresupuesto(periodo, puntoVenta),
    queryFn: () =>
      peticion<CambioPresupuesto[]>("/presupuesto/historial", {
        parametros: { periodo, punto_venta: puntoVenta },
      }),
    enabled: puntoVenta !== "",
    staleTime: 30_000,
  });
}

/** Invalida todo lo que un cambio de presupuesto puede haber movido. */
function useInvalidarPresupuesto(periodo: string, puntoVenta: string) {
  const cliente = useQueryClient();
  return () => {
    void cliente.invalidateQueries({ queryKey: claves.presupuesto(periodo, puntoVenta) });
    void cliente.invalidateQueries({ queryKey: claves.historialPresupuesto(periodo, puntoVenta) });
    void cliente.invalidateQueries({ queryKey: ["presupuesto"] });
    void cliente.invalidateQueries({ queryKey: ["reporte"] });
  };
}

export function useGuardarPresupuesto(
  periodo: string,
  puntoVenta: string,
): UseMutationResult<void, Error, EntradaPresupuesto> {
  const invalidar = useInvalidarPresupuesto(periodo, puntoVenta);
  return useMutation({
    mutationFn: (datos) => peticion<void>("/presupuesto", { metodo: "PUT", cuerpo: datos }),
    onSuccess: invalidar,
  });
}

export function useCargaMasivaPresupuesto(
  periodo: string,
  puntoVenta: string,
): UseMutationResult<ResultadoCargaMasiva, Error, File> {
  const invalidar = useInvalidarPresupuesto(periodo, puntoVenta);
  return useMutation({
    mutationFn: (archivo) =>
      enviarArchivo<ResultadoCargaMasiva>("/presupuesto/carga-masiva", archivo, { periodo }),
    onSuccess: invalidar,
  });
}

export function usePeriodos(): UseQueryResult<Periodo[]> {
  return useQuery({
    queryKey: claves.periodos,
    queryFn: () => peticion<Periodo[]>("/periodos"),
    staleTime: 5 * 60_000,
  });
}

export function useCerrarPeriodo(): UseMutationResult<Periodo, Error, string> {
  const cliente = useQueryClient();
  return useMutation({
    mutationFn: (periodo) => peticion<Periodo>(`/periodos/${periodo}/cerrar`, { metodo: "POST" }),
    onSuccess: () => {
      void cliente.invalidateQueries({ queryKey: claves.periodos });
      void cliente.invalidateQueries({ queryKey: ["presupuesto"] });
    },
  });
}

// ── Ingesta ──────────────────────────────────────────────────────────────────

export function useCorridasIngesta(): UseQueryResult<CorridaIngesta[]> {
  return useQuery({
    queryKey: claves.corridas,
    queryFn: () => peticion<CorridaIngesta[]>("/ingesta/corridas"),
    staleTime: 30_000,
  });
}

export function useRechazosIngesta(id: number | null): UseQueryResult<RechazoIngesta[]> {
  return useQuery({
    queryKey: claves.rechazos(id ?? 0),
    queryFn: () => peticion<RechazoIngesta[]>(`/ingesta/corridas/${id}/rechazos`),
    enabled: id !== null,
  });
}

function useInvalidarIngesta() {
  const cliente = useQueryClient();
  return () => {
    void cliente.invalidateQueries({ queryKey: claves.corridas });
    void cliente.invalidateQueries({ queryKey: claves.salud });
    // Una ingesta cambia la venta: los reportes que estén en pantalla ya no valen.
    void cliente.invalidateQueries({ queryKey: ["reporte"] });
  };
}

export function useEjecutarIngesta(): UseMutationResult<unknown, Error, EntradaIngesta> {
  const invalidar = useInvalidarIngesta();
  return useMutation({
    mutationFn: (datos) => peticion("/ingesta/ejecutar", { metodo: "POST", cuerpo: datos }),
    onSuccess: invalidar,
  });
}

export function useIngestaArchivo(): UseMutationResult<unknown, Error, File> {
  const invalidar = useInvalidarIngesta();
  return useMutation({
    mutationFn: (archivo) => enviarArchivo("/ingesta/archivo", archivo),
    onSuccess: invalidar,
  });
}
