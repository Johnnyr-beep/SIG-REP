import { Fragment, useMemo, useState } from "react";

import { MODO_EJEMPLOS } from "@/api/cliente";
import { useSerieBalanceComprobacion } from "@/api/consultasFinanciero";
import type { FilaBalanceComprobacion } from "@/api/tipos";
import { AvisoError, Cargando, Tarjeta, Vacio } from "@/componentes/comunes";

const MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];
const CLASES_PYG = ["Ingresos", "Costos", "Gastos"] as const;

type ClasePyG = (typeof CLASES_PYG)[number];

interface MovimientoMes {
  disponible: boolean;
  ingresos: number | null;
  costos: number | null;
  gastos: number | null;
}

interface CuentaAnual {
  clase: ClasePyG;
  codigo: string;
  descripcion: string;
  valores: Array<number | null>;
}

function montoMovimiento(fila: FilaBalanceComprobacion): number | null {
  if (fila.clase === "Ingresos") return Number(fila.creditos) - Number(fila.debitos);
  if (fila.clase.startsWith("Costo")) return Number(fila.debitos) - Number(fila.creditos);
  if (fila.clase === "Gastos") return Number(fila.debitos) - Number(fila.creditos);
  return null;
}

function periodoDe(anio: number, mes: number): string {
  return `${anio}${String(mes).padStart(2, "0")}`;
}

function dineroMillones(valor: number | null): string {
  if (valor === null || !Number.isFinite(valor)) return "—";
  return `$${new Intl.NumberFormat("es-CO", { maximumFractionDigits: 0 }).format(valor / 1_000_000)} M`;
}

function porcentaje(valor: number | null): string {
  if (valor === null || !Number.isFinite(valor)) return "—";
  return `${new Intl.NumberFormat("es-CO", { maximumFractionDigits: 1 }).format(valor * 100)} %`;
}

function totalDe(meses: MovimientoMes[], campo: ClasePyG): number | null {
  const valores = meses
    .map((mes) => mes[campo.toLocaleLowerCase() as "ingresos" | "costos" | "gastos"])
    .filter((valor): valor is number => valor !== null);
  return valores.length ? valores.reduce((total, valor) => total + valor, 0) : null;
}

export function IngresosCostos() {
  const anioActual = new Date().getFullYear();
  const [anio, setAnio] = useState(anioActual);
  const periodoMaximo = anio === anioActual ? new Date().getMonth() + 1 : 12;
  const periodos = useMemo(
    () => Array.from({ length: periodoMaximo }, (_, indice) => periodoDe(anio, indice + 1)),
    [anio, periodoMaximo],
  );
  const consultas = useSerieBalanceComprobacion(periodos);
  const cargando = consultas.some((consulta) => consulta.isLoading);
  const error = consultas.find((consulta) => consulta.error)?.error;

  const meses = useMemo<MovimientoMes[]>(() => {
    return Array.from({ length: 12 }, (_, indice) => {
      const filas = consultas[indice]?.data?.filas;
      if (!filas?.length) {
        return { disponible: false, ingresos: null, costos: null, gastos: null };
      }

      const filasIngresos = filas.filter((fila) => fila.clase === "Ingresos");
      const filasCostos = filas.filter((fila) => fila.clase.startsWith("Costo"));
      const filasGastos = filas.filter((fila) => fila.clase === "Gastos");
      const sumar = (cuentas: FilaBalanceComprobacion[]) =>
        cuentas.reduce((total, fila) => total + (montoMovimiento(fila) ?? 0), 0);
      const disponible = filasIngresos.length + filasCostos.length + filasGastos.length > 0;

      return {
        disponible,
        ingresos: filasIngresos.length ? sumar(filasIngresos) : null,
        costos: filasCostos.length ? sumar(filasCostos) : null,
        gastos: filasGastos.length ? sumar(filasGastos) : null,
      };
    });
  }, [consultas]);

  const cuentas = useMemo(() => {
    const porCuenta = new Map<string, CuentaAnual>();
    consultas.forEach((consulta, indiceMes) => {
      for (const fila of consulta.data?.filas ?? []) {
        const movimiento = montoMovimiento(fila);
        if (movimiento === null) continue;
        const clase: ClasePyG = fila.clase === "Ingresos"
          ? "Ingresos"
          : fila.clase.startsWith("Costo")
            ? "Costos"
            : "Gastos";
        const clave = `${clase}-${fila.mayor_iii}`;
        let cuenta = porCuenta.get(clave);
        if (!cuenta) {
          cuenta = {
            clase,
            codigo: fila.mayor_iii,
            descripcion: fila.descripcion ?? "Sin descripción en SIESA",
            valores: Array.from({ length: 12 }, () => null),
          };
          porCuenta.set(clave, cuenta);
        }
        cuenta.valores[indiceMes] = (cuenta.valores[indiceMes] ?? 0) + movimiento;
      }
    });
    return porCuenta;
  }, [consultas]);

  const ingresos = totalDe(meses, "Ingresos");
  const costos = totalDe(meses, "Costos");
  const gastos = totalDe(meses, "Gastos");
  const utilidad = ingresos === null || costos === null || gastos === null
    ? null
    : ingresos - costos - gastos;
  const margenBruto = ingresos === null || ingresos === 0 || costos === null
    ? null
    : (ingresos - costos) / ingresos;
  const margenNeto = ingresos === null || ingresos === 0 || utilidad === null
    ? null
    : utilidad / ingresos;
  const mesesDisponibles = meses.filter((mes) => mes.disponible).length;
  const ultimoMesDisponible = meses.reduce(
    (ultimo, mes, indice) => (mes.disponible ? indice : ultimo),
    -1,
  );
  const maxIngresos = Math.max(0, ...meses.map((mes) => mes.ingresos ?? 0));
  const maxCostos = Math.max(0, ...meses.map((mes) => mes.costos ?? 0));
  const fechaCorte = new Intl.DateTimeFormat("es-CO", {
    day: "numeric",
    month: "short",
    year: "numeric",
  }).format(new Date());

  function totalCuenta(cuenta: CuentaAnual): number | null {
    const valores = cuenta.valores.filter((valor): valor is number => valor !== null);
    return valores.length ? valores.reduce((total, valor) => total + valor, 0) : null;
  }

  return (
    <main className="ingresos-costos">
      <header className="ingresos-costos__encabezado">
        <div>
          <p className="ingresos-costos__eyebrow">
            GSC REPORTES · {MODO_EJEMPLOS ? "DATOS DE EJEMPLO" : "LIBRO MAYOR CONTABLE"}
          </p>
          <h2>Ingresos y costos</h2>
          {ultimoMesDisponible >= 0 ? (
            <p className="ingresos-costos__corte">
              {mesesDisponibles} períodos con datos · último movimiento {MESES[ultimoMesDisponible]} {anio}
            </p>
          ) : null}
        </div>
        <div className="ingresos-costos__controles">
          <label className="campo">
            <span>Año</span>
            <select
              className="campo__control"
              value={anio}
              onChange={(evento) => setAnio(Number(evento.target.value))}
            >
              {Array.from({ length: 6 }, (_, indice) => anioActual - indice).map((opcion) => (
                <option key={opcion} value={opcion}>{opcion}</option>
              ))}
            </select>
          </label>
          <span className="ingresos-costos__fecha">
            <span aria-hidden="true">▣</span> Corte a hoy · {fechaCorte}
          </span>
        </div>
      </header>

      <AvisoError error={error} />
      {cargando ? <Cargando texto="Consultando movimientos contables del año…" /> : null}
      {!cargando && mesesDisponibles === 0 ? (
        <Vacio
          titulo="Sin movimientos contables para este año"
          detalle="No se recibieron balances de comprobación para los períodos consultados. No se mostrarán cifras estimadas."
        />
      ) : null}

      {mesesDisponibles > 0 ? (
        <>
          <section className="ingresos-costos__indicadores" aria-label="Resumen acumulado del año">
            <article className="ingresos-costos__indicador">
              <span>Ingresos</span>
              <strong>{dineroMillones(ingresos)}</strong>
              <small>Acumulado de períodos disponibles</small>
            </article>
            <article className="ingresos-costos__indicador ingresos-costos__indicador--costo">
              <span>Costo</span>
              <strong>{dineroMillones(costos)}</strong>
              <small>
                {porcentaje(
                  ingresos !== null && ingresos !== 0 && costos !== null
                    ? costos / ingresos
                    : null,
                )} de los ingresos
              </small>
            </article>
            <article className="ingresos-costos__indicador">
              <span>% Margen bruto</span>
              <strong>{porcentaje(margenBruto)}</strong>
              <small>Margen: {dineroMillones(ingresos !== null && costos !== null ? ingresos - costos : null)}</small>
            </article>
            <article className="ingresos-costos__indicador">
              <span>Gastos</span>
              <strong>{dineroMillones(gastos)}</strong>
              <small>
                {porcentaje(
                  ingresos !== null && ingresos !== 0 && gastos !== null
                    ? gastos / ingresos
                    : null,
                )} de los ingresos
              </small>
            </article>
            <article className="ingresos-costos__indicador ingresos-costos__indicador--utilidad">
              <span>Utilidad</span>
              <strong>{dineroMillones(utilidad)}</strong>
              <small>Margen neto {porcentaje(margenNeto)}</small>
            </article>
          </section>

          <section className="ingresos-costos__graficos" aria-label="Resumen mensual">
            <article className="ingresos-costos__panel">
              <div className="ingresos-costos__panel-cabecera">
                <h3>Ingresos por mes</h3>
                <span>Millones de pesos</span>
              </div>
              <ol className="ingresos-costos__barras" aria-label="Ingresos por mes">
                {meses.map((mes, indice) => {
                  const valor = mes.ingresos;
                  const alto = valor === null || maxIngresos === 0
                    ? 0
                    : Math.max(2, (Math.max(0, valor) / maxIngresos) * 100);
                  return (
                    <li key={MESES[indice]} className="ingresos-costos__barra-columna">
                      <span className="ingresos-costos__barra-valor">
                        {valor === null ? "—" : dineroMillones(valor).replace(" M", "")}
                      </span>
                      <div className={`ingresos-costos__barra-pista${valor === null ? " ingresos-costos__barra-pista--vacia" : ""}`}>
                        <span className="ingresos-costos__barra" style={{ height: `${alto}%` }} />
                      </div>
                      <span className="ingresos-costos__barra-mes">{MESES[indice]}</span>
                    </li>
                  );
                })}
              </ol>
            </article>

            <article className="ingresos-costos__panel ingresos-costos__panel--costos">
              <div className="ingresos-costos__panel-cabecera">
                <h3>Costo por mes</h3>
                <span>Millones</span>
              </div>
              <ol className="ingresos-costos__costos">
                {meses.map((mes, indice) => {
                  const valor = mes.costos;
                  const ancho = valor === null || maxCostos === 0
                    ? 0
                    : Math.max(1, (Math.max(0, valor) / maxCostos) * 100);
                  return (
                    <li key={MESES[indice]}>
                      <span>{MESES[indice]}</span>
                      <div className={`ingresos-costos__costo-pista${valor === null ? " ingresos-costos__costo-pista--vacia" : ""}`}>
                        <span style={{ width: `${ancho}%` }} />
                      </div>
                      <strong>{valor === null ? "—" : dineroMillones(valor).replace("$", "").replace(" M", "")}</strong>
                    </li>
                  );
                })}
              </ol>
              <div className="ingresos-costos__costo-total">
                <span>Total</span>
                <strong>{dineroMillones(costos)}</strong>
              </div>
            </article>
          </section>

          <Tarjeta
            titulo="Detalle por cuenta PUC"
            descripcion="Movimientos mensuales de ingresos, costos y gastos. Los guiones indican períodos o cuentas sin datos reportados."
            sinRelleno
          >
            <div className="tabla-envoltorio tabla-envoltorio--alta">
              <table className="tabla tabla--anclada ingresos-costos__tabla" aria-busy={cargando}>
                <caption className="solo-lectores">
                  Detalle mensual por cuenta PUC, con importes en millones de pesos.
                </caption>
                <thead>
                  <tr>
                    <th scope="col" className="columna-ancla" rowSpan={2}>Cuenta</th>
                    <th scope="col" rowSpan={2}>Concepto</th>
                    <th scope="col" className="numero" colSpan={12}>Millones de pesos</th>
                    <th scope="col" className="numero" rowSpan={2}>Total</th>
                  </tr>
                  <tr>
                    {MESES.map((mes) => <th key={mes} scope="col" className="numero">{mes}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {CLASES_PYG.map((clase) => {
                    const filas = [...cuentas.values()]
                      .filter((cuenta) => cuenta.clase === clase)
                      .sort((a, b) => a.codigo.localeCompare(b.codigo));
                    const movimientoClase = meses.map((mes) => mes[clase.toLocaleLowerCase() as "ingresos" | "costos" | "gastos"]);
                    const totalClase = totalDe(meses, clase);
                    if (!filas.length && totalClase === null) return null;
                    return (
                      <Fragment key={clase}>
                        <tr className="ingresos-costos__grupo">
                          <th scope="rowgroup" className="columna-ancla" colSpan={2}>{clase}</th>
                          {movimientoClase.map((valor, indice) => (
                            <td key={MESES[indice]} className="numero">{dineroMillones(valor)}</td>
                          ))}
                          <td className="numero">{dineroMillones(totalClase)}</td>
                        </tr>
                        {filas.map((cuenta) => (
                          <tr key={`${cuenta.clase}-${cuenta.codigo}`}>
                            <th scope="row" className="columna-ancla">{cuenta.codigo}</th>
                            <td>{cuenta.descripcion}</td>
                            {cuenta.valores.map((valor, indice) => (
                              <td key={MESES[indice]} className="numero">
                                {valor === null ? "—" : dineroMillones(valor).replace("$", "").replace(" M", "")}
                              </td>
                            ))}
                            <td className="numero">{dineroMillones(totalCuenta(cuenta))}</td>
                          </tr>
                        ))}
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </Tarjeta>
        </>
      ) : null}
    </main>
  );
}