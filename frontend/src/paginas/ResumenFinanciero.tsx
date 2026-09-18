/**
 * Resumen financiero consolidado — instancia Grupo Santacruz.
 *
 * Balance general, estado de resultados e indicadores del libro mayor que
 * carga `python -m app.infrastructure.cargar_libro_mayor`. Una sola pantalla,
 * a propósito: es el primer corte del módulo y responde la pregunta que pide
 * el negocio —¿cómo va la compañía este mes, según el libro mayor?— antes de
 * abrir el detalle por cuenta o por tercero.
 */

import { useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  useBalanceGeneral,
  useEstadoResultados,
  useIndicadoresFinancieros,
  useSerieBalanceGeneral,
  useSerieEstadoResultados,
} from "@/api/consultasFinanciero";
import { AvisoError, Cargando, Tarjeta } from "@/componentes/comunes";
import { Indicador } from "@/componentes/indicadores";
import { dinero, dineroCorto, numero, porcentaje } from "@/utilidades/formato";

/** `"2026-07"` del `<input type="month">` a `"202607"` que pide la API. */
function aPeriodoApi(mes: string): string {
  return mes.replace("-", "");
}

function periodoActual(): string {
  const hoy = new Date();
  return `${hoy.getFullYear()}-${String(hoy.getMonth() + 1).padStart(2, "0")}`;
}

/** Los `n` períodos `AAAAMM` que terminan en `mes` (`"2026-07"`), de más viejo a más nuevo. */
function ultimosPeriodos(mes: string, n: number): string[] {
  const [anioTexto, mesTexto] = mes.split("-");
  const anio = Number(anioTexto ?? 0);
  const mesNumero = Number(mesTexto ?? 1);
  const periodos: string[] = [];
  for (let i = n - 1; i >= 0; i--) {
    const fecha = new Date(anio, mesNumero - 1 - i, 1);
    periodos.push(`${fecha.getFullYear()}${String(fecha.getMonth() + 1).padStart(2, "0")}`);
  }
  return periodos;
}

/** `"202607"` → `"jul 2026"`, para el eje de la tendencia. */
function mesCortoDePeriodo(periodo: string): string {
  const anio = periodo.slice(0, 4);
  const mesNumero = periodo.slice(4, 6);
  const fecha = new Date(Number(anio), Number(mesNumero) - 1, 1);
  return new Intl.DateTimeFormat("es-CO", { month: "short", year: "2-digit" })
    .format(fecha)
    .replace(".", "");
}

interface FilaAnalisis {
  etiqueta: string;
  actual: string | null;
  base: string | null;
  anterior: string | null;
}

/** Participación de `actual` sobre `base` (análisis vertical). */
function participacion(actual: string | null, base: string | null): string | null {
  if (actual === null || base === null || Number(base) === 0) return null;
  return String(Math.abs(Number(actual) / Number(base)));
}

/** Variación porcentual de `actual` contra `anterior` (análisis horizontal). */
function variacionPorcentual(actual: string | null, anterior: string | null): string | null {
  if (actual === null || anterior === null || Number(anterior) === 0) return null;
  return String((Number(actual) - Number(anterior)) / Math.abs(Number(anterior)));
}

function variacionAbsoluta(actual: string | null, anterior: string | null): string | null {
  if (actual === null || anterior === null) return null;
  return String(Number(actual) - Number(anterior));
}

export function ResumenFinanciero() {
  const [mes, setMes] = useState(periodoActual());
  const periodo = aPeriodoApi(mes);
  const filtros = { periodo };

  const balance = useBalanceGeneral(filtros);
  const resultados = useEstadoResultados(filtros);
  const indicadores = useIndicadoresFinancieros(filtros);

  const periodosSerie = ultimosPeriodos(mes, 6);
  const serie = useSerieEstadoResultados(periodosSerie);
  const serieBalance = useSerieBalanceGeneral(periodosSerie);

  const cargando = balance.isLoading || resultados.isLoading || indicadores.isLoading;
  const error = balance.error ?? resultados.error ?? indicadores.error;

  const datosResultados = resultados.data
    ? [
        { nombre: "Ingresos", valor: Number(resultados.data.ingresos) },
        { nombre: "Costos", valor: Number(resultados.data.costos) },
        { nombre: "Gastos", valor: Number(resultados.data.gastos) },
      ]
    : [];

  // Estructura de financiación: de qué está hecho el activo, pasivo o
  // patrimonio. En magnitud absoluta a propósito —la torta reparte peso, no
  // signo— con el descuadre ya avisado aparte, arriba.
  const datosFinanciamiento = balance.data
    ? [
        { nombre: "Pasivo", valor: Math.abs(Number(balance.data.pasivo)), color: "var(--peligro)" },
        { nombre: "Patrimonio", valor: Math.abs(Number(balance.data.patrimonio)), color: "var(--acento)" },
      ]
    : [];

  const datosTendencia = periodosSerie.map((p, indice) => ({
    periodo: mesCortoDePeriodo(p),
    ingresos: serie[indice]?.data ? Number(serie[indice]?.data?.ingresos) : null,
    utilidad_neta: serie[indice]?.data ? Number(serie[indice]?.data?.utilidad_neta) : null,
  }));
  const serieCargando = serie.some((consulta) => consulta.isLoading);

  // Análisis vertical y horizontal: el mes elegido es el último punto de la
  // serie de 6 meses que ya se pidió para la tendencia, así que el mes
  // anterior sale de ahí sin una petición nueva.
  const resultadosAnterior = serie[serie.length - 2]?.data ?? null;
  const balanceAnterior = serieBalance[serieBalance.length - 2]?.data ?? null;

  const filasAnalisis: FilaAnalisis[] = balance.data && resultados.data
    ? [
        { etiqueta: "Activo", actual: balance.data.activo, base: balance.data.activo, anterior: balanceAnterior?.activo ?? null },
        { etiqueta: "Pasivo", actual: balance.data.pasivo, base: balance.data.activo, anterior: balanceAnterior?.pasivo ?? null },
        { etiqueta: "Patrimonio", actual: balance.data.patrimonio, base: balance.data.activo, anterior: balanceAnterior?.patrimonio ?? null },
        { etiqueta: "Ingresos", actual: resultados.data.ingresos, base: resultados.data.ingresos, anterior: resultadosAnterior?.ingresos ?? null },
        { etiqueta: "Costos", actual: resultados.data.costos, base: resultados.data.ingresos, anterior: resultadosAnterior?.costos ?? null },
        { etiqueta: "Gastos", actual: resultados.data.gastos, base: resultados.data.ingresos, anterior: resultadosAnterior?.gastos ?? null },
        { etiqueta: "Utilidad neta", actual: resultados.data.utilidad_neta, base: resultados.data.ingresos, anterior: resultadosAnterior?.utilidad_neta ?? null },
      ]
    : [];

  return (
    <div className="pila">
      <Tarjeta
        titulo="Resumen financiero"
        descripcion="Balance general y estado de resultados del libro mayor, por período contable."
        acciones={
          <form
            className="formulario formulario--linea"
            onSubmit={(evento) => evento.preventDefault()}
          >
            <label className="campo">
              <span>Período</span>
              <input
                className="campo__control"
                type="month"
                value={mes}
                onChange={(evento) => setMes(evento.target.value)}
                required
              />
            </label>
          </form>
        }
      >
        <AvisoError error={error} />
        {cargando ? <Cargando texto="Cargando el resumen financiero…" /> : null}

        {!cargando && balance.data ? (
          <>
            <h3>Balance general</h3>
            <div className="rejilla rejilla--indicadores">
              <Indicador etiqueta="Activo" valor={dinero(balance.data.activo)} tamano="mediano" />
              <Indicador etiqueta="Pasivo" valor={dinero(balance.data.pasivo)} tamano="mediano" />
              <Indicador etiqueta="Patrimonio" valor={dinero(balance.data.patrimonio)} tamano="mediano" />
              <Indicador
                etiqueta="Utilidad del ejercicio"
                valor={dinero(balance.data.utilidad_del_ejercicio)}
                tamano="mediano"
                nota="Ingresos − costos − gastos acumulados del año, aún sin cerrar contra patrimonio."
                tono={balance.data.utilidad_del_ejercicio.trim().startsWith("-") ? "peligro" : "exito"}
              />
              <Indicador
                etiqueta="Descuadre"
                valor={dinero(balance.data.descuadre)}
                tamano="mediano"
                nota="Activo − pasivo − patrimonio − utilidad del ejercicio. Debe ser cero; si no lo es, el descuadre viene del origen."
                tono={balance.data.descuadre === "0.00" ? undefined : "aviso"}
              />
            </div>
          </>
        ) : null}

        {!cargando && resultados.data ? (
          <>
            <h3>Estado de resultados</h3>
            <div className="rejilla rejilla--indicadores">
              <Indicador etiqueta="Ingresos" valor={dinero(resultados.data.ingresos)} tamano="mediano" />
              <Indicador etiqueta="Costos" valor={dinero(resultados.data.costos)} tamano="mediano" />
              <Indicador etiqueta="Gastos" valor={dinero(resultados.data.gastos)} tamano="mediano" />
              <Indicador
                etiqueta="Utilidad neta"
                valor={dinero(resultados.data.utilidad_neta)}
                tamano="mediano"
                tono={resultados.data.utilidad_neta.trim().startsWith("-") ? "peligro" : "exito"}
              />
            </div>
          </>
        ) : null}

        {!cargando && indicadores.data ? (
          <>
            <h3>Indicadores</h3>
            <div className="rejilla rejilla--indicadores">
              <Indicador
                etiqueta="Liquidez corriente"
                valor={numero(indicadores.data.liquidez_corriente, 2)}
                nota="Activo corriente / pasivo corriente"
              />
              <Indicador
                etiqueta="Endeudamiento"
                valor={porcentaje(indicadores.data.endeudamiento)}
                nota="Pasivo / activo"
              />
              <Indicador
                etiqueta="Margen neto"
                valor={porcentaje(indicadores.data.margen_neto)}
                nota="Utilidad neta / ingresos"
              />
            </div>
          </>
        ) : null}
      </Tarjeta>

      <Tarjeta
        titulo="Análisis vertical y horizontal"
        descripcion="Participación de cada cifra sobre su total (activo o ingresos) y variación contra el mes anterior."
      >
        {cargando || serieCargando ? (
          <Cargando texto="Cargando el análisis…" />
        ) : filasAnalisis.length === 0 ? null : (
          <div className="tabla-envoltorio">
            <table className="tabla">
              <thead>
                <tr>
                  <th scope="col">Cifra</th>
                  <th scope="col" className="numero">Valor</th>
                  <th scope="col" className="numero">% vertical</th>
                  <th scope="col" className="numero">Mes anterior</th>
                  <th scope="col" className="numero">Variación</th>
                  <th scope="col" className="numero">% horizontal</th>
                </tr>
              </thead>
              <tbody>
                {filasAnalisis.map((fila) => (
                  <tr key={fila.etiqueta}>
                    <th scope="row">{fila.etiqueta}</th>
                    <td className="numero">{dinero(fila.actual)}</td>
                    <td className="numero">
                      {participacion(fila.actual, fila.base) === null
                        ? "—"
                        : porcentaje(participacion(fila.actual, fila.base))}
                    </td>
                    <td className="numero suave">{dinero(fila.anterior)}</td>
                    <td className="numero">{dinero(variacionAbsoluta(fila.actual, fila.anterior))}</td>
                    <td className="numero">
                      {variacionPorcentual(fila.actual, fila.anterior) === null
                        ? "—"
                        : porcentaje(variacionPorcentual(fila.actual, fila.anterior))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Tarjeta>

      <div className="rejilla rejilla--panel">
        <Tarjeta titulo="Ingresos, costos y gastos" descripcion="Del período elegido.">
          {resultados.isLoading ? (
            <Cargando texto="Cargando…" />
          ) : (
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={datosResultados}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--borde)" />
                <XAxis dataKey="nombre" stroke="var(--texto-suave)" fontSize={12} />
                <YAxis stroke="var(--texto-suave)" fontSize={12} tickFormatter={(v) => dineroCorto(String(v))} width={70} />
                <Tooltip formatter={(v) => dinero(String(v ?? 0))} contentStyle={{ background: "var(--superficie)", border: "1px solid var(--borde)" }} />
                <Bar dataKey="valor" fill="var(--acento)" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </Tarjeta>

        <Tarjeta
          titulo="Estructura de financiación"
          descripcion="Cuánto del activo viene de deuda y cuánto de patrimonio."
        >
          {balance.isLoading ? (
            <Cargando texto="Cargando…" />
          ) : (
            <ResponsiveContainer width="100%" height={260}>
              <PieChart>
                <Pie
                  data={datosFinanciamiento}
                  dataKey="valor"
                  nameKey="nombre"
                  innerRadius={60}
                  outerRadius={90}
                  paddingAngle={2}
                >
                  {datosFinanciamiento.map((entrada) => (
                    <Cell key={entrada.nombre} fill={entrada.color} />
                  ))}
                </Pie>
                <Tooltip formatter={(v) => dinero(String(v ?? 0))} contentStyle={{ background: "var(--superficie)", border: "1px solid var(--borde)" }} />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          )}
        </Tarjeta>
      </div>

      <Tarjeta
        titulo="Tendencia de los últimos 6 meses"
        descripcion="Ingresos y utilidad neta, mes a mes."
      >
        {serieCargando ? (
          <Cargando texto="Cargando la tendencia…" />
        ) : (
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={datosTendencia}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--borde)" />
              <XAxis dataKey="periodo" stroke="var(--texto-suave)" fontSize={12} />
              <YAxis stroke="var(--texto-suave)" fontSize={12} tickFormatter={(v) => dineroCorto(String(v))} width={70} />
              <Tooltip formatter={(v) => dinero(String(v ?? 0))} contentStyle={{ background: "var(--superficie)", border: "1px solid var(--borde)" }} />
              <Legend />
              <Line type="monotone" dataKey="ingresos" name="Ingresos" stroke="var(--acento)" strokeWidth={2.5} dot connectNulls />
              <Line type="monotone" dataKey="utilidad_neta" name="Utilidad neta" stroke="var(--exito)" strokeWidth={2.5} dot connectNulls />
            </LineChart>
          </ResponsiveContainer>
        )}
      </Tarjeta>
    </div>
  );
}
