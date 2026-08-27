/** Captura del total histórico mensual por punto de venta. */

import { Fragment, useMemo, useState } from "react";
import type { FormEvent } from "react";

import {
  useGuardarHistoriaVenta,
  useHistoriaVenta,
  usePuntosVenta,
} from "@/api/consultas";
import type { HistoriaVenta as HistoriaVentaTipo } from "@/api/tipos";
import { AvisoError, Tarjeta, Vacio } from "@/componentes/comunes";
import { useFiltros } from "@/componentes/filtros";
import { dinero, fechaHora, kilos, periodoLargo } from "@/utilidades/formato";

import { normalizarDecimal } from "./Presupuesto";

interface Edicion {
  puntoVentaId: number;
  monto: string;
  kilos: string;
  motivo: string;
}

function periodoAnterior(periodo: string): string {
  const [anio, mes] = periodo.split("-");
  return `${Number(anio) - 1}-${mes}`;
}

export function HistoriaVenta() {
  const { filtros } = useFiltros();
  const [periodo, setPeriodo] = useState(() => periodoAnterior(filtros.periodo));
  const [edicion, setEdicion] = useState<Edicion | null>(null);
  const [errorFormulario, setErrorFormulario] = useState<string | null>(null);
  const { data: puntos } = usePuntosVenta();
  const { data: historia, isLoading, error } = useHistoriaVenta(periodo);
  const guardar = useGuardarHistoriaVenta(periodo);

  const historiaPorPunto = useMemo(
    () =>
      new Map(
        (historia ?? []).map((fila) => [fila.punto_venta_id, fila] as const),
      ),
    [historia],
  );

  function editar(
    puntoVentaId: number,
    fila: HistoriaVentaTipo | undefined,
  ) {
    setErrorFormulario(null);
    setEdicion({
      puntoVentaId,
      monto: fila?.monto ?? "",
      kilos: fila?.kilos ?? "",
      motivo: "",
    });
  }

  function alGuardar(evento: FormEvent) {
    evento.preventDefault();
    if (!edicion) return;
    const monto = normalizarDecimal(edicion.monto);
    const kilosNormalizados = normalizarDecimal(edicion.kilos);
    if (monto === null || kilosNormalizados === null) {
      setErrorFormulario("Escriba valores numéricos válidos en pesos y kilos.");
      return;
    }
    if (edicion.motivo.trim().length < 5) {
      setErrorFormulario("Explique el origen o motivo del dato en al menos 5 caracteres.");
      return;
    }
    guardar.mutate(
      {
        periodo,
        punto_venta_id: edicion.puntoVentaId,
        monto,
        kilos: kilosNormalizados,
        motivo: edicion.motivo.trim(),
      },
      {
        onSuccess: () => {
          setEdicion(null);
          setErrorFormulario(null);
        },
      },
    );
  }

  return (
    <div className="pila">
      <section className="filtros" aria-label="Período histórico">
        <label className="filtros__campo">
          <span>Período que va a comparar</span>
          <input
            className="campo__control"
            type="month"
            value={periodo}
            onChange={(evento) => {
              setPeriodo(evento.target.value);
              setEdicion(null);
            }}
          />
        </label>
        {periodo.length === 7 ? (
          <p className="tenue">
            Se usará al consultar{" "}
            {periodoLargo(
              `${Number(periodo.slice(0, 4)) + 1}${periodo.slice(4)}`,
            )}
            .
          </p>
        ) : null}
      </section>

      <div className="aviso aviso--info" role="status">
        <div>
          <strong>Respaldo para períodos sin detalle en SIESA.</strong>
          <p>
            Si un PDV ya tiene transacciones del período, esas transacciones
            prevalecen. SIGREP nunca suma las dos fuentes ni duplica la venta.
          </p>
        </div>
      </div>

      <AvisoError error={error} />
      <AvisoError error={guardar.error} />

      <Tarjeta
        titulo={`Venta histórica de ${periodoLargo(periodo)}`}
        descripcion="Totales mensuales por punto de venta, en pesos y kilogramos"
        sinRelleno
      >
        {isLoading ? (
          <p className="cargando">Cargando la historia…</p>
        ) : (puntos ?? []).length === 0 ? (
          <Vacio
            titulo="No hay puntos de venta"
            detalle="Configure el catálogo antes de cargar historia."
          />
        ) : (
          <div className="tabla-envoltorio">
            <table className="tabla">
              <thead>
                <tr>
                  <th scope="col">Punto de venta</th>
                  <th scope="col" className="numero">Venta ($)</th>
                  <th scope="col" className="numero">Venta (kg)</th>
                  <th scope="col">Última actualización</th>
                  <th scope="col"><span className="solo-lectores">Acciones</span></th>
                </tr>
              </thead>
              <tbody>
                {(puntos ?? []).filter((punto) => punto.presupuestado).map((punto) => {
                  const fila = historiaPorPunto.get(punto.id);
                  const abierta = edicion?.puntoVentaId === punto.id;
                  return (
                    <Fragment key={punto.id}>
                      <tr>
                        <th scope="row">
                          {punto.codigo_co} · {punto.nombre}
                        </th>
                        <td className="numero">{dinero(fila?.monto ?? null)}</td>
                        <td className="numero">{kilos(fila?.kilos ?? null)}</td>
                        <td className="tenue">
                          {fila
                            ? `${fechaHora(fila.actualizado_en)} · ${fila.actualizado_por ?? "—"}`
                            : "Sin cargar"}
                        </td>
                        <td>
                          <button
                            type="button"
                            className="boton boton--pequeno"
                            onClick={() => editar(punto.id, fila)}
                          >
                            {fila ? "Corregir" : "Cargar"}
                          </button>
                        </td>
                      </tr>
                      {abierta ? (
                        <tr>
                          <td colSpan={5}>
                            <form className="formulario-en-linea" onSubmit={alGuardar}>
                              <label className="campo">
                                <span>Venta ($)</span>
                                <input
                                  className="campo__control"
                                  inputMode="decimal"
                                  value={edicion.monto}
                                  onChange={(evento) =>
                                    setEdicion({ ...edicion, monto: evento.target.value })
                                  }
                                  autoFocus
                                />
                              </label>
                              <label className="campo">
                                <span>Venta (kg)</span>
                                <input
                                  className="campo__control"
                                  inputMode="decimal"
                                  value={edicion.kilos}
                                  onChange={(evento) =>
                                    setEdicion({ ...edicion, kilos: evento.target.value })
                                  }
                                />
                              </label>
                              <label className="campo">
                                <span>Origen o motivo</span>
                                <input
                                  className="campo__control"
                                  value={edicion.motivo}
                                  maxLength={400}
                                  onChange={(evento) =>
                                    setEdicion({ ...edicion, motivo: evento.target.value })
                                  }
                                  placeholder="Ej. cierre validado por contabilidad"
                                />
                              </label>
                              {errorFormulario ? (
                                <p className="campo__error">{errorFormulario}</p>
                              ) : null}
                              <div className="acciones">
                                <button
                                  type="submit"
                                  className="boton boton--principal"
                                  disabled={guardar.isPending}
                                >
                                  {guardar.isPending ? "Guardando…" : "Guardar"}
                                </button>
                                <button
                                  type="button"
                                  className="boton boton--sutil"
                                  onClick={() => setEdicion(null)}
                                >
                                  Cancelar
                                </button>
                              </div>
                            </form>
                          </td>
                        </tr>
                      ) : null}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Tarjeta>
    </div>
  );
}
