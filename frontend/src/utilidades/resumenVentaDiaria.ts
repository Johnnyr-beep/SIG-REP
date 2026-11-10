import type { FilaVentaDiaria } from "@/api/tipos";

export function resumirRangoDiario(
  fila: Pick<FilaVentaDiaria, "valores" | "total" | "documentos">,
  referencias: (string | null)[],
) {
  const venta = fila.valores.some((valor) => valor !== null) ? fila.total : null;
  const presupuesto =
    referencias.length === fila.valores.length &&
    referencias.length > 0 &&
    referencias.every((valor) => valor !== null)
      ? String(referencias.reduce((suma, valor) => suma + Number(valor), 0))
      : null;
  // Un conteo parcial no puede presentarse como el total del rango.
  const documentos =
    fila.documentos.length === fila.valores.length &&
    fila.documentos.length > 0 &&
    fila.documentos.every((valor) => valor !== null)
      ? fila.documentos.reduce<number>((suma, valor) => suma + (valor ?? 0), 0)
      : null;
  const cumplimiento =
    venta !== null && presupuesto !== null && Number(presupuesto) !== 0
      ? Number(venta) / Number(presupuesto)
      : null;
  const ticketPromedio =
    venta !== null && documentos !== null && documentos > 0
      ? Number(venta) / documentos
      : null;

  return { venta, presupuesto, documentos, cumplimiento, ticketPromedio };
}
