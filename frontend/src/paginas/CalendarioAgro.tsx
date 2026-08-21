/**
 * Días hábiles y trabajados de los dos centros de operación.
 *
 * La unidad de calendario de agropecuaria es el **centro** —301 Planta y 302
 * Montería— y no una zona: son dos, pueden abrir días distintos y son los únicos
 * contra los que se deriva el ideal.
 *
 * Dos particularidades que la pantalla tiene que respetar:
 *
 * - **Los días admiten media jornada**, así que son decimales. Un `27,5` no es
 *   un error de captura.
 * - **`dias_trabajados` vacío significa «derivado de la fecha de corte»**, y el
 *   backend lo marca con `derivado`. Escribir un número ahí es afirmar algo
 *   sobre la realidad —«ese sábado no abrimos»— y esa afirmación manda sobre lo
 *   que el sistema calcularía solo. Por eso el campo se puede vaciar: es la
 *   forma de retirar la afirmación y volver a la derivación.
 */

import { useState } from "react";
import { useSearchParams } from "react-router-dom";

import {
  useCalendarioAgro,
  useGuardarCalendarioAgro,
} from "@/api/consultasAgro";
import type { CalendarioAgro as Fila } from "@/api/tiposAgro";
import {
  AvisoError,
  Cargando,
  Distintivo,
  Tarjeta,
  Vacio,
} from "@/componentes/comunes";
import {
  dias,
  periodoActual,
  periodoLargo,
  porcentaje,
} from "@/utilidades/formato";

export function CalendarioAgro() {
  const [parametros, setParametros] = useSearchParams();
  const periodo = parametros.get("periodo") ?? periodoActual();

  const { data, isLoading, error } = useCalendarioAgro(periodo);
  const guardar = useGuardarCalendarioAgro(periodo);

  function fijarPeriodo(valor: string) {
    const siguientes = new URLSearchParams(parametros);
    siguientes.set("periodo", valor);
    setParametros(siguientes, { replace: true });
  }

  const filas = data ?? [];

  return (
    <div className="pila">
      <section className="filtros" aria-label="Período del calendario">
        <label className="filtros__campo">
          <span>Período</span>
          <input
            className="campo__control"
            type="month"
            value={periodo}
            onChange={(evento) => fijarPeriodo(evento.target.value)}
            required
          />
        </label>
      </section>

      <AvisoError error={error} />
      <AvisoError error={guardar.error} />

      {isLoading ? <Cargando texto="Cargando el calendario…" /> : null}

      {data ? (
        <Tarjeta
          titulo="Días hábiles por centro de operación"
          descripcion={
            <>
              {periodoLargo(periodo)}. Los días hábiles (<code>H</code>) son el
              denominador del ideal y de la proyección: cambiarlos mueve el
              semáforo de todas las pantallas de la unidad. Admiten media
              jornada.
            </>
          }
          sinRelleno
        >
          {filas.length === 0 ? (
            <Vacio
              titulo="Sin centros"
              detalle="No hay centros de operación registrados todavía. Aparecen con la primera ingesta."
            />
          ) : (
            <div className="tabla-envoltorio">
              <table className="tabla">
                <thead>
                  <tr>
                    <th scope="col">Centro</th>
                    <th
                      scope="col"
                      title="H — los días que el centro abre en el mes."
                    >
                      Días hábiles
                    </th>
                    <th
                      scope="col"
                      title="T — los días transcurridos hasta el corte."
                    >
                      Días trabajados
                    </th>
                    <th
                      scope="col"
                      title="T / H — la parte del mes que ya pasó."
                    >
                      Ideal
                    </th>
                    <th scope="col">
                      <span className="solo-lectores">Acciones</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {filas.map((fila) => (
                    <FilaCentro
                      key={fila.centro}
                      fila={fila}
                      guardar={guardar}
                    />
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

function FilaCentro({
  fila,
  guardar,
}: {
  fila: Fila;
  guardar: ReturnType<typeof useGuardarCalendarioAgro>;
}) {
  const [editando, setEditando] = useState(false);
  const [habiles, setHabiles] = useState(fila.dias_habiles);
  const [trabajados, setTrabajados] = useState(fila.dias_trabajados ?? "");

  function enviar(evento: React.FormEvent) {
    evento.preventDefault();
    guardar.mutate(
      {
        centro: fila.centro,
        datos: {
          dias_habiles: habiles,
          // Vacío es `null` y `null` significa **derivado**, no cero: retirar la
          // afirmación del usuario y dejar que el sistema lo calcule del corte.
          dias_trabajados: trabajados.trim() === "" ? null : trabajados,
        },
      },
      { onSuccess: () => setEditando(false) },
    );
  }

  if (editando) {
    return (
      <tr>
        <th scope="row">
          {fila.nombre}
          <span className="tenue mono"> · {fila.centro}</span>
        </th>
        <td colSpan={4}>
          <form className="formulario formulario--linea" onSubmit={enviar}>
            <label className="campo campo--estrecho">
              <span>Hábiles</span>
              <input
                className="campo__control"
                type="number"
                min="0.5"
                max="31"
                step="0.5"
                value={habiles}
                onChange={(evento) => setHabiles(evento.target.value)}
                required
              />
            </label>
            <label className="campo campo--estrecho">
              <span>Trabajados</span>
              <input
                className="campo__control"
                type="number"
                min="0"
                max="31"
                step="0.5"
                value={trabajados}
                onChange={(evento) => setTrabajados(evento.target.value)}
                placeholder="derivado"
                title="Vacío = lo deriva el sistema de la fecha de corte. Un número aquí manda sobre esa derivación."
              />
            </label>
            <button
              type="button"
              className="boton boton--sutil"
              onClick={() => setEditando(false)}
            >
              Cancelar
            </button>
            <button
              type="submit"
              className="boton boton--pequeno"
              disabled={guardar.isPending}
            >
              {guardar.isPending ? "Guardando…" : "Guardar"}
            </button>
          </form>
        </td>
      </tr>
    );
  }

  return (
    <tr>
      <th scope="row">
        {fila.nombre}
        <span className="tenue mono"> · {fila.centro}</span>
      </th>
      <td className="numero">{dias(fila.dias_habiles)}</td>
      <td className="numero">
        {dias(fila.dias_trabajados)}{" "}
        {fila.derivado ? (
          <Distintivo tono="neutro">derivado del corte</Distintivo>
        ) : (
          <Distintivo tono="info">fijado a mano</Distintivo>
        )}
      </td>
      <td className="numero">{porcentaje(fila.ideal)}</td>
      <td>
        <button
          type="button"
          className="boton boton--sutil boton--pequeno"
          onClick={() => setEditando(true)}
        >
          Cambiar
        </button>
      </td>
    </tr>
  );
}
