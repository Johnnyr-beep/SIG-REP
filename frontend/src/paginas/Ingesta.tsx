/**
 * Ingesta desde SIESA.
 *
 * Dos preguntas, en este orden: ¿la última carga entró bien? y ¿qué se quedó
 * fuera y por qué? La segunda es la que evita que el reporte mienta: si 28 filas
 * se rechazaron por tener el campo `Domicilio` en blanco, el gerente tiene
 * derecho a saber que su venta del día está incompleta en esa medida.
 */

import { useState } from "react";
import type { FormEvent } from "react";

import {
  useCorridasIngesta,
  useEjecutarIngesta,
  useIngestaArchivo,
  useRechazosIngesta,
  useSalud,
} from "@/api/consultas";
import type { FuenteIngesta } from "@/api/tipos";
import { useAuth } from "@/auth/ContextoAuth";
import {
  AvisoError,
  Campo,
  Distintivo,
  Tarjeta,
  Vacio,
} from "@/componentes/comunes";
import { tonoEstadoIngesta } from "@/utilidades/dominio";
import { fechaHora, humanizar, numero } from "@/utilidades/formato";

export function Ingesta() {
  const { puedeParametrizar } = useAuth();
  const { data: salud } = useSalud();
  const { data: corridas, isLoading, error } = useCorridasIngesta();

  const [corridaAbierta, setCorridaAbierta] = useState<number | null>(null);
  const { data: rechazos, isLoading: cargandoRechazos } =
    useRechazosIngesta(corridaAbierta);

  const ejecutar = useEjecutarIngesta();
  const subir = useIngestaArchivo();

  const [desde, setDesde] = useState("");
  const [hasta, setHasta] = useState("");
  const [fuente, setFuente] = useState<FuenteIngesta>("excel");
  const [archivo, setArchivo] = useState<File | null>(null);

  const ultima = corridas?.[0] ?? null;

  function alEjecutar(evento: FormEvent) {
    evento.preventDefault();
    if (!desde || !hasta) return;
    ejecutar.mutate({ desde, hasta, fuente });
  }

  return (
    <div className="pila">
      <Tarjeta titulo="Estado de la última carga">
        <div className="rejilla rejilla--indicadores">
          <div className="indicador">
            <span className="indicador__etiqueta">Última ingesta</span>
            <span className="indicador__valor indicador__valor--mediano">
              {fechaHora(salud?.ultima_ingesta ?? ultima?.cuando ?? null)}
            </span>
            <span className="indicador__nota">
              {ultima
                ? `Corrida #${ultima.id} · ${ultima.fuente}`
                : "Sin corridas registradas"}
            </span>
          </div>

          <div className="indicador">
            <span className="indicador__etiqueta">Filas aceptadas</span>
            <span className="indicador__valor indicador__valor--mediano">
              {numero(ultima?.aceptadas ?? null)}
            </span>
            <span className="indicador__nota">
              de {numero(ultima?.filas_leidas ?? null)} leídas
            </span>
          </div>

          <div
            className={`indicador${(ultima?.rechazadas ?? 0) > 0 ? " indicador--aviso" : ""}`}
          >
            <span className="indicador__etiqueta">Filas rechazadas</span>
            <span className="indicador__valor indicador__valor--mediano">
              {numero(ultima?.rechazadas ?? null)}
            </span>
            <span className="indicador__nota">
              {(ultima?.rechazadas ?? 0) > 0
                ? "Revise el detalle: la venta del período está incompleta en esa medida."
                : "Sin rechazos."}
            </span>
          </div>

          <div className="indicador">
            <span className="indicador__etiqueta">Servicio</span>
            <span className="indicador__valor indicador__valor--mediano">
              {salud ? humanizar(salud.estado) : "—"}
            </span>
            <span className="indicador__nota">
              {salud
                ? `${salud.base_datos} · versión ${salud.version}`
                : "Sin respuesta de /salud"}
            </span>
          </div>
        </div>
      </Tarjeta>

      {puedeParametrizar ? (
        <Tarjeta
          titulo="Ejecutar una carga"
          descripcion="Reprocesar una fecha reemplaza el día completo; no duplica."
        >
          <form className="fila fila--envolvente" onSubmit={alEjecutar}>
            <Campo etiqueta="Desde">
              <input
                className="campo__control"
                type="date"
                value={desde}
                onChange={(evento) => setDesde(evento.target.value)}
                required
              />
            </Campo>
            <Campo etiqueta="Hasta">
              <input
                className="campo__control"
                type="date"
                value={hasta}
                onChange={(evento) => setHasta(evento.target.value)}
                required
              />
            </Campo>
            <Campo etiqueta="Fuente">
              <select
                className="campo__control"
                value={fuente}
                onChange={(evento) =>
                  setFuente(evento.target.value === "siesa" ? "siesa" : "excel")
                }
              >
                <option value="excel">Excel (libro actual)</option>
                <option value="siesa">API de SIESA</option>
              </select>
            </Campo>
            <button
              type="submit"
              className="boton boton--principal boton--pequeno"
              disabled={ejecutar.isPending || !desde || !hasta}
            >
              {ejecutar.isPending ? "Ejecutando…" : "Ejecutar"}
            </button>
          </form>

          <AvisoError error={ejecutar.error} />

          <hr className="separador" />

          <form
            className="fila fila--envolvente"
            onSubmit={(evento) => {
              evento.preventDefault();
              if (archivo) subir.mutate(archivo);
            }}
          >
            <Campo
              etiqueta="O cargue el archivo de SIESA"
              ayuda="Formato .xlsx"
            >
              <input
                className="campo__control"
                type="file"
                accept=".xlsx"
                onChange={(evento) =>
                  setArchivo(evento.target.files?.[0] ?? null)
                }
              />
            </Campo>
            <button
              type="submit"
              className="boton boton--pequeno"
              disabled={!archivo || subir.isPending}
            >
              {subir.isPending ? "Subiendo…" : "Cargar archivo"}
            </button>
          </form>

          <AvisoError error={subir.error} />
        </Tarjeta>
      ) : null}

      <AvisoError error={error} />

      <Tarjeta
        titulo="Corridas"
        descripcion="Historial de cargas y su resultado."
        sinRelleno
      >
        {isLoading ? (
          <p className="cargando">Cargando el historial…</p>
        ) : (corridas ?? []).length === 0 ? (
          <Vacio
            titulo="Sin corridas"
            detalle="Todavía no se ha ejecutado ninguna ingesta."
          />
        ) : (
          <div className="tabla-envoltorio">
            <table className="tabla">
              <thead>
                <tr>
                  <th scope="col" className="numero">
                    #
                  </th>
                  <th scope="col">Cuándo</th>
                  <th scope="col">Quién</th>
                  <th scope="col">Fuente</th>
                  <th scope="col">Rango</th>
                  <th scope="col">Estado</th>
                  <th scope="col" className="numero">
                    Leídas
                  </th>
                  <th scope="col" className="numero">
                    Aceptadas
                  </th>
                  <th scope="col" className="numero">
                    Rechazadas
                  </th>
                  <th scope="col" className="numero">
                    Duración
                  </th>
                  <th scope="col">
                    <span className="solo-lectores">Acciones</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {(corridas ?? []).map((corrida) => (
                  <tr key={corrida.id}>
                    <td className="numero mono">{corrida.id}</td>
                    <td>{fechaHora(corrida.cuando)}</td>
                    <td>{corrida.quien}</td>
                    <td>{corrida.fuente}</td>
                    <td className="tenue">
                      {corrida.desde} → {corrida.hasta}
                    </td>
                    <td>
                      <Distintivo tono={tonoEstadoIngesta(corrida.estado)}>
                        {humanizar(corrida.estado)}
                      </Distintivo>
                    </td>
                    <td className="numero">{numero(corrida.filas_leidas)}</td>
                    <td className="numero">{numero(corrida.aceptadas)}</td>
                    <td
                      className={`numero${corrida.rechazadas > 0 ? " texto-peligro" : ""}`}
                    >
                      {numero(corrida.rechazadas)}
                    </td>
                    <td className="numero tenue">
                      {numero(corrida.duracion_ms)} ms
                    </td>
                    <td>
                      <button
                        type="button"
                        className="boton boton--pequeno"
                        onClick={() =>
                          setCorridaAbierta(
                            corridaAbierta === corrida.id ? null : corrida.id,
                          )
                        }
                        aria-expanded={corridaAbierta === corrida.id}
                        disabled={corrida.rechazadas === 0}
                      >
                        {corridaAbierta === corrida.id
                          ? "Ocultar"
                          : "Ver rechazos"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Tarjeta>

      {corridaAbierta !== null ? (
        <Tarjeta
          titulo={`Filas rechazadas · corrida #${corridaAbierta}`}
          descripcion="Cada rechazo con su campo, el valor recibido y el motivo."
          sinRelleno
        >
          {cargandoRechazos ? (
            <p className="cargando">Cargando los rechazos…</p>
          ) : (rechazos ?? []).length === 0 ? (
            <Vacio
              titulo="Sin rechazos"
              detalle="Esta corrida aceptó todas las filas."
            />
          ) : (
            <div className="tabla-envoltorio">
              <table className="tabla">
                <thead>
                  <tr>
                    <th scope="col" className="numero">
                      Fila
                    </th>
                    <th scope="col">Campo</th>
                    <th scope="col">Valor recibido</th>
                    <th scope="col">Motivo</th>
                  </tr>
                </thead>
                <tbody>
                  {(rechazos ?? []).map((rechazo, indice) => (
                    <tr key={`${rechazo.fila}-${rechazo.campo}-${indice}`}>
                      <td className="numero mono">{numero(rechazo.fila)}</td>
                      <td>{rechazo.campo}</td>
                      <td className="mono">
                        {rechazo.valor === "" ? "(vacío)" : rechazo.valor}
                      </td>
                      <td>{rechazo.motivo}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Tarjeta>
      ) : null}
    </div>
  );
}
