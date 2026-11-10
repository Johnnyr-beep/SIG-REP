import type { FilaVentaDiaria } from "@/api/tipos";

export function resumirRangoDiario(
  fila: Pick<FilaVentaDiaria, "valores" | "total" | "documentos">,
  referencias: (string | null)[],
) {
  const diasRango = fila.valores.length;
  const documentosEnRango = fila.documentos.slice(0, diasRango);
  const diasConDocumentos = documentosEnRango.filter(
    (valor) => valor !== null && valor !== undefined,
  ).length;
  const diasConTicket = fila.valores.reduce(
    (total, valor, indice) =>
      valor !== null &&
      fila.documentos[indice] !== null &&
      fila.documentos[indice] !== undefined
        ? total + 1
        : total,
    0,
  );
  const ventaConTicket = fila.valores.reduce((suma, valor, indice) => {
    const documentos = fila.documentos[indice];
    return valor !== null && documentos !== null && documentos !== undefined
      ? suma + Number(valor)
      : suma;
  }, 0);
  const documentosConVenta = fila.valores.reduce((suma, valor, indice) => {
    const documentos = fila.documentos[indice];
    return valor !== null && documentos !== null && documentos !== undefined
      ? suma + documentos
      : suma;
  }, 0);
  const venta = fila.valores.some((valor) => valor !== null) ? fila.total : null;
  const presupuesto =
    referencias.length === diasRango &&
    referencias.length > 0 &&
    referencias.every((valor) => valor !== null)
      ? String(referencias.reduce((suma, valor) => suma + Number(valor), 0))
      : null;
  // Los conteos parciales se muestran junto con los días cubiertos.
  const documentos =
    diasConDocumentos > 0
      ? documentosEnRango.reduce<number>((suma, valor) => suma + (valor ?? 0), 0)
      : null;
  const cumplimiento =
    venta !== null && presupuesto !== null && Number(presupuesto) !== 0
      ? Number(venta) / Number(presupuesto)
      : null;
  const ticketPromedio =
    documentosConVenta > 0
      ? ventaConTicket / documentosConVenta
      : null;

  return {
    venta,
    presupuesto,
    documentos,
    cumplimiento,
    ticketPromedio,
    diasConDocumentos,
    diasConTicket,
    diasRango,
  };
}
