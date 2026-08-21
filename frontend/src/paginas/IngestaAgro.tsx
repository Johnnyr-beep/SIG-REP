/**
 * Carga de la venta agropecuaria desde la API de consulta, y su bitácora.
 *
 * Reprocesar un rango lo **reemplaza**, no lo duplica: la ingesta es idempotente
 * y la pantalla lo dice, porque sin esa frase nadie se atreve a volver a cargar
 * un día que salió raro.
 *
 * La columna que más se malinterpreta es `impuesto`, y por eso lleva su
 * explicación al lado: cuenta filas que están **dentro** de las aceptadas —se
 * guardan, marcadas— y que no suman en ningún total, porque el impuesto no es
 * venta sino recaudo a nombre de terceros. Sin esa nota, la cifra se lee como un
 * fallo de la carga. Y no coincide con `impuesto_lineas` de la conciliación, que
 * suma líneas facturadas y no filas: en la primera carga real fueron 170 filas y
 * 180 líneas.
 */

import { useState } from "react";

import {
  useCorridasAgro,
  useEjecutarIngestaAgro,
  useRechazosAgro,
} from "@/api/consultasAgro";
import { useSalud } from "@/api/consultas";
import { useAuth } from "@/auth/ContextoAuth";
import {
  AvisoError,
  Cargando,
  Distintivo,
  Tarjeta,
  Vacio,
} from "@/componentes/comunes";
import { fechaHora, fechaHoy, humanizar, numero } from "@/utilidades/formato";

export function IngestaAgro() {
  const { data: corridas, isLoading, error } = useCorridasAgro();
  const { data: salud } = useSalud();
  const { tieneRol } = useAuth();
  const ejecutar = useEjecutarIngestaAgro();

  const hoy = fechaHoy();
  const [desde, setDesde] = useState(hoy.slice(0, 8) + "01");
  const [hasta, setHasta] = useState(hoy);
  const [verRechazos, setVerRechazos] = useState<number | null>(null);

  const puedeCargar = tieneRol("ADMIN", "GERENTE", "ANALISTA");
  const ultima = corridas?.[0];

  return (
    <div className="pila">
      <Tarjeta
        titulo="Cargar venta desde SIESA"
        descripcion={
          <>
            Compañía 3 · <code>/ventas/agropecuaria</code>. Los dos extremos del
            rango se incluyen.{" "}
            <strong>Reprocesar un rango lo reemplaza, no lo duplica</strong>,
            así que volver a cargar un día ya cargado es seguro.
          </>
        }
      >
        <form
          className="formulario formulario--linea"
          onSubmit={(evento) => {
            evento.preventDefault();
            ejecutar.mutate({ desde, hasta });
          }}
        >
          <label className="campo">
            <span>Desde</span>
            <input
              className="campo__control"
              type="date"
              value={desde}
              onChange={(evento) => setDesde(evento.target.value)}
              required
            />
          </label>
          <label className="campo">
            <span>Hasta</span>
            <input
              className="campo__control"
              type="date"
              value={hasta}
              min={desde}
              onChange={(evento) => setHasta(evento.target.value)}
              required
            />
          </label>
          <button
            type="submit"
            className="boton"
            disabled={ejecutar.isPending || !puedeCargar}
            title={
              puedeCargar
                ? undefined
                : "Requiere el rol ADMIN, GERENTE o ANALISTA."
            }
          >
            {ejecutar.isPending ? "Cargando…" : "Ejecutar ingesta"}
          </button>
        </form>

        <dl className="datos">
          <div>
            <dt>Última carga</dt>
            <dd>
              {fechaHora(salud?.ultima_ingesta ?? ultima?.cuando ?? null)}
            </dd>
          </div>
          <div>
            <dt>Estado del sistema</dt>
            <dd>
              {salud ? humanizar(salud.estado) : "—"}
              <span className="tenue">
                {salud
                  ? ` · ${salud.base_datos} · versión ${salud.version}`
                  : ""}
              </span>
            </dd>
          </div>
        </dl>
      </Tarjeta>

      <AvisoError error={error} />
      <AvisoError error={ejecutar.error} />

      {isLoading ? <Cargando texto="Cargando la bitácora…" /> : null}

      {corridas ? (
        <Tarjeta
          titulo="Corridas"
          descripcion={
            <>
              <strong>Impuesto</strong> cuenta filas que van <em>dentro</em> de
              las aceptadas —se guardan marcadas— y que no suman en ningún
              total, porcentaje ni comparación contra presupuesto: no son venta,
              son recaudo a nombre de terceros. Se cuentan aparte para que
              conciliar la corrida contra el origen no dé una diferencia sin
              explicación.
            </>
          }
          sinRelleno
        >
          {corridas.length === 0 ? (
            <Vacio
              titulo="Todavía no se ha cargado nada"
              detalle="Ejecute la primera ingesta con el formulario de arriba."
            />
          ) : (
            <div className="tabla-envoltorio">
              <table className="tabla tabla--compacta">
                <thead>
                  <tr>
                    <th scope="col">Cuándo</th>
                    <th scope="col">Quién</th>
                    <th scope="col">Rango</th>
                    <th scope="col">Estado</th>
                    <th scope="col">Leídas</th>
                    <th scope="col">Aceptadas</th>
                    <th scope="col">Impuesto</th>
                    <th scope="col">Rechazadas</th>
                    <th scope="col">Duración</th>
                  </tr>
                </thead>
                <tbody>
                  {corridas.map((corrida) => (
                    <tr key={corrida.id}>
                      <td>{fechaHora(corrida.cuando)}</td>
                      <td>{corrida.quien ?? "automática"}</td>
                      <td className="mono">
                        {corrida.desde ?? "—"} → {corrida.hasta ?? "—"}
                      </td>
                      <td>
                        <Distintivo
                          tono={
                            corrida.estado === "COMPLETADA"
                              ? "exito"
                              : "peligro"
                          }
                        >
                          {humanizar(corrida.estado)}
                        </Distintivo>
                      </td>
                      <td className="numero">{numero(corrida.filas_leidas)}</td>
                      <td className="numero">{numero(corrida.aceptadas)}</td>
                      <td className="numero tenue">
                        {numero(corrida.impuesto)}
                      </td>
                      <td className="numero">
                        {corrida.rechazadas > 0 ? (
                          <button
                            type="button"
                            className="boton boton--sutil boton--pequeno"
                            onClick={() =>
                              setVerRechazos(
                                verRechazos === corrida.id ? null : corrida.id,
                              )
                            }
                          >
                            {numero(corrida.rechazadas)}
                          </button>
                        ) : (
                          "0"
                        )}
                      </td>
                      <td className="numero tenue">
                        {corrida.duracion_ms === null
                          ? "—"
                          : `${numero(corrida.duracion_ms)} ms`}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Tarjeta>
      ) : null}

      {verRechazos !== null ? <Rechazos id={verRechazos} /> : null}
    </div>
  );
}

/**
 * El detalle de por qué no se pudo aceptar una fila.
 *
 * Restringido a `GERENTE` y `ADMIN` en el contrato, y no por burocracia: los
 * rechazos llevan valores crudos de filas reales de facturación.
 */
function Rechazos({ id }: { id: number }) {
  const { data, isLoading, error } = useRechazosAgro(id);

  return (
    <Tarjeta titulo={`Filas rechazadas de la corrida ${id}`} sinRelleno>
      <AvisoError error={error} />
      {isLoading ? <Cargando texto="Cargando los rechazos…" /> : null}
      {data ? (
        <div className="tabla-envoltorio">
          <table className="tabla tabla--compacta">
            <thead>
              <tr>
                <th scope="col">Fila</th>
                <th scope="col">Campo</th>
                <th scope="col">Valor</th>
                <th scope="col">Motivo</th>
              </tr>
            </thead>
            <tbody>
              {data.map((rechazo, indice) => (
                <tr key={indice}>
                  <td className="numero">{rechazo.fila ?? "—"}</td>
                  <td className="mono">{rechazo.campo ?? "—"}</td>
                  <td className="mono">{rechazo.valor ?? "—"}</td>
                  <td>{rechazo.motivo}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </Tarjeta>
  );
}
