import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { peticion } from "./cliente";
import type { AgroTatIngesta, AgroTatResumen } from "./tipos";

export interface FiltrosTat {
  fecha_inicio: string;
  fecha_fin: string;
  limit?: number;
  offset?: number;
}

export function useVentasTat(filtros: FiltrosTat) {
  return useQuery({
    queryKey: ["agro", "tat", filtros],
    queryFn: () => peticion<AgroTatResumen>("/agro/tat", { parametros: { ...filtros } }),
    enabled: Boolean(filtros.fecha_inicio && filtros.fecha_fin),
  });
}

export function useIngestarTat() {
  const cliente = useQueryClient();
  return useMutation({
    mutationFn: (filtros: Pick<FiltrosTat, "fecha_inicio" | "fecha_fin">) =>
      peticion<AgroTatIngesta>("/agro/tat/ingesta", {
        metodo: "POST",
        cuerpo: filtros,
      }),
    onSuccess: () => cliente.invalidateQueries({ queryKey: ["agro", "tat"] }),
  });
}