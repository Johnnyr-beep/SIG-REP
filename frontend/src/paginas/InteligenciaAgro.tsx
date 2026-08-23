import { useSearchParams } from "react-router-dom";

import { useInteligenciaAgro } from "@/api/consultasAgro";
import { Cargando, AvisoError, Tarjeta, Vacio } from "@/componentes/comunes";
import { dinero, periodoActual, periodoLargo } from "@/utilidades/formato";

export function InteligenciaAgro() {
  const [parametros, setParametros] = useSearchParams();
  const periodo = parametros.get("periodo") ?? periodoActual();
  const { data, isLoading, error } = useInteligenciaAgro(periodo);

  return (
    <div className="pila">
      <section className="filtros" aria-label="Período de análisis">
        <label className="filtros__campo">
          <span>Período</span>
          <input
            className="campo__control"
            type="month"
            value={periodo}
            onChange={(evento) => {
              const siguientes = new URLSearchParams(parametros);
              siguientes.set("periodo", evento.target.value);
              setParametros(siguientes, { replace: true });
            }}
          />
        </label>
      </section>
      <AvisoError error={error} />
      {isLoading ? <Cargando texto="Analizando comportamiento de compra…" /> : null}
      {data && !data.disponible ? (
        <Vacio titulo="Aún no hay comparación disponible" detalle={data.mensaje} />
      ) : null}
      {data?.disponible ? (
        <>
          <Tarjeta
            titulo={`Alertas de clientes · ${periodoLargo(periodo)}`}
            descripcion={`Comparación contra ${periodoLargo(data.periodo_anterior)}.`}
          >
            {data.alertas.length === 0 ? (
              <Vacio titulo="Sin disminuciones detectadas" />
            ) : (
              <div className="tabla-envoltorio">
                <table className="tabla">
                  <thead><tr><th>Tipo</th><th>Cliente</th><th>Anterior</th><th>Actual</th><th>Detalle</th></tr></thead>
                  <tbody>
                    {data.alertas.map((alerta) => (
                      <tr key={`${alerta.tipo}-${alerta.cliente}`}>
                        <td>{alerta.tipo === "suspendio" ? "Suspendió" : "Disminuyó"}</td>
                        <th scope="row">{alerta.cliente}</th>
                        <td className="numero">{dinero(alerta.venta_anterior)}</td>
                        <td className="numero">{dinero(alerta.venta_actual)}</td>
                        <td>{alerta.detalle}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Tarjeta>
          <Tarjeta titulo="Productos no solicitados">
            {data.productos_no_solicitados.length === 0 ? <Vacio titulo="Sin productos pendientes de recuperar" /> : (
              <ul>
                {data.productos_no_solicitados.map((item) => (
                  <li key={`${item.cliente}-${item.producto}`}><strong>{item.cliente}</strong>: {item.producto} ({dinero(item.venta_anterior)})</li>
                ))}
              </ul>
            )}
          </Tarjeta>
          <Tarjeta titulo="Oportunidades comerciales">
            {data.oportunidades.length === 0 ? <Vacio titulo="Sin oportunidades calculadas" /> : (
              <ul>
                {data.oportunidades.slice(0, 20).map((item) => (
                  <li key={`${item.cliente}-${item.producto}`}><strong>{item.cliente}</strong>: ofrecer {item.producto}. {item.detalle}</li>
                ))}
              </ul>
            )}
          </Tarjeta>
          <Tarjeta titulo="Recomendaciones automáticas">
            <ul>{data.recomendaciones.map((item) => <li key={item.titulo}><strong>{item.titulo}:</strong> {item.detalle}</li>)}</ul>
          </Tarjeta>
        </>
      ) : null}
    </div>
  );
}
