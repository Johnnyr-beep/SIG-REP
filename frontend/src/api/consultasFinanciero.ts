/** Consultas del tablero financiero consolidado (Grupo Santacruz). */

import { useQuery } from "@tanstack/react-query";

import { peticion } from "./cliente";
import type {
  RespuestaBalanceComprobacion,
  RespuestaBalanceGeneral,
  RespuestaCartera,
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
