/**
 * Tablero gerencial — la pantalla que abre el gerente.
 *
 * Está construida alrededor de una sola pregunta: ¿la compañía va donde debería
 * ir hoy? La respuesta se da tres veces con distinto grado de detalle —semáforo,
 * barra contra el ideal, cifras— para que se pueda leer en tres segundos, en
 * treinta, o con la calculadora al lado.
 */

import { Link } from "react-router-dom";

import { useExportar, useTablero } from "@/api/consultas";
import type { FilaGrupo } from "@/api/tipos";
import { useAuth } from "@/auth/ContextoAuth";
import { AvisoError, Cargando, Tarjeta, Vacio } from "@/componentes/comunes";
import { BarraFiltros, useFiltros } from "@/componentes/filtros";
import { BarraContraIdeal } from "@/componentes/graficos";
import {
  Indicador,
  PieCalculo,
  Semaforo,
  notaComparativa,
} from "@/componentes/indicadores";
import { FORMULAS } from "@/utilidades/dominio";
import {
  dineroCorto,
  kilos,
  mesCorto,
  porMedida,
  porcentaje,
  puntos,
} from "@/utilidades/formato";

const MESES = Array.from({ length: 12 }, (_, indice) => indice + 1);

export function Tablero() {
  const control = useFiltros();
  const { filtros } = control;
  const { data, isLoading, error } = useTablero(filtros);
  const exportar = useExportar();
  const { tienePermiso } = useAuth();

  const medida = data?.medida ?? filtros.medida;
  const grande = (valor: string | null) =>
    medida === "kilos" ? kilos(valor) : dineroCorto(valor);
  const tonoSemaforo =
    data?.consolidado.semaforo === "VERDE"
      ? "exito"
      : data?.consolidado.semaforo === "AMARILLO"
        ? "aviso"
        : data?.consolidado.semaforo === "ROJO"
          ? "peligro"
          : undefined;
  const tonoMargen =
    data?.consolidado.margen_porcentaje == null
      ? undefined
      : data.consolidado.margen_porcentaje.trim().startsWith("-")
        ? "peligro"
        : "exito";
  const tonoCrecimiento =
    data?.consolidado.crecimiento == null
      ? undefined
      : data.consolidado.crecimiento.trim().startsWith("-")
        ? "peligro"
        : "exito";
  const tonoProyeccionMesAnterior =
    data?.variacion_proyeccion_mes_anterior == null
      ? undefined
      : data.variacion_proyeccion_mes_anterior.trim().startsWith("-")
        ? "peligro"
        : "exito";
  const tonoPromedioDesdeMayo =
    data?.variacion_venta_mayo_a_ultimo_mes == null
      ? undefined
      : data.variacion_venta_mayo_a_ultimo_mes.trim().startsWith("-")
        ? "peligro"
        : "exito";

  return (
    <div className="pila">
      <BarraFiltros
        control={control}
        mostrar={{ grupo: false, puntoVenta: false, categoria: true }}
        acciones={tienePermiso("PERMISO_DESCARGAR_TABLERO") ? (
          <button
            type="button"
            className="boton boton--pequeno"
            onClick={() => exportar.mutate({ reporte: "tablero", filtros })}
            disabled={exportar.isPending}
          >
            {exportar.isPending ? "Generando…" : "Exportar a Excel"}
          </button>
        ) : undefined}
      />

      <AvisoError error={error} />
      <AvisoError error={exportar.error} />

      {isLoading ? <Cargando texto="Consolidando el período…" /> : null}

      {data ? (
        <>
          <Tarjeta
            titulo="Consolidado de la compañía"
            descripcion={`Venta acumulada contra presupuesto del mes, al ${data.fecha_corte}.`}
            pie={
              <PieCalculo
                parametros={data.parametros_calculo}
                medida={medida}
              />
            }
          >
            <div className="consolidado">
              <div className="consolidado__foco">
                <p className="consolidado__etiqueta">Cumplimiento</p>
                <p className={`consolidado__cifra${tonoSemaforo ? ` consolidado__cifra--${tonoSemaforo}` : ""}`}>
                  {porcentaje(data.consolidado.cumplimiento)}
                </p>
                <Semaforo estado={data.consolidado.semaforo} />
                <p className="consolidado__brecha">
                  {puntos(data.consolidado.brecha)} frente al ideal
                </p>
                <p className="tenue">
                  {notaComparativa(
                    data.consolidado.cumplimiento,
                    data.consolidado.ideal,
                  )}
                </p>
              </div>

              <div className="consolidado__barra">
                <BarraContraIdeal
                  cumplimiento={data.consolidado.cumplimiento}
                  ideal={data.consolidado.ideal}
                  semaforo={data.consolidado.semaforo}
                  etiqueta="Consolidado de la compañía"
                />
              </div>
            </div>

            <div className="rejilla rejilla--indicadores">
              <Indicador
                etiqueta="Presupuesto del mes"
                valor={grande(data.consolidado.presupuesto)}
                nota={porMedida(data.consolidado.presupuesto, medida)}
              />
              <Indicador
                etiqueta="Venta acumulada"
                valor={grande(data.consolidado.venta)}
                nota={porMedida(data.consolidado.venta, medida)}
                tono="exito"
              />
              <Indicador
                etiqueta="Venta acumulada al corte del mes anterior"
                valor={grande(data.venta_mes_anterior)}
                nota={
                  <>
                    <span>
                      {data.fecha_corte_mes_anterior
                        ? `Al corte ${data.fecha_corte_mes_anterior}`
                        : "Corte anterior sin dato"}
                    </span>
                    <span
                      className={`consolidado__variacion-mensual${data.variacion_venta_mes_anterior === null ? "" : data.variacion_venta_mes_anterior.trim().startsWith("-") ? " consolidado__variacion-mensual--baja" : " consolidado__variacion-mensual--alza"}`}
                    >
                      {data.variacion_venta_mes_anterior === null
                        ? "Variación vs. mes anterior: —"
                        : `${data.variacion_venta_mes_anterior.trim().startsWith("-") ? "▼ " : "▲ "}${porcentaje(data.variacion_venta_mes_anterior)} vs. mes anterior`}
                    </span>
                  </>
                }
              />
              <Indicador
                etiqueta="Proyección al cierre"
                valor={grande(data.consolidado.proyeccion)}
                nota={`${porcentaje(data.consolidado.cumplimiento_proyectado)} del presupuesto`}
                pista={<p className="formula">{FORMULAS.proyeccion}</p>}
                tono={tonoSemaforo}
              />
              <Indicador
                etiqueta="Proyección al cierre vs. mes anterior"
                valor={grande(data.consolidado.proyeccion)}
                nota={
                  <>
                    <span>
                      Cierre mes anterior: {porMedida(data.venta_cierre_mes_anterior, medida)}
                    </span>
                    <span
                      className={`consolidado__variacion-mensual${tonoProyeccionMesAnterior ? ` consolidado__variacion-mensual--${tonoProyeccionMesAnterior}` : ""}`}
                    >
                      {data.variacion_proyeccion_mes_anterior === null
                        ? "Variación vs. cierre anterior: —"
                        : `${data.variacion_proyeccion_mes_anterior.trim().startsWith("-") ? "▼ " : "▲ "}${porcentaje(data.variacion_proyeccion_mes_anterior)} vs. cierre anterior`}
                    </span>
                  </>
                }
                pista={
                  <p className="formula">
                    (proyección actual - cierre del mes anterior) / cierre del mes anterior
                  </p>
                }
                tono={tonoProyeccionMesAnterior}
              />
              <Indicador
                etiqueta="Venta diaria requerida"
                valor={grande(data.consolidado.venta_diaria_requerida)}
                nota="Para llegar al presupuesto con los días que quedan"
                pista={
                  <p className="formula">{FORMULAS.venta_diaria_requerida}</p>
                }
                tono="aviso"
              />
              <Indicador
                etiqueta="Venta diaria promedio"
                valor={grande(data.consolidado.venta_diaria_promedio)}
                nota="Ritmo actual"
                pista={
                  <p className="formula">{FORMULAS.venta_diaria_promedio}</p>
                }
                tono="exito"
              />
              <Indicador
                etiqueta="Crecimiento año anterior"
                valor={porcentaje(data.consolidado.crecimiento)}
                nota={`Año anterior: ${porMedida(data.consolidado.venta_anio_anterior, medida)}`}
                pista={<p className="formula">{FORMULAS.crecimiento}</p>}
                tono={tonoCrecimiento}
              />
              <Indicador
                etiqueta="Venta promedio mensual desde mayo"
                valor={grande(data.venta_promedio_desde_mayo)}
                nota={
                  <>
                    <span>
                      {data.mes_ultimo_cerrado_promedio === null
                        ? "Sin meses completos desde mayo"
                        : `Promedio mayo–${mesCorto(`${data.periodo.slice(0, 4)}-${String(data.mes_ultimo_cerrado_promedio).padStart(2, "0")}`)} ${data.periodo.slice(0, 4)}`}
                    </span>
                    <span>
                      Mayo: {grande(data.venta_mayo)} · Último mes cerrado: {grande(data.venta_ultimo_mes_cerrado)}
                    </span>
                    <span
                      className={`consolidado__variacion-mensual${tonoPromedioDesdeMayo ? ` consolidado__variacion-mensual--${tonoPromedioDesdeMayo}` : ""}`}
                    >
                      {data.variacion_venta_mayo_a_ultimo_mes === null
                        ? "Variación mayo vs. último mes cerrado: —"
                        : `${data.variacion_venta_mayo_a_ultimo_mes.trim().startsWith("-") ? "▼ " : "▲ "}${porcentaje(data.variacion_venta_mayo_a_ultimo_mes)} último mes vs. mayo`}
                    </span>
                  </>
                }
                pista={
                  <p className="formula">
                    Promedio mensual desde mayo hasta el último mes completo. Variación: (venta último mes cerrado − venta mayo) / venta mayo.
                  </p>
                }
                tono={tonoPromedioDesdeMayo}
              />
              <Indicador
                etiqueta="Margen"
                valor={porcentaje(data.consolidado.margen_porcentaje)}
                nota={porMedida(data.consolidado.margen_valor, "valor")}
                pista={
                  <>
                    <p className="formula">{FORMULAS.margen_porcentaje}</p>
                    <p className="tenue">
                      Se calcula sobre los totales, nunca promediando el
                      porcentaje que envía SIESA línea a línea.
                    </p>
                  </>
                }
                tono={tonoMargen}
              />
            </div>
          </Tarjeta>

          <Tarjeta
            titulo="Los cuatro grupos"
            descripcion="Cada barra llega hasta donde se ha cumplido; la marca vertical es dónde debería ir hoy."
          >
            {data.grupos.length === 0 ? (
              <Vacio
                titulo="Sin grupos"
                detalle="El período no tiene agrupaciones con presupuesto."
              />
            ) : (
              <div className="rejilla rejilla--grupos">
                {data.grupos.map((grupo) => (
                  <TarjetaGrupo
                    key={grupo.codigo}
                    grupo={grupo}
                    medida={medida}
                  />
                ))}
              </div>
            )}
          </Tarjeta>

          <Tarjeta
            titulo="Venta sin presupuesto"
            descripcion="Puntos que venden y no están presupuestados. Se reportan aparte y no descuadran el consolidado."
          >
            {data.sin_presupuesto.length === 0 ? (
              <p className="tenue">
                Ningún punto de venta registró venta fuera del presupuesto en
                este período.
              </p>
            ) : (
              <ul className="lista-simple">
                {data.sin_presupuesto.map((punto) => (
                  <li key={punto.codigo_co}>
                    <span className="mono">{punto.codigo_co}</span>{" "}
                    {punto.nombre}
                    <strong className="empujar">
                      {porMedida(punto.venta, medida)}
                    </strong>
                  </li>
                ))}
              </ul>
            )}
          </Tarjeta>

          <Tarjeta
            titulo={`Venta por punto de venta · ${data.ventas_anuales.anio}`}
            descripcion={`Ventas de enero a diciembre de ${data.ventas_anuales.anio}, consolidadas por punto de venta y totalizadas por mes.`}
            sinRelleno
          >
            {data.ventas_anuales.filas.length === 0 ? (
              <Vacio
                titulo="Sin puntos de venta"
                detalle="Ningún punto coincide con el alcance o los filtros seleccionados."
              />
            ) : (
              <div className="tabla-envoltorio tabla-envoltorio--alta">
                <table className="tabla tabla--anclada">
                  <caption className="solo-lectores">
                    Venta por punto de venta, desglosada por mes en
                    {" "}{data.ventas_anuales.anio}, en {medida === "kilos" ? "kilos" : "pesos"}.
                  </caption>
                  <thead>
                    <tr>
                      <th scope="col" className="columna-ancla">Punto de venta</th>
                      {MESES.map((mes) => (
                        <th key={mes} scope="col" className="numero">
                          {mesCorto(`${data.ventas_anuales.anio}-${String(mes).padStart(2, "0")}`)}
                        </th>
                      ))}
                      <th scope="col" className="numero">Total año</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.ventas_anuales.filas.map((fila) => (
                      <tr key={fila.punto_venta}>
                        <th scope="row" className="columna-ancla">
                          <span className="mono">{fila.punto_venta}</span> · {fila.nombre}
                        </th>
                        {MESES.map((mes, indice) => (
                          <td key={mes} className="numero">
                            {porMedida(fila.valores[indice], medida)}
                          </td>
                        ))}
                        <td className="numero">
                          <strong>{porMedida(fila.total, medida)}</strong>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot>
                    <tr>
                      <th scope="row" className="columna-ancla">
                        <span className="fila-totales__nombre">Total compañía</span>
                      </th>
                      {MESES.map((mes, indice) => (
                        <td key={mes} className="numero">
                          {porMedida(data.ventas_anuales.totales_mensuales[indice], medida)}
                        </td>
                      ))}
                      <td className="numero">
                        <strong>{porMedida(data.ventas_anuales.total, medida)}</strong>
                      </td>
                    </tr>
                  </tfoot>
                </table>
              </div>
            )}
          </Tarjeta>
        </>
      ) : null}
    </div>
  );
}

function TarjetaGrupo({
  grupo,
  medida,
}: {
  grupo: FilaGrupo;
  medida: "valor" | "kilos";
}) {
  return (
    <article className="grupo">
      <header className="grupo__cabecera">
        <div>
          <h3>{grupo.nombre}</h3>
          <span className="tenue mono">{grupo.codigo}</span>
        </div>
        <Semaforo estado={grupo.semaforo} />
      </header>

      <p className="grupo__cifra">{porcentaje(grupo.cumplimiento)}</p>
      <p className="tenue">
        Ideal {porcentaje(grupo.ideal)} · brecha {puntos(grupo.brecha)}
      </p>

      <BarraContraIdeal
        cumplimiento={grupo.cumplimiento}
        ideal={grupo.ideal}
        semaforo={grupo.semaforo}
        etiqueta={grupo.nombre}
        compacta
      />

      <dl className="grupo__detalle">
        <div>
          <dt>Presupuesto</dt>
          <dd>{porMedida(grupo.presupuesto, medida)}</dd>
        </div>
        <div>
          <dt>Venta</dt>
          <dd>{porMedida(grupo.venta, medida)}</dd>
        </div>
        <div>
          <dt>Proyección</dt>
          <dd>
            {porMedida(grupo.proyeccion, medida)}{" "}
            <span className="tenue">
              ({porcentaje(grupo.cumplimiento_proyectado)})
            </span>
          </dd>
        </div>
        <div>
          <dt>V. diaria requerida</dt>
          <dd>{porMedida(grupo.venta_diaria_requerida, medida)}</dd>
        </div>
      </dl>

      <Link
        className="grupo__enlace"
        to={`/cumplimiento?grupo=${grupo.codigo}&medida=${medida}`}
      >
        Ver los puntos de venta del grupo →
      </Link>
    </article>
  );
}
