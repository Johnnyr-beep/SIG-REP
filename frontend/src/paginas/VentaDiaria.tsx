/**
 * Venta diaria — la matriz de puntos de venta por días.
 *
 * Equivale a la `Hoja1` del libro actual, con dos diferencias que el Excel no
 * tiene. La primera: cada celda se compara contra el presupuesto diario derivado
 * (`presupuesto mensual ÷ días hábiles de la zona`), así que la tabla no dice
 * solo cuánto se vendió sino si ese día alcanzó. La marca ▲▼ acompaña siempre al
 * color, para que la lectura no dependa de distinguir tonos. La segunda: la fila
 * de totales viene calculada, fijada al pie y con su propia línea de referencia,
 * en lugar de obligar a sumar columnas a mano.
 *
 * ── El presupuesto es mensual y el rango puede no serlo ─────────────────────
 *
 * Con `desde` y `hasta` el rango cruza de mes, y entonces **hay dos líneas de
 * referencia distintas y las dos son correctas**: un día de julio no se mide
 * contra el presupuesto de agosto. Toda celda de esta pantalla resuelve su
 * referencia por el período de **su propia fecha** —el prefijo `YYYY-MM`, que es
 * la regla que fija el contrato— contra `presupuesto_diario_por_periodo`.
 * `presupuesto_diario_por_pdv` queda solo como respaldo, porque es la referencia
 * del período de la petición y en un rango a caballo daría el número equivocado
 * justo en los días del otro mes.
 *
 * ── Número de documentos (§4.4) ─────────────────────────────────────────────
 *
 * Va como nota pequeña bajo la cifra de cada día, no en su propia columna: es
 * un dato de apoyo, no la medida contra la que se compara el presupuesto, y
 * una columna propia por día duplicaría el ancho de una tabla que ya se
 * desplaza en horizontal. `null` es «sin conteo sincronizado ese día», no
 * «cero documentos», y se pinta «—» exactamente por la misma razón que el
 * resto de indefinidos de esta pantalla.
 */

import { useState } from "react";

import {
  useExportar,
  useExportarVentaDiariaAsadero,
  useVentaDiaria,
  useVentaDiariaAsadero,
} from "@/api/consultas";
import type { RespuestaVentaDiaria } from "@/api/tipos";
import { MAXIMO_DIAS_VENTA_DIARIA } from "@/api/tipos";
import { useAuth } from "@/auth/ContextoAuth";
import { AvisoError, Cargando, Tarjeta, Vacio } from "@/componentes/comunes";
import {
  BarraFiltros,
  diasDelRangoPedido,
  useFiltros,
} from "@/componentes/filtros";
import { ColumnasDiarias } from "@/componentes/graficos";
import { PieCalculo } from "@/componentes/indicadores";
import { FORMULAS } from "@/utilidades/dominio";
import {
  SIN_DATO,
  esDomingo,
  fecha as formatearFecha,
  periodoDeFecha,
  porMedida,
  porcentaje,
} from "@/utilidades/formato";

/** Una fila del resumen del corte: PDV, presupuesto del día, venta del día,
 * cumplimiento (fracción, para poder ordenar) y documentos. `cumplimiento`
 * es `null` sin presupuesto —432 EVENTOS BUCARAMANGA, por ejemplo— y esas
 * filas se quedan al final, nunca se ordenan como si fueran un 0%. */
interface FilaResumenCorte {
  codigo: string | null;
  nombre: string;
  pptoDia: string | null;
  venta: string | null;
  documentos: number | null;
  cumplimiento: number | null;
  ticketPromedio: number | null;
}

/** Venta entre número de documentos; `null` sin documentos (evita dividir por 0). */
function ticketPromedioDe(
  venta: string | null,
  documentos: number | null,
): number | null {
  return venta !== null && documentos
    ? Number(venta) / documentos
    : null;
}

function filaResumenDe(
  codigo: string | null,
  nombre: string,
  pptoDia: string | null,
  venta: string | null,
): Omit<FilaResumenCorte, "documentos" | "ticketPromedio"> {
  const cumplimiento =
    pptoDia && venta !== null && Number(pptoDia) !== 0
      ? Number(venta) / Number(pptoDia)
      : null;
  return { codigo, nombre, pptoDia, venta, cumplimiento };
}

export function VentaDiaria({ asadero = false }: { asadero?: boolean }) {
  const control = useFiltros();
  const { filtros } = control;

  /**
   * El rango se valida **antes** de pedir nada.
   *
   * El selector ya impide construir un rango invertido o de más de 92 días, pero
   * un enlace pegado a mano sí puede traerlo. Aquí se detiene: un 422 que el
   * usuario no puede provocar es mejor que uno bien explicado, y si aun así el
   * backend lo rechaza, `AvisoError` muestra su mensaje y su código tal cual.
   */
  const dias = diasDelRangoPedido(filtros.desde, filtros.hasta);
  const rangoInvertido = dias !== null && dias <= 0;
  const rangoExcesivo = dias !== null && dias > MAXIMO_DIAS_VENTA_DIARIA;
  const rangoValido = !rangoInvertido && !rangoExcesivo;

  const { data, isLoading, error } = asadero
    ? useVentaDiariaAsadero(filtros, rangoValido)
    : useVentaDiaria(filtros, rangoValido);
  const exportar = useExportar();
  const exportarAsadero = useExportarVentaDiariaAsadero();
  const { tienePermiso } = useAuth();

  const [seleccionado, setSeleccionado] = useState<string | null>(null);

  const medida = data?.medida ?? filtros.medida;
  const formatear = (valor: string | null) => porMedida(valor, medida);

  /**
   * La referencia de un punto de venta en un período concreto.
   *
   * `presupuesto_diario_por_periodo` manda siempre —con el rango dentro de un
   * solo mes tiene una única entrada y dice lo mismo que
   * `presupuesto_diario_por_pdv`, así que no hace falta ramificar según si el
   * rango cruza o no—. El respaldo solo entra en juego si la respuesta no
   * publica el desglose, es decir contra un backend anterior a este contrato.
   */
  function referenciaDePeriodo(
    respuesta: RespuestaVentaDiaria,
    codigo: string,
    periodo: string,
  ): string | null {
    const delPeriodo = respuesta.presupuesto_diario_por_periodo?.[periodo];
    if (delPeriodo) return delPeriodo[codigo] ?? null;
    return respuesta.presupuesto_diario_por_pdv?.[codigo] ?? null;
  }

  /**
   * La referencia de una celda sale del período de **su propia fecha**.
   *
   * El código de período de una fecha es su prefijo `YYYY-MM`, así que cruzarlos
   * no necesita nada más: es toda la mecánica que hace correcta la comparación
   * en un rango que cruza de mes.
   */
  function referenciaDeCelda(
    respuesta: RespuestaVentaDiaria,
    codigo: string,
    fecha: string,
  ) {
    return referenciaDePeriodo(respuesta, codigo, periodoDeFecha(fecha) ?? "");
  }

  /** Lo mismo para la fila de totales, que trae su propio desglose por período. */
  function referenciaDeTotales(respuesta: RespuestaVentaDiaria, fecha: string) {
    const totales = respuesta.totales;
    if (!totales) return null;
    const periodo = periodoDeFecha(fecha);
    const porPeriodo = totales.presupuesto_diario_por_periodo;
    if (periodo !== null && porPeriodo && periodo in porPeriodo)
      return porPeriodo[periodo] ?? null;
    return totales.presupuesto_diario ?? null;
  }

  const filaSeleccionada =
    data?.filas.find((fila) => fila.punto_venta === seleccionado) ?? null;

  return (
    <div className="pila">
      <BarraFiltros
        control={control}
        mostrar={{ rango: true, categoria: !asadero }}
        acciones={asadero ? (
          tienePermiso("PERMISO_DESCARGAR_VENTA_DIARIA_ASADERO") ? (
            <button
              type="button"
              className="boton boton--pequeno"
              onClick={() => exportarAsadero.mutate(filtros)}
              disabled={exportarAsadero.isPending || !rangoValido}
            >
              {exportarAsadero.isPending ? "Generando…" : "Exportar a Excel"}
            </button>
          ) : undefined
        ) : !tienePermiso("PERMISO_DESCARGAR_VENTA_DIARIA") ? undefined : (
          <button
            type="button"
            className="boton boton--pequeno"
            onClick={() =>
              exportar.mutate({ reporte: "venta-diaria", filtros })
            }
            disabled={exportar.isPending || !rangoValido}
          >
            {exportar.isPending ? "Generando…" : "Exportar a Excel"}
          </button>
        )}
      />

      {rangoInvertido ? (
        <div className="aviso aviso--advertencia" role="alert">
          <div>
            <strong>La fecha «desde» es posterior a «hasta».</strong>
            <p className="tenue" style={{ marginTop: 4 }}>
              Un rango invertido se rechaza en lugar de devolver la tabla vacía
              que saldría de forma natural: eso haría pasar un error de captura
              por «no hubo ventas». Corrija cualquiera de las dos fechas.
            </p>
          </div>
        </div>
      ) : null}

      {rangoExcesivo ? (
        <div className="aviso aviso--advertencia" role="alert">
          <div>
            <strong>
              El rango pedido son {dias} días y el máximo del reporte de venta
              diaria es {MAXIMO_DIAS_VENTA_DIARIA}.
            </strong>
            <p className="tenue" style={{ marginTop: 4 }}>
              El reporte pinta un día por columna, así que el tope está donde
              deja de tener sentido dibujarlo. Acorte el rango —un trimestre
              cubre el mes en curso más los dos anteriores— o consulte el
              tablero y el cumplimiento, que agregan por período en lugar de por
              día.
            </p>
          </div>
        </div>
      ) : null}

      <AvisoError error={error} />
      <AvisoError error={exportar.error} />
      <AvisoError error={exportarAsadero.error} />

      {isLoading && rangoValido ? (
        <Cargando texto="Armando la matriz de venta diaria…" />
      ) : null}

      {data ? (
        <>
          {filaSeleccionada ? (
            <Tarjeta
              titulo={`Detalle diario · ${filaSeleccionada.nombre}`}
              descripcion="La línea horizontal es el presupuesto diario derivado; si el rango cruza de mes, escalona en el cambio de período."
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
                referencia={referenciaDeCelda(
                  data,
                  filaSeleccionada.punto_venta,
                  data.fechas[0] ?? "",
                )}
                formatear={formatear}
                columnas={data.fechas.map((fecha, indice) => ({
                  fecha,
                  etiqueta: String(Number(fecha.slice(8, 10))),
                  valor: filaSeleccionada.valores[indice] ?? null,
                  esDomingo: esDomingo(fecha),
                  referencia: referenciaDeCelda(
                    data,
                    filaSeleccionada.punto_venta,
                    fecha,
                  ),
                }))}
              />
            </Tarjeta>
          ) : null}

          <Tarjeta
            titulo="Resumen del corte"
            descripcion={`Venta del ${formatearFecha(data.hasta ?? data.fecha_corte)} por punto de venta, de mayor a menor cumplimiento. Pulse un punto de venta para ver su serie del período.`}
            sinRelleno
            pie={
              <PieCalculo
                parametros={data.parametros_calculo}
                medida={medida}
                extra={
                  <p className="pie-calculo__formulas">
                    {FORMULAS.presupuesto_diario}
                  </p>
                }
              />
            }
          >
            {data.filas.length === 0 ? (
              <Vacio
                titulo="Sin venta registrada"
                detalle="El rango seleccionado no tiene días con venta ingerida en los puntos de venta elegidos."
              />
            ) : (
              (() => {
                const ultimoIndice = data.fechas.length - 1;
                const ultimaFecha = data.fechas[ultimoIndice] ?? "";

                const filasResumen: FilaResumenCorte[] = data.filas.map(
                  (fila) => {
                    const venta = fila.valores[ultimoIndice] ?? null;
                    const documentos = fila.documentos?.[ultimoIndice] ?? null;
                    return {
                      ...filaResumenDe(
                        fila.punto_venta,
                        fila.nombre,
                        referenciaDeCelda(data, fila.punto_venta, ultimaFecha),
                        venta,
                      ),
                      documentos,
                      ticketPromedio: ticketPromedioDe(venta, documentos),
                    };
                  },
                );

                // Sin presupuesto al final, nunca como si fuera 0 %: un punto sin
                // parametrizar (432 EVENTOS BUCARAMANGA) no es el peor cumplimiento,
                // es un dato que no aplica.
                const filasOrdenadas = [...filasResumen].sort((a, b) => {
                  if (a.cumplimiento === null && b.cumplimiento === null)
                    return 0;
                  if (a.cumplimiento === null) return 1;
                  if (b.cumplimiento === null) return -1;
                  return b.cumplimiento - a.cumplimiento;
                });

                const totalResumen = data.totales
                  ? (() => {
                      const venta = data.totales.valores?.[ultimoIndice] ?? null;
                      const documentos =
                        data.totales.documentos?.[ultimoIndice] ?? null;
                      return {
                        ...filaResumenDe(
                          null,
                          "Total",
                          referenciaDeTotales(data, ultimaFecha),
                          venta,
                        ),
                        documentos,
                        ticketPromedio: ticketPromedioDe(venta, documentos),
                      };
                    })()
                  : null;

                return (
                  <div className="tabla-envoltorio tabla-envoltorio--alta">
                    <table className="tabla tabla--anclada tabla--resumen-corte">
                      <caption className="solo-lectores">
                        Resumen de venta del {formatearFecha(ultimaFecha)} por
                        punto de venta, ordenado de mayor a menor
                        cumplimiento. La última fila es el total de los puntos
                        de venta que publica la respuesta.
                      </caption>
                      <thead>
                        <tr>
                          <th scope="col">C.O.</th>
                          <th scope="col" className="columna-ancla">
                            PDV
                          </th>
                          <th scope="col" className="numero">
                            Ppto día
                          </th>
                          <th scope="col" className="numero">
                            Venta
                          </th>
                          <th scope="col" className="numero">
                            % Cumplimiento
                          </th>
                          <th scope="col" className="numero">
                            Documentos
                          </th>
                          <th scope="col" className="numero">
                            Ticket promedio
                          </th>
                        </tr>
                      </thead>

                      <tbody>
                        {filasOrdenadas.map((fila, indice) => {
                          const activa =
                            fila.codigo !== null &&
                            fila.codigo === seleccionado;

                          return (
                            <tr
                              key={fila.codigo ?? String(indice)}
                              className={activa ? "fila-activa" : ""}
                            >
                              <td className="mono">{fila.codigo ?? SIN_DATO}</td>
                              <th scope="row" className="columna-ancla">
                                <button
                                  type="button"
                                  className="enlace-fila"
                                  onClick={() =>
                                    setSeleccionado(
                                      activa ? null : fila.codigo,
                                    )
                                  }
                                  disabled={fila.codigo === null}
                                >
                                  {fila.nombre}
                                </button>
                              </th>
                              <td className="numero">
                                {formatear(fila.pptoDia)}
                              </td>
                              <td className="numero">
                                {formatear(fila.venta)}
                              </td>
                              <td className="numero">
                                {fila.cumplimiento === null
                                  ? SIN_DATO
                                  : porcentaje(String(fila.cumplimiento))}
                              </td>
                              <td className="numero">
                                {fila.documentos ?? SIN_DATO}
                              </td>
                              <td className="numero">
                                {fila.ticketPromedio === null
                                  ? SIN_DATO
                                  : formatear(String(fila.ticketPromedio))}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>

                      {totalResumen ? (
                        <tfoot>
                          <tr className="fila-totales">
                            <td></td>
                            <th scope="row" className="columna-ancla">
                              <span className="fila-totales__nombre">
                                Total
                                {control.puntosSeleccionados.length > 0
                                  ? ` · ${control.puntosSeleccionados.length} elegidos`
                                  : ""}
                              </span>
                            </th>
                            <td className="numero">
                              {formatear(totalResumen.pptoDia)}
                            </td>
                            <td className="numero">
                              {formatear(totalResumen.venta)}
                            </td>
                            <td className="numero">
                              {totalResumen.cumplimiento === null
                                ? SIN_DATO
                                : porcentaje(
                                    String(totalResumen.cumplimiento),
                                  )}
                            </td>
                            <td className="numero">
                              {totalResumen.documentos ?? SIN_DATO}
                            </td>
                            <td className="numero">
                              {totalResumen.ticketPromedio === null
                                ? SIN_DATO
                                : formatear(String(totalResumen.ticketPromedio))}
                            </td>
                          </tr>
                        </tfoot>
                      ) : null}
                    </table>
                  </div>
                );
              })()
            )}
          </Tarjeta>
        </>
      ) : null}
    </div>
  );
}
