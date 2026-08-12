/**
 * Calendario de días hábiles por zona.
 *
 * Es el corazón de la parametrización: `ideal = días trabajados ÷ días hábiles`
 * es la vara contra la que se mide todo lo demás, así que un error de medio día
 * aquí mueve el semáforo de cuatro puntos de venta. Por eso la pantalla admite
 * medias jornadas (27,5) y muestra el ideal resultante en la misma fila, para
 * que el efecto del cambio se vea antes de guardarlo.
 */

import { useMemo, useState } from "react";
import type { FormEvent } from "react";

import { useCalendario, useGuardarCalendario, useZonas } from "@/api/consultas";
import type { FilaCalendario, ReferenciaSimple } from "@/api/tipos";
import { useAuth } from "@/auth/ContextoAuth";
import { AvisoError, Campo, Dialogo, Tarjeta, Vacio } from "@/componentes/comunes";
import { useFiltros } from "@/componentes/filtros";
import { FORMULAS, etiquetaDe } from "@/utilidades/dominio";
import { dias, fecha, periodoLargo, porcentaje } from "@/utilidades/formato";
import { normalizarDecimal } from "@/paginas/Presupuesto";

/** El identificador solo viaja cuando la referencia es un objeto. */
function idDe(referencia: ReferenciaSimple | null | undefined): number | null {
  if (referencia === null || referencia === undefined) return null;
  if (typeof referencia === "string") return null;
  return referencia.id ?? null;
}

interface EdicionZona {
  zonaId: number;
  nombre: string;
  dias_habiles: string;
  dias_trabajados: string;
  derivar: boolean;
}

export function Calendario() {
  const { filtros, fijar } = useFiltros();
  const { puedeParametrizar } = useAuth();

  const { data: calendario, isLoading, error } = useCalendario(filtros.periodo);
  const { data: zonas } = useZonas();
  const guardar = useGuardarCalendario(filtros.periodo);

  const [edicion, setEdicion] = useState<EdicionZona | null>(null);
  const [errorFormulario, setErrorFormulario] = useState<string | null>(null);

  /**
   * El contrato devuelve el calendario con el nombre de la zona pero la
   * escritura necesita `zona_id`. Cuando la respuesta no trae el identificador,
   * se resuelve contra el catálogo de zonas por nombre.
   */
  const idPorNombre = useMemo(() => {
    const mapa = new Map<string, number>();
    for (const zona of zonas ?? []) mapa.set(zona.nombre.toUpperCase(), zona.id);
    return mapa;
  }, [zonas]);

  function resolverId(fila: FilaCalendario): number | null {
    return idDe(fila.zona) ?? idPorNombre.get(etiquetaDe(fila.zona).toUpperCase()) ?? null;
  }

  function abrir(fila: FilaCalendario) {
    const zonaId = resolverId(fila);
    if (zonaId === null) return;
    setErrorFormulario(null);
    setEdicion({
      zonaId,
      nombre: etiquetaDe(fila.zona),
      dias_habiles: fila.dias_habiles ?? "",
      dias_trabajados: fila.dias_trabajados ?? "",
      derivar: false,
    });
  }

  function alGuardar(evento: FormEvent) {
    evento.preventDefault();
    if (!edicion) return;

    const habiles = normalizarDecimal(edicion.dias_habiles);
    if (habiles === null) {
      setErrorFormulario("Los días hábiles deben ser un número; admiten media jornada (27,5).");
      return;
    }

    let trabajados: string | null = null;
    if (!edicion.derivar) {
      trabajados = normalizarDecimal(edicion.dias_trabajados);
      if (trabajados === null) {
        setErrorFormulario(
          "Los días trabajados deben ser un número, o marque «derivar del calendario».",
        );
        return;
      }
    }

    setErrorFormulario(null);
    guardar.mutate(
      { zonaId: edicion.zonaId, datos: { dias_habiles: habiles, dias_trabajados: trabajados } },
      { onSuccess: () => setEdicion(null) },
    );
  }

  return (
    <div className="pila">
      <section className="filtros" aria-label="Período del calendario">
        <label className="filtros__campo">
          <span>Período</span>
          <input
            className="campo__control"
            type="month"
            value={filtros.periodo}
            onChange={(evento) => fijar("periodo", evento.target.value)}
          />
        </label>
      </section>

      <AvisoError error={error} />

      <div className="aviso aviso--info" role="note">
        <div>
          <strong>Pendiente de confirmar con el usuario.</strong>
          <p>
            Los días hábiles de las zonas de MALAMBO, CONCORDE, SANFELIPE, OLAYA, LA93, ALAMEDA y
            ALAMEDA2 aún no están definidos (§8.1 de la especificación). Se parametrizan en esta
            pantalla; hasta entonces el valor sembrado es un supuesto, no un dato del negocio.
          </p>
        </div>
      </div>

      <Tarjeta
        titulo={`Días hábiles · ${periodoLargo(filtros.periodo)}`}
        descripcion="Un domingo o festivo que abre medio día cuenta 0,5. El ideal se recalcula solo."
        sinRelleno
        pie={
          <p className="pie-calculo__formulas">
            {FORMULAS.ideal} · {FORMULAS.presupuesto_diario}
          </p>
        }
      >
        {isLoading ? (
          <p className="cargando">Cargando el calendario…</p>
        ) : (calendario ?? []).length === 0 ? (
          <Vacio
            titulo="Sin zonas parametrizadas"
            detalle="El período no tiene calendario cargado."
          />
        ) : (
          <div className="tabla-envoltorio">
            <table className="tabla">
              <thead>
                <tr>
                  <th scope="col">Zona</th>
                  <th scope="col" className="numero">
                    Días hábiles (H)
                  </th>
                  <th scope="col" className="numero">
                    Días trabajados (T)
                  </th>
                  <th scope="col" className="numero">
                    Ideal
                  </th>
                  <th scope="col">Fecha de corte</th>
                  {puedeParametrizar ? (
                    <th scope="col">
                      <span className="solo-lectores">Acciones</span>
                    </th>
                  ) : null}
                </tr>
              </thead>
              <tbody>
                {(calendario ?? []).map((fila, indice) => (
                  <tr key={`${etiquetaDe(fila.zona)}-${indice}`}>
                    <th scope="row">{etiquetaDe(fila.zona)}</th>
                    <td className="numero">{dias(fila.dias_habiles)}</td>
                    <td className="numero">{dias(fila.dias_trabajados)}</td>
                    <td className="numero numero--destacado">{porcentaje(fila.ideal)}</td>
                    <td>{fecha(fila.fecha_corte)}</td>
                    {puedeParametrizar ? (
                      <td>
                        <button
                          type="button"
                          className="boton boton--pequeno"
                          onClick={() => abrir(fila)}
                          disabled={resolverId(fila) === null}
                          title={
                            resolverId(fila) === null
                              ? "No se pudo resolver el identificador de la zona."
                              : undefined
                          }
                        >
                          Editar
                        </button>
                      </td>
                    ) : null}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Tarjeta>

      <Dialogo
        abierto={edicion !== null}
        titulo={edicion ? `Días hábiles · ${edicion.nombre}` : ""}
        onCerrar={() => setEdicion(null)}
      >
        {edicion ? (
          <form className="pila" onSubmit={alGuardar}>
            {errorFormulario ? (
              <div className="aviso aviso--error" role="alert">
                {errorFormulario}
              </div>
            ) : null}
            <AvisoError error={guardar.error} />

            <Campo
              etiqueta="Días hábiles del mes"
              ayuda="Total de la zona. Admite media jornada: 27,5."
            >
              <input
                className="campo__control"
                inputMode="decimal"
                value={edicion.dias_habiles}
                onChange={(evento) =>
                  setEdicion({ ...edicion, dias_habiles: evento.target.value })
                }
                required
              />
            </Campo>

            <label className="fila">
              <input
                type="checkbox"
                checked={edicion.derivar}
                onChange={(evento) => setEdicion({ ...edicion, derivar: evento.target.checked })}
              />
              <span>Derivar los días trabajados del calendario y la fecha de corte</span>
            </label>

            <Campo
              etiqueta="Días trabajados al corte"
              ayuda={
                edicion.derivar
                  ? "Lo calculará el backend a partir del calendario."
                  : "Sobrescribe el valor derivado."
              }
            >
              <input
                className="campo__control"
                inputMode="decimal"
                value={edicion.derivar ? "" : edicion.dias_trabajados}
                onChange={(evento) =>
                  setEdicion({ ...edicion, dias_trabajados: evento.target.value })
                }
                disabled={edicion.derivar}
              />
            </Campo>

            <p className="tenue">
              Cambiar estos valores mueve el ideal, el semáforo y la proyección de todos los puntos
              de venta de la zona.
            </p>

            <div className="grupo-botones">
              <button type="submit" className="boton boton--principal" disabled={guardar.isPending}>
                {guardar.isPending ? "Guardando…" : "Guardar"}
              </button>
              <button type="button" className="boton" onClick={() => setEdicion(null)}>
                Cancelar
              </button>
            </div>
          </form>
        ) : null}
      </Dialogo>
    </div>
  );
}
