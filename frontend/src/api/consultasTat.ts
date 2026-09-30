import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { peticion } from "./cliente";
import type { AgroTatIngesta, AgroTatResumen } from "./tipos";

export interface FiltrosTat {
  fecha_inicio: string;
  fecha_fin: string;
  tipo_comercial?: string;
  limit?: number;
  offset?: number;
}

const LIMITE_PAGINA_TAT = 500;

async function consultarVentasTat(filtros: FiltrosTat): Promise<AgroTatResumen> {
  const limite = filtros.limit ?? LIMITE_PAGINA_TAT;
  const offsetInicial = filtros.offset ?? 0;
  const parametros = { ...filtros, limit: limite, offset: offsetInicial };
  const primera = await peticion<AgroTatResumen>("/agro/tat", {
    parametros,
  });

  if (filtros.limit !== undefined || primera.filas.length < limite) {
    return primera;
  }

  const filas = [...primera.filas];
  let offset = offsetInicial + primera.filas.length;
  while (primera.filas.length === limite) {
    const pagina = await peticion<AgroTatResumen>("/agro/tat", {
      parametros: { ...parametros, offset },
    });
    filas.push(...pagina.filas);
    offset += pagina.filas.length;
    if (pagina.filas.length < limite) break;
  }

  return { ...primera, filas };
}

export function useVentasTat(filtros: FiltrosTat, habilitado = true) {
  return useQuery({
    queryKey: ["agro", "tat", filtros],
    queryFn: () => consultarVentasTat(filtros),
    enabled: habilitado && Boolean(filtros.fecha_inicio && filtros.fecha_fin),
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