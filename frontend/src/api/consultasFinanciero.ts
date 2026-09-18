/** Consultas del tablero financiero consolidado (Grupo Santacruz). */

import { useQueries, useQuery } from "@tanstack/react-query";

import { peticion } from "./cliente";
import type {
  RespuestaBalanceComprobacion,
  RespuestaBalanceGeneral,
  RespuestaCartera,
  RespuestaDetalleCuentas,
  RespuestaEstadoResultados,
  RespuestaIndicadoresFinancieros,
} from "./tipos";

export interface FiltrosFinanciero {
  periodo: string;
  cia?: number | null;
}

function parametrosDe(filtros: FiltrosFinanciero) {
  return { periodo: filtros.periodo, cia: filtros.cia ?? undefined };
}

export function useBalanceGeneral(filtros: FiltrosFinanciero, habilitado = true) {
  return useQuery({
    queryKey: ["financiero", "balance-general", filtros],
    queryFn: () =>
      peticion<RespuestaBalanceGeneral>("/financiero/balance-general", {
        parametros: parametrosDe(filtros),
      }),
    enabled: habilitado && Boolean(filtros.periodo),
  });
}

export function useEstadoResultados(filtros: FiltrosFinanciero, habilitado = true) {
  return useQuery({
    queryKey: ["financiero", "estado-resultados", filtros],
    queryFn: () =>
      peticion<RespuestaEstadoResultados>("/financiero/estado-resultados", {
        parametros: parametrosDe(filtros),
      }),
    enabled: habilitado && Boolean(filtros.periodo),
  });
}

export function useIndicadoresFinancieros(filtros: FiltrosFinanciero, habilitado = true) {
  return useQuery({
    queryKey: ["financiero", "indicadores", filtros],
    queryFn: () =>
      peticion<RespuestaIndicadoresFinancieros>("/financiero/indicadores", {
        parametros: parametrosDe(filtros),
      }),
    enabled: habilitado && Boolean(filtros.periodo),
  });
}

export function useCartera(filtros: FiltrosFinanciero, habilitado = true) {
  return useQuery({
    queryKey: ["financiero", "cartera", filtros],
    queryFn: () =>
      peticion<RespuestaCartera>("/financiero/cartera", {
        parametros: parametrosDe(filtros),
      }),
    enabled: habilitado && Boolean(filtros.periodo),
  });
}

export function useBalanceComprobacion(filtros: FiltrosFinanciero, habilitado = true) {
  return useQuery({
    queryKey: ["financiero", "balance-comprobacion", filtros],
    queryFn: () =>
      peticion<RespuestaBalanceComprobacion>("/financiero/balance-comprobacion", {
        parametros: parametrosDe(filtros),
      }),
    enabled: habilitado && Boolean(filtros.periodo),
  });
}

export interface FiltrosDetalleCuentas extends FiltrosFinanciero {
  centro_costo?: string | null;
  mayor_iii?: string | null;
}

export function useDetalleCuentas(filtros: FiltrosDetalleCuentas, habilitado = true) {
  return useQuery({
    queryKey: ["financiero", "detalle-cuentas", filtros],
    queryFn: () =>
      peticion<RespuestaDetalleCuentas>("/financiero/detalle-cuentas", {
        parametros: {
          periodo: filtros.periodo,
          cia: filtros.cia ?? undefined,
          centro_costo: filtros.centro_costo ?? undefined,
          mayor_iii: filtros.mayor_iii ?? undefined,
        },
      }),
    enabled: habilitado && Boolean(filtros.periodo),
  });
}

/**
 * El estado de resultados de varios períodos a la vez, para la tendencia.
 *
 * Una petición por período —el backend no tiene un endpoint de serie— en
 * paralelo con `useQueries`: nueve meses cargados son nueve peticiones
 * pequeñas, no una sola pesada.
 */
export function useSerieEstadoResultados(periodos: string[]) {
  return useQueries({
    queries: periodos.map((periodo) => ({
      queryKey: ["financiero", "estado-resultados", { periodo }],
      queryFn: () =>
        peticion<RespuestaEstadoResultados>("/financiero/estado-resultados", {
          parametros: { periodo },
        }),
    })),
  });
}

/** Igual que `useSerieEstadoResultados`, para el análisis horizontal del balance. */
export function useSerieBalanceGeneral(periodos: string[]) {
  return useQueries({
    queries: periodos.map((periodo) => ({
      queryKey: ["financiero", "balance-general", { periodo }],
      queryFn: () =>
        peticion<RespuestaBalanceGeneral>("/financiero/balance-general", {
          parametros: { periodo },
        }),
    })),
  });
}
