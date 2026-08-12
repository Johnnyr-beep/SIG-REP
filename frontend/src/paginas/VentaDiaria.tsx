/**
 * Venta diaria — la matriz de puntos de venta por días del mes.
 *
 * Equivale a la `Hoja1` del libro actual, con una diferencia que el Excel no
 * tiene: cada celda se compara contra el presupuesto diario derivado
 * (`presupuesto mensual ÷ días hábiles de la zona`), así que la tabla no dice
 * solo cuánto se vendió sino si ese día alcanzó. La marca ▲▼ acompaña siempre al
 * color, para que la lectura no dependa de distinguir tonos.
 */

import { useState } from "react";

import { useExportar, useVentaDiaria } from "@/api/consultas";
import type { FilaVentaDiaria } from "@/api/tipos";
import { AvisoError, Cargando, Tarjeta, Vacio } from "@/componentes/comunes";
import { BarraFiltros, useFiltros } from "@/componentes/filtros";
import { ColumnasDiarias } from "@/componentes/graficos";
import { PieCalculo } from "@/componentes/indicadores";
import { FORMULAS } from "@/utilidades/dominio";
import {
  SIN_DATO,
  comparaParaGrafico,
  diaDelMes,
  esDomingo,
  porMedida,
} from "@/utilidades/formato";

export function VentaDiaria() {
  const control = useFiltros();
  const { filtros } = control;
  const { data, isLoading, error } = useVentaDiaria(filtros);
  const exportar = useExportar();

  const [seleccionado, setSeleccionado] = useState<string | null>(null);

  const medida = data?.medida ?? filtros.medida;
  const formatear = (valor: string | null) => porMedida(valor, medida);

  /**
   * `presupuesto_diario_por_pdv` viene indexado por código de C.O., que es
   * exactamente lo que trae `fila.punto_venta`. No hace falta puente por nombre.
   */
  function presupuestoDiario(fila: FilaVentaDiaria): string | null {
    if (!data) return null;
    return data.presupuesto_diario_por_pdv[fila.punto_venta] ?? null;
  }

  const filaSeleccionada =
    data?.filas.find((fila) => fila.punto_venta === seleccionado) ?? null;

  return (
    <div className="pila">
      <BarraFiltros
        control={control}
        acciones={
          <button
            type="button"
            className="boton boton--pequeno"
            onClick={() => exportar.mutate({ reporte: "venta-diaria", filtros })}
            disabled={exportar.isPending}
          >
            {exportar.isPending ? "Generando…" : "Exportar a Excel"}
          </button>
        }
      />

      <AvisoError error={error} />
      <AvisoError error={exportar.error} />

      {isLoading ? <Cargando texto="Armando la matriz del mes…" /> : null}

      {data ? (
        <>
          {filaSeleccionada ? (
            <Tarjeta
              titulo={`Detalle diario · ${filaSeleccionada.nombre}`}
              descripcion="La línea horizontal es el presupuesto diario derivado."
              acciones={
                <button
                  type="button"
                  className="boton boton--pequeno"
                  onClick={() => setSeleccionado(null)}
                >
                  Cerrar detalle
                </button>
              }
            >
              <ColumnasDiarias
                titulo={`Venta diaria de ${filaSeleccionada.nombre}`}
                referencia={presupuestoDiario(filaSeleccionada)}
                formatear={formatear}
                columnas={data.fechas.map((fecha, indice) => ({
                  fecha,
                  etiqueta: String(Number(fecha.slice(8, 10))),
                  valor: filaSeleccionada.valores[indice] ?? null,
                  esDomingo: esDomingo(fecha),
                }))}
              />
            </Tarjeta>
          ) : null}

          <Tarjeta
            titulo="Venta día por día"
            descripcion="Pulse un punto de venta para ver su serie del mes. ▲ el día superó el presupuesto diario; ▼ quedó por debajo."
            sinRelleno
            pie={
              <PieCalculo
                parametros={data.parametros_calculo}
                medida={medida}
                extra={<p className="pie-calculo__formulas">{FORMULAS.presupuesto_diario}</p>}
              />
            }
          >
            {data.filas.length === 0 ? (
              <Vacio
                titulo="Sin venta registrada"
                detalle="El período no tiene días con venta ingerida."
              />
            ) : (
              <div className="tabla-envoltorio tabla-envoltorio--alta">
                <table className="tabla tabla--anclada tabla--matriz">
                  <caption className="solo-lectores">
                    Venta por punto de venta y día del período {data.fecha_corte ?? ""}.
                  </caption>
                  <thead>
                    <tr>
                      <th scope="col" className="columna-ancla">
                        Punto de venta
                      </th>
                      {data.fechas.map((fecha) => (
                        <th
                          key={fecha}
                          scope="col"
                          className={`numero${esDomingo(fecha) ? " columna-domingo" : ""}`}
                        >
                          {diaDelMes(fecha)}
                        </th>
                      ))}
                      <th scope="col" className="numero columna-total">
                        Total
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.filas.map((fila, indice) => {
                      const referencia = presupuestoDiario(fila);
                      const codigo = fila.punto_venta;
                      const activa = codigo !== null && codigo === seleccionado;

                      return (
                        <tr key={codigo ?? String(indice)} className={activa ? "fila-activa" : ""}>
                          <th scope="row" className="columna-ancla">
                            <button
                              type="button"
                              className="enlace-fila"
                              onClick={() => setSeleccionado(activa ? null : codigo)}
                              disabled={codigo === null}
                            >
                              {fila.nombre}
                            </button>
                            <span className="columna-ancla__nota">
                              Ppto/día: {referencia === null ? SIN_DATO : formatear(referencia)}
                            </span>
                          </th>

                          {data.fechas.map((fecha, columna) => {
                            const valor = fila.valores[columna] ?? null;
                            const comparacion = comparaParaGrafico(valor, referencia);
                            const clase =
                              comparacion === null
                                ? ""
                                : comparacion >= 0
                                  ? " celda--sobre"
                                  : " celda--bajo";

                            return (
                              <td
                                key={fecha}
                                className={`numero${clase}${esDomingo(fecha) ? " columna-domingo" : ""}`}
                              >
                                {formatear(valor)}
                                {comparacion === null ? null : (
                                  <span className="celda__marca" aria-hidden="true">
                                    {comparacion >= 0 ? "▲" : "▼"}
                                  </span>
                                )}
                                {comparacion === null ? null : (
                                  <span className="solo-lectores">
                                    {comparacion >= 0
                                      ? " por encima del presupuesto diario"
                                      : " por debajo del presupuesto diario"}
                                  </span>
                                )}
                              </td>
                            );
                          })}

                          <td className="numero columna-total">{formatear(fila.total)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </Tarjeta>
        </>
      ) : null}
    </div>
  );
}
