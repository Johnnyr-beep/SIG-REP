import { useSearchParams } from "react-router-dom";

import { useInteligenciaAgro } from "@/api/consultasAgro";
import type { AlertaComercial } from "@/api/tiposAgro";
import { AvisoError, Cargando, Tarjeta, Vacio } from "@/componentes/comunes";
import { Indicador } from "@/componentes/indicadores";
import { dinero, periodoActual, periodoLargo } from "@/utilidades/formato";

export function InteligenciaAgro() {
  const [parametros, setParametros] = useSearchParams();
  const periodo = parametros.get("periodo") ?? periodoActual();
  const { data, isLoading, error } = useInteligenciaAgro(periodo);
  const suspendidos = data?.alertas.filter((alerta) => alerta.tipo === "suspendio") ?? [];
  const disminuyeron = data?.alertas.filter((alerta) => alerta.tipo === "disminuyo") ?? [];

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
          <section className="inteligencia__encabezado">
            <div>
              <p className="inteligencia__eyebrow">Comparación mensual</p>
              <h2>Prioridades para {periodoLargo(periodo)}</h2>
              <p className="suave">
                Frente a {periodoLargo(data.periodo_anterior)}, ordenadas para
                convertir señales de compra en acciones comerciales.
              </p>
            </div>
          </section>

          <section className="rejilla rejilla--indicadores" aria-label="Prioridades">
            <Indicador
              etiqueta="Clientes suspendidos"
              valor={suspendidos.length}
              nota="Contactar primero, antes de perder la relación comercial."
              tono="peligro"
            />
            <Indicador
              etiqueta="Clientes con caída"
              valor={disminuyeron.length}
              nota="Compran menos de 80 % frente al mes anterior."
              tono="aviso"
            />
            <Indicador
              etiqueta="Productos por recuperar"
              valor={data.productos_no_solicitados.length}
              nota="Antes comprados, ahora ausentes del pedido."
              tono="aviso"
            />
            <Indicador
              etiqueta="Oportunidades"
              valor={data.oportunidades.length}
              nota="Productos con demanda que aún no compra ese cliente."
              tono="exito"
            />
          </section>

          <Tarjeta
            titulo="1. Recuperación prioritaria"
            descripcion="Clientes con mayor riesgo de pérdida, ordenados por venta histórica."
          >
            <ListaAlertas alertas={data.alertas.slice(0, 12)} />
          </Tarjeta>

          <div className="inteligencia__dos-columnas">
            <Tarjeta
              titulo="2. Productos por recuperar"
              descripcion="Llévelos a la próxima conversación con cada cliente."
            >
              {data.productos_no_solicitados.length === 0 ? (
                <Vacio titulo="Sin productos pendientes de recuperar" />
              ) : (
                <ul className="lista-simple">
                  {data.productos_no_solicitados.slice(0, 12).map((item) => (
                    <li key={`${item.cliente}-${item.producto}`}>
                      <span>
                        <strong>{item.cliente}</strong>
                        <span className="suave"> · {item.producto}</span>
                      </span>
                      <strong className="empujar numero">
                        {dinero(item.venta_anterior)}
                      </strong>
                    </li>
                  ))}
                </ul>
              )}
            </Tarjeta>

            <Tarjeta
              titulo="3. Oportunidades de venta"
              descripcion="Productos que ya tienen demanda en otros clientes."
            >
              {data.oportunidades.length === 0 ? (
                <Vacio titulo="Sin oportunidades calculadas" />
              ) : (
                <ul className="lista-simple">
                  {data.oportunidades.slice(0, 12).map((item) => (
                    <li key={`${item.cliente}-${item.producto}`}>
                      <span>
                        <strong>{item.cliente}</strong>
                        <span className="suave"> · ofrecer {item.producto}</span>
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </Tarjeta>
          </div>

          <Tarjeta
            titulo="4. Plan de acción"
            descripcion="Recomendaciones automáticas basadas en las alertas de este período."
          >
            <ol className="inteligencia__plan">
              {data.recomendaciones.map((item) => (
                <li key={item.titulo}>
                  <strong>{item.titulo}</strong>
                  <span>{item.detalle}</span>
                </li>
              ))}
            </ol>
          </Tarjeta>
        </>
      ) : null}
    </div>
  );
}

function ListaAlertas({ alertas }: { alertas: AlertaComercial[] }) {
  if (alertas.length === 0) return <Vacio titulo="Sin disminuciones detectadas" />;

  return (
    <div className="tabla-envoltorio">
      <table className="tabla">
        <thead>
          <tr>
            <th>Señal</th>
            <th>Cliente</th>
            <th className="numero">Mes anterior</th>
            <th className="numero">Mes actual</th>
            <th>Acción sugerida</th>
          </tr>
        </thead>
        <tbody>
          {alertas.map((alerta) => (
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
  );
}
