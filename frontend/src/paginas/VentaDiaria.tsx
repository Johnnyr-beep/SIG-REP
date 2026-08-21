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
 * ── Lo que esta pantalla no pinta ───────────────────────────────────────────
 *
 * No hay columna de número de documentos, y no está pendiente de cargar: la
 * fuente de SIESA no entrega ese dato (`docs/INTEGRACION-SIESA.md` §4.4) y no se
 * puede aproximar contando líneas, porque una venta de ocho productos son ocho
 * líneas y **un** documento. Reservar la columna, aunque fuera con un «—»,
 * sugeriría que el dato existe y está fallando; lo cierto es que todavía no se
 * puede pedir.
 */

import { useState } from "react";

import { useExportar, useVentaDiaria } from "@/api/consultas";
import type { FilaVentaDiaria, RespuestaVentaDiaria } from "@/api/tipos";
import { MAXIMO_DIAS_VENTA_DIARIA } from "@/api/tipos";
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
  comparaParaGrafico,
  diaDelMes,
  esDomingo,
  fecha as formatearFecha,
  mesCorto,
  periodoDeFecha,
  porMedida,
} from "@/utilidades/formato";

/** Una referencia diaria por período tocado, tal como se pinta bajo el nombre. */
type ReferenciasPorPeriodo = [periodo: string, valor: string | null][];

/**
 * La línea de referencia de una fila, bajo su nombre.
 *
 * Con un solo período se escribe la cifra y ya. Cuando el rango cruza de mes y
 * las referencias difieren se escriben **todas**, una por mes: elegir una sería
 * publicar la referencia equivocada para la mitad de las columnas, y resumirlas
 * en un promedio sería inventar un número que no existe en ningún sitio.
 */
function NotaReferencia({
  referencias,
  formatear,
}: {
  referencias: ReferenciasPorPeriodo;
  formatear: (valor: string | null) => string;
}) {
  if (referencias.length === 0) {
    return <span className="columna-ancla__nota">Ppto/día: {SIN_DATO}</span>;
  }

  const distintas = new Set(referencias.map(([, valor]) => valor ?? ""));

  if (distintas.size <= 1) {
    const unica = referencias[0]?.[1] ?? null;
    return (
      <span className="columna-ancla__nota">
        Ppto/día: {unica === null ? SIN_DATO : formatear(unica)}
      </span>
    );
  }

  return (
    <span className="columna-ancla__nota">
      Ppto/día:{" "}
      {referencias.map(([periodo, valor], indice) => (
        <span key={periodo}>
          {indice === 0 ? "" : " · "}
          {mesCorto(periodo)} {valor === null ? SIN_DATO : formatear(valor)}
        </span>
      ))}
    </span>
  );
}

/** Celda de un día: la cifra, la marca ▲▼ y su lectura para el lector de pantalla. */
function CeldaDia({
  valor,
  referencia,
  fecha,
  formatear,
}: {
  valor: string | null;
  referencia: string | null;
  fecha: string;
  formatear: (valor: string | null) => string;
}) {
  const comparacion = comparaParaGrafico(valor, referencia);
  const tono =
    comparacion === null
      ? ""
      : comparacion >= 0
        ? " celda--sobre"
        : " celda--bajo";

  return (
    <td
      className={`numero${tono}${esDomingo(fecha) ? " columna-domingo" : ""}`}
    >
      {formatear(valor)}
      {comparacion === null ? null : (
        <>
          <span className="celda__marca" aria-hidden="true">
            {comparacion >= 0 ? "▲" : "▼"}
          </span>
          <span className="solo-lectores">
            {comparacion >= 0
              ? " por encima del presupuesto diario"
              : " por debajo del presupuesto diario"}
          </span>
        </>
      )}
    </td>
  );
}

export function VentaDiaria() {
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

  const { data, isLoading, error } = useVentaDiaria(filtros, rangoValido);
  const exportar = useExportar();

  const [seleccionado, setSeleccionado] = useState<string | null>(null);

  const medida = data?.medida ?? filtros.medida;
  const formatear = (valor: string | null) => porMedida(valor, medida);

  /** Los períodos que toca el rango; uno solo en el modo de siempre. */
  function periodosDe(respuesta: RespuestaVentaDiaria): string[] {
    if (respuesta.periodos?.length) return respuesta.periodos;
    const unico = respuesta.periodo ?? filtros.periodo;
    return unico ? [unico] : [];
  }

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

  function referenciasDeFila(
    respuesta: RespuestaVentaDiaria,
    fila: FilaVentaDiaria,
  ): ReferenciasPorPeriodo {
    return periodosDe(respuesta).map((periodo) => [
      periodo,
      referenciaDePeriodo(respuesta, fila.punto_venta, periodo),
    ]);
  }

  function referenciasDeTotales(
    respuesta: RespuestaVentaDiaria,
  ): ReferenciasPorPeriodo {
    const totales = respuesta.totales;
    if (!totales) return [];
    return periodosDe(respuesta).map((periodo) => [
      periodo,
      totales.presupuesto_diario_por_periodo?.[periodo] ??
        totales.presupuesto_diario ??
        null,
    ]);
  }

  const filaSeleccionada =
    data?.filas.find((fila) => fila.punto_venta === seleccionado) ?? null;

  return (
    <div className="pila">
      <BarraFiltros
        control={control}
        mostrar={{ rango: true }}
        acciones={
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
        }
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
            titulo="Venta día por día"
            descripcion="Pulse un punto de venta para ver su serie. ▲ el día superó el presupuesto diario; ▼ quedó por debajo. La fila de totales queda fijada al pie."
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
              <div className="tabla-envoltorio tabla-envoltorio--alta">
                <table className="tabla tabla--anclada tabla--matriz">
                  <caption className="solo-lectores">
                    Venta por punto de venta y día, del{" "}
                    {formatearFecha(data.desde)} al{" "}
                    {formatearFecha(data.hasta ?? data.fecha_corte)}. La última
                    fila es el total de los puntos de venta que publica la
                    respuesta.
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
                      const codigo = fila.punto_venta;
                      const activa = codigo !== null && codigo === seleccionado;

                      return (
                        <tr
                          key={codigo ?? String(indice)}
                          className={activa ? "fila-activa" : ""}
                        >
                          <th scope="row" className="columna-ancla">
                            <button
                              type="button"
                              className="enlace-fila"
                              onClick={() =>
                                setSeleccionado(activa ? null : codigo)
                              }
                              disabled={codigo === null}
                            >
                              {fila.nombre}
                            </button>
                            <NotaReferencia
                              referencias={referenciasDeFila(data, fila)}
                              formatear={formatear}
                            />
                          </th>

                          {data.fechas.map((fecha, columna) => (
                            <CeldaDia
                              key={fecha}
                              fecha={fecha}
                              valor={fila.valores[columna] ?? null}
                              referencia={referenciaDeCelda(
                                data,
                                codigo,
                                fecha,
                              )}
                              formatear={formatear}
                            />
                          ))}

                          <td className="numero columna-total">
                            {formatear(fila.total)}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>

                  {/*
                    `totales` llega en un campo propio de la respuesta, no como una
                    fila más de `filas`: mezclada habría que reconocerla por su
                    nombre y esa convención se rompe el día que alguien bautice
                    «TOTAL» un punto de venta. Va en un `<tfoot>`, que es la
                    semántica correcta y además la mantiene pegada al pie de la
                    tabla sin sacarla del mismo `<table>`, de modo que sus celdas
                    siguen alineadas con las columnas al desplazar en horizontal.
                  */}
                  {data.totales ? (
                    <tfoot>
                      <tr className="fila-totales">
                        <th scope="row" className="columna-ancla">
                          {/*
                            No dice «de la compañía»: el total respeta el alcance
                            del usuario, así que para un JEFE_PDV es el de sus
                            puntos y esa etiqueta sería sencillamente falsa.
                          */}
                          <span className="fila-totales__nombre">
                            Total
                            {control.puntosSeleccionados.length > 0
                              ? ` · ${control.puntosSeleccionados.length} elegidos`
                              : ""}
                          </span>
                          <NotaReferencia
                            referencias={referenciasDeTotales(data)}
                            formatear={formatear}
                          />
                        </th>

                        {data.fechas.map((fecha, columna) => (
                          <CeldaDia
                            key={fecha}
                            fecha={fecha}
                            valor={data.totales.valores?.[columna] ?? null}
                            referencia={referenciaDeTotales(data, fecha)}
                            formatear={formatear}
                          />
                        ))}

                        <td className="numero columna-total">
                          {formatear(data.totales.total)}
                        </td>
                      </tr>
                    </tfoot>
                  ) : null}
                </table>
              </div>
            )}
          </Tarjeta>
        </>
      ) : null}
    </div>
  );
}
