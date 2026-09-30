import { useState } from "react";

import { useVentasTat } from "@/api/consultasTat";
import type { FiltrosTat } from "@/api/consultasTat";
import { AvisoError, Cargando, Tarjeta, Vacio } from "@/componentes/comunes";
import { dinero, fechaHoy, numero } from "@/utilidades/formato";

export function VentasTat() {
  const hoy = fechaHoy();
  const [fechaInicio, setFechaInicio] = useState(hoy.slice(0, 8) + "01");
  const [fechaFin, setFechaFin] = useState(hoy);
  const [tipoComercial, setTipoComercial] = useState("");
  const filtros: FiltrosTat = {
    fecha_inicio: fechaInicio,
    fecha_fin: fechaFin,
    tipo_comercial: tipoComercial || undefined,
  };
  const [filtrosConsultados, setFiltrosConsultados] = useState<FiltrosTat>(filtros);
  const consulta = useVentasTat(filtrosConsultados);

  return (
    <div className="pila">
      <Tarjeta
        titulo="Ventas TAT"
        descripcion="Facturación de Agropecuaria por sucursal y cliente."
        acciones={
          <div className="ventas-tat__resumen" aria-live="polite">
            <div className="indicador">
              <span className="indicador__etiqueta">Cantidad total</span>
              <strong className="indicador__valor indicador__valor--mediano">
                {consulta.data ? numero(consulta.data.total_cantidad, 2) : "—"}
              </strong>
            </div>
            <div className="indicador indicador--exito">
              <span className="indicador__etiqueta">Venta subtotal</span>
              <strong className="indicador__valor indicador__valor--mediano">
                {consulta.data ? dinero(consulta.data.total_subtotal) : "—"}
              </strong>
            </div>
          </div>
        }
      >
        <form
          className="formulario formulario--linea"
          onSubmit={(evento) => {
            evento.preventDefault();
            setFiltrosConsultados(filtros);
          }}
        >
          <label className="campo">
            <span>Fecha inicial</span>
            <input className="campo__control" type="date" value={fechaInicio} onChange={(evento) => setFechaInicio(evento.target.value)} required />
          </label>
          <label className="campo">
            <span>Fecha final</span>
            <input className="campo__control" type="date" value={fechaFin} min={fechaInicio} onChange={(evento) => setFechaFin(evento.target.value)} required />
          </label>
          <label className="campo">
            <span>Tipo comercial</span>
            <select
              className="campo__control"
              value={tipoComercial}
              onChange={(evento) => setTipoComercial(evento.target.value)}
            >
              <option value="">Todos</option>
              {(consulta.data?.tipos_comerciales ?? []).map((tipo) => (
                <option key={tipo} value={tipo}>
                  {tipo}
                </option>
              ))}
            </select>
          </label>
          <button type="submit" className="boton">Consultar</button>
        </form>
      </Tarjeta>

      <AvisoError error={consulta.error} />
      {consulta.isLoading ? <Cargando texto="Cargando ventas TAT…" /> : null}
      {consulta.data ? (
        <Tarjeta titulo={`${numero(consulta.data.filas.length)} facturas`} sinRelleno>
          {consulta.data.filas.length === 0 ? (
            <Vacio titulo="No hay ventas en este rango" detalle="Ajuste las fechas para consultar otro período." />
          ) : (
            <div className="tabla-envoltorio">
              <table className="tabla tabla--compacta tabla--ventas-tat">
                <thead>
                  <tr>
                    <th>Fecha</th><th>Documento</th><th>Sucursal</th><th>Cliente</th>
                    <th>Tipo comercial</th><th className="numero">Cantidad</th><th className="numero">Venta subtotal</th>
                  </tr>
                </thead>
                <tbody>
                  {consulta.data.filas.map((fila) => (
                    <tr key={`${fila.fecha_documento}-${fila.nro_documento}-${fila.cliente_factura}`}>
                      <td>{fila.fecha_documento}</td>
                      <td className="mono">{fila.nro_documento}</td>
                      <td>{fila.descripcion_sucursal ?? fila.codigo_sucursal ?? "—"}</td>
                      <td>{fila.razon_social_cliente ?? fila.cliente_factura ?? "—"}</td>
                      <td>{fila.tipo_comercial ?? "—"}</td>
                      <td className="numero">{fila.cantidad_inv}</td>
                      <td className="numero">{fila.valor_subtotal}</td>
                    </tr>
                  ))}
                </tbody>
                <tfoot><tr><th colSpan={5}>Total</th><th className="numero">{consulta.data.total_cantidad}</th><th className="numero">{consulta.data.total_subtotal}</th></tr></tfoot>
              </table>
            </div>
          )}
        </Tarjeta>
      ) : null}
    </div>
  );
}