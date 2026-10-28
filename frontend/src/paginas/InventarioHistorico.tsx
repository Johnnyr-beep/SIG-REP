import { useState } from "react";
import type { FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";

import { peticion } from "@/api/cliente";
import { AvisoError, Cargando, Tarjeta, Vacio } from "@/componentes/comunes";
import { dineroMillones, fecha, fechaHoy, numero } from "@/utilidades/formato";

interface PaginaInventario {
  columnas: string[];
  filas: Record<string, string | null>[];
  total: number;
  limit: number;
  offset: number;
  count: number;
  has_more: boolean;
  next_offset: number | null;
}

const ETIQUETAS: Record<string, string> = {
  Compania: "Compañía", Fecha: "Fecha", Periodo: "Período", CO_Docto: "C.O.",
  Tipo_Docto: "Tipo documento", Nro_Docto: "Documento", Concepto: "Concepto",
  Motivo: "Motivo", Bodega: "Código bodega", Desc_Bodega: "Bodega", Item: "Item ID",
  Referencia: "Referencia", Desc_Item: "Producto", UM: "Unidad", Naturaleza: "Naturaleza",
  Cantidad: "Cantidad", Costo_Total: "Costo total (millones)", Estado_Docto: "Estado documento",
};

function valorCelda(columna: string, valor: string | null | undefined): string {
  if (valor === null || valor === undefined || valor === "") return "—";
  if (columna === "Fecha") return fecha(valor.slice(0, 10));
  if (columna === "Costo_Total") return dineroMillones(valor, 2);
  if (columna === "Cantidad") return numero(valor, 2);
  return valor;
}

export function InventarioHistorico() {
  const hoy = fechaHoy();
  const [desde, setDesde] = useState(`${hoy.slice(0, 7)}-01`);
  const [hasta, setHasta] = useState(hoy);
  const [instalacion, setInstalacion] = useState("");
  const [rango, setRango] = useState<{ desde: string; hasta: string; instalacion: string } | null>(null);
  const [offsets, setOffsets] = useState([0]);
  const offset = offsets[offsets.length - 1] ?? 0;
  const consulta = useQuery({
    queryKey: ["inventario", "historico", rango, offset],
    queryFn: () => peticion<PaginaInventario>("/inventario/historico", {
      parametros: {
        desde: rango!.desde, hasta: rango!.hasta, limit: 100, offset,
        instalacion: rango!.instalacion || undefined,
      },
    }),
    enabled: rango !== null,
    retry: false,
  });
  const datos = consulta.data;

  function consultar(evento: FormEvent) {
    evento.preventDefault();
    if (!desde || !hasta || desde > hasta) return;
    setOffsets([0]);
    if (rango?.desde === desde && rango.hasta === hasta && rango.instalacion === instalacion && offset === 0) {
      void consulta.refetch();
    } else {
      setRango({ desde, hasta, instalacion });
    }
  }

  return (
    <div className="pila">
      <Tarjeta titulo="Inventario histórico" sinRelleno acciones={(
        <form className="formulario formulario--linea" onSubmit={consultar}>
          <label className="campo">
            <span>Instalación</span>
            <select className="campo__control" value={instalacion} onChange={(evento) => {
              const valor = evento.target.value;
              setInstalacion(valor);
              setOffsets([0]);
              if (rango) setRango({ ...rango, instalacion: valor });
            }}>
              <option value="">Todas</option>
              <option value="planta">Planta</option>
              <option value="monteria">Montería</option>
            </select>
          </label>
          <label className="campo">
            <span>Desde</span>
            <input className="campo__control" type="date" required value={desde}
              max={hasta || undefined} onChange={(evento) => setDesde(evento.target.value)} />
          </label>
          <label className="campo">
            <span>Hasta</span>
            <input className="campo__control" type="date" required value={hasta}
              min={desde || undefined} onChange={(evento) => setHasta(evento.target.value)} />
          </label>
          <button className="boton boton--pequeno" type="submit" disabled={consulta.isFetching || !desde || !hasta || desde > hasta}>
            {consulta.isFetching ? "Consultando…" : "Consultar"}
          </button>
        </form>
      )}>
        <AvisoError error={consulta.error} />
        {consulta.isFetching ? <Cargando texto="Consultando inventario histórico…" /> : null}
        {!rango ? <Vacio titulo="Selecciona un período" detalle="Agropecuaria · compañía 3" /> : null}
        {datos && !consulta.isFetching && datos.count === 0 ? (
          <Vacio titulo="Sin movimientos" detalle="No hay movimientos de inventario para este período." />
        ) : null}
        {datos && !consulta.isFetching && datos.count > 0 ? (
          <div className="tabla-envoltorio tabla-envoltorio--alta">
            <table className="tabla tabla--anclada">
              <caption className="solo-lectores">Inventario histórico de Agropecuaria. Movimientos de la compañía 3.</caption>
              <thead><tr>{datos.columnas.map((columna) => (
                <th scope="col" key={columna}>{ETIQUETAS[columna] ?? columna.replaceAll("_", " ")}</th>
              ))}</tr></thead>
              <tbody>{datos.filas.map((fila, indice) => (
                <tr key={offset + indice}>{datos.columnas.map((columna) => (
                  <td key={columna} className={columna === "Cantidad" || columna === "Costo_Total" ? "numero" : undefined}>
                    {valorCelda(columna, fila[columna])}
                  </td>
                ))}</tr>
              ))}</tbody>
            </table>
          </div>
        ) : null}
        {datos && !consulta.isFetching ? (
          <div className="fila" style={{ justifyContent: "space-between", padding: "var(--espacio-4)" }}>
            <span className="tenue">{datos.count ? `${numero(offset + 1)}–${numero(offset + datos.count)} de ` : ""}{numero(datos.total)} movimientos</span>
            <div className="fila">
              <button className="boton boton--pequeno" type="button" disabled={offsets.length <= 1}
                onClick={() => setOffsets((actual) => actual.slice(0, -1))}>Anterior</button>
              <span className="tenue">Página {offsets.length}</span>
              <button className="boton boton--pequeno" type="button" disabled={!datos.has_more || datos.next_offset === null}
                onClick={() => { if (datos.next_offset !== null) setOffsets((actual) => [...actual, datos.next_offset!]); }}>Siguiente</button>
            </div>
          </div>
        ) : null}
      </Tarjeta>
    </div>
  );
}