import { Fragment, useMemo, useState } from "react";

import { MODO_EJEMPLOS } from "@/api/cliente";
import { useSerieDetalleCuentasVivo } from "@/api/consultasFinanciero";
import type { FilaDetalleCuentaEnVivo } from "@/api/tipos";
import { AvisoError, Cargando, Tarjeta, Vacio } from "@/componentes/comunes";

const MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];
const CLASES_PYG = ["Ingresos", "Costos", "Gastos"] as const;
const EMPRESAS = [
  { cia: 3, nombre: "Agropecuaria Santacruz" },
  { cia: 4, nombre: "Carnes Santacruz" },
  { cia: 6, nombre: "Cristian Serrano" },
  { cia: 7, nombre: "Serueda" },
  { cia: 8, nombre: "Inversiones Serrano Millán" },
] as const;

type ClasePyG = (typeof CLASES_PYG)[number];

interface MovimientoMes {
  disponible: boolean;
  ingresos: number | null;
  costos: number | null;
  gastos: number | null;
}

interface LineaIngresoAnual {
  codigos: string[];
  descripcion: string;
  ingresos: Array<number | null>;
  costos: Array<number | null>;
}

function montoMovimiento(fila: FilaDetalleCuentaEnVivo): number | null {
  if (fila.clase === "Ingresos" || fila.clase.startsWith("Costo") || fila.clase === "Gastos") {
    return Number(fila.monto);
  }
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

function numeroMillones(valor: number | null): string {
  if (valor === null || !Number.isFinite(valor)) return "—";
  return new Intl.NumberFormat("es-CO", { maximumFractionDigits: 3 }).format(valor / 1_000_000);
}

function claveConcepto(fila: FilaDetalleCuentaEnVivo): string {
  const concepto = fila.cuenta.trim() || `cuenta ${fila.auxiliar.slice(0, 4)}`;
  return concepto
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLocaleLowerCase("es-CO")
    .replace(/\s+/g, " ")
    .trim();
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
  const [cia, setCia] = useState<number>(EMPRESAS[0].cia);
  const periodoMaximo = anio === anioActual ? new Date().getMonth() + 1 : 12;
  const periodos = useMemo(
    () => Array.from({ length: periodoMaximo }, (_, indice) => periodoDe(anio, indice + 1)),
    [anio, periodoMaximo],
  );
  const consultas = useSerieDetalleCuentasVivo(cia, periodos);
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
      const sumar = (cuentas: FilaDetalleCuentaEnVivo[]) =>
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

  const lineasIngreso = useMemo(() => {
    const filasPorMes = consultas.map((consulta) => consulta.data?.filas ?? []);
    const porConcepto = new Map<string, LineaIngresoAnual>();

    filasPorMes.forEach((filas, indiceMes) => {
      for (const fila of filas) {
        if (fila.clase !== "Ingresos") continue;
        const clave = claveConcepto(fila);
        let linea = porConcepto.get(clave);
        if (!linea) {
          linea = {
            codigos: [],
            descripcion: fila.cuenta.trim() || `Cuenta PUC ${fila.auxiliar.slice(0, 4)}`,
            ingresos: Array.from({ length: 12 }, () => null),
            costos: Array.from({ length: 12 }, () => null),
          };
          porConcepto.set(clave, linea);
        }
        const codigo = fila.auxiliar.slice(0, 4);
        if (!linea.codigos.includes(codigo)) linea.codigos.push(codigo);
        const movimiento = montoMovimiento(fila);
        if (movimiento !== null) {
          linea.ingresos[indiceMes] = (linea.ingresos[indiceMes] ?? 0) + movimiento;
        }
      }
    });

    filasPorMes.forEach((filas, indiceMes) => {
      for (const fila of filas) {
        if (!fila.clase.startsWith("Costo")) continue;
        const linea = porConcepto.get(claveConcepto(fila));
        if (!linea) continue;
        const movimiento = montoMovimiento(fila);
        if (movimiento !== null) {
          linea.costos[indiceMes] = (linea.costos[indiceMes] ?? 0) + movimiento;
        }
      }
    });

    return [...porConcepto.values()].sort((a, b) => a.descripcion.localeCompare(b.descripcion, "es-CO"));
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

  function totalValores(valores: Array<number | null>): number | null {
    const disponibles = valores.filter((valor): valor is number => valor !== null);
    return disponibles.length ? disponibles.reduce((total, valor) => total + valor, 0) : null;
  }

  return (
    <main className="ingresos-costos">
      <header className="ingresos-costos__encabezado">
        <div>
          <p className="ingresos-costos__eyebrow">
            GSC REPORTES · {MODO_EJEMPLOS ? "DATOS DE EJEMPLO" : "SIESA · DATOS EN VIVO"}
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
          <label className="campo">
            <span>Empresa</span>
            <select
              className="campo__control"
              value={cia}
              onChange={(evento) => setCia(Number(evento.target.value))}
            >
              {EMPRESAS.map((empresa) => (
                <option key={empresa.cia} value={empresa.cia}>{empresa.nombre}</option>
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
            titulo="Ingresos detalle"
            descripcion="Ingreso: valor y participación sobre el total del mes. Rentab.: margen bruto y porcentaje sobre el ingreso de la línea; se calcula cuando coincide la descripción PUC del costo."
            sinRelleno
          >
            <div className="tabla-envoltorio tabla-envoltorio--alta">
              <table className="tabla tabla--anclada ingresos-costos__tabla" aria-busy={cargando}>
                <caption className="solo-lectores">
                  Detalle mensual por línea PUC, con ingreso, participación vertical, margen bruto y porcentaje de rentabilidad.
                </caption>
                <thead>
                  <tr>
                    <th scope="col" className="columna-ancla" rowSpan={2}>Cuenta</th>
                    <th scope="col" rowSpan={2}>Concepto</th>
                    {MESES.map((mes) => (
                      <th key={mes} scope="colgroup" className="numero" colSpan={2}>{mes}</th>
                    ))}
                    <th scope="colgroup" className="numero" colSpan={2}>Total</th>
                  </tr>
                  <tr>
                    {Array.from({ length: 13 }, (_, indice) => (
                      <Fragment key={indice}>
                        <th scope="col" className="numero">Ingreso</th>
                        <th scope="col" className="numero">Rentab.</th>
                      </Fragment>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  <tr className="ingresos-costos__grupo">
                    <th scope="rowgroup" className="columna-ancla" colSpan={2}>Ingresos</th>
                    {meses.map((mes, indice) => {
                      const margen = mes.ingresos !== null && mes.costos !== null
                        ? mes.ingresos - mes.costos
                        : null;
                      return (
                        <Fragment key={MESES[indice]}>
                          <td className="numero ingresos-costos__ingreso">
                            <span>{numeroMillones(mes.ingresos)}</span>
                            <small>{porcentaje(mes.ingresos !== null && mes.ingresos !== 0 ? 1 : null)}</small>
                          </td>
                          <td className="numero ingresos-costos__rentabilidad">
                            <span>{numeroMillones(margen)}</span>
                            <small>{porcentaje(margen !== null && mes.ingresos ? margen / mes.ingresos : null)}</small>
                          </td>
                        </Fragment>
                      );
                    })}
                    <td className="numero ingresos-costos__ingreso">
                      <span>{numeroMillones(ingresos)}</span>
                      <small>{porcentaje(ingresos !== null && ingresos !== 0 ? 1 : null)}</small>
                    </td>
                    <td className="numero ingresos-costos__rentabilidad">
                      <span>{numeroMillones(ingresos !== null && costos !== null ? ingresos - costos : null)}</span>
                      <small>{porcentaje(margenBruto)}</small>
                    </td>
                  </tr>
                  {lineasIngreso.map((linea) => {
                    const totalIngreso = totalValores(linea.ingresos);
                    const totalCosto = totalValores(linea.costos);
                    const totalMargen = totalIngreso !== null && totalCosto !== null
                      ? totalIngreso - totalCosto
                      : null;
                    return (
                      <tr key={linea.descripcion}>
                        <th scope="row" className="columna-ancla">{linea.codigos.join(" / ")}</th>
                        <td>{linea.descripcion}</td>
                        {linea.ingresos.map((valor, indice) => {
                          const costo = linea.costos[indice] ?? null;
                          const margen = valor !== null && costo !== null ? valor - costo : null;
                          const totalMes = meses[indice]?.ingresos ?? null;
                          return (
                            <Fragment key={MESES[indice]}>
                              <td className="numero ingresos-costos__ingreso">
                                <span>{numeroMillones(valor)}</span>
                                <small>{porcentaje(valor !== null && totalMes ? valor / totalMes : null)}</small>
                              </td>
                              <td className="numero ingresos-costos__rentabilidad">
                                <span>{numeroMillones(margen)}</span>
                                <small>{porcentaje(margen !== null && valor ? margen / valor : null)}</small>
                              </td>
                            </Fragment>
                          );
                        })}
                        <td className="numero ingresos-costos__ingreso">
                          <span>{numeroMillones(totalIngreso)}</span>
                          <small>{porcentaje(totalIngreso !== null && ingresos ? totalIngreso / ingresos : null)}</small>
                        </td>
                        <td className="numero ingresos-costos__rentabilidad">
                          <span>{numeroMillones(totalMargen)}</span>
                          <small>{porcentaje(totalMargen !== null && totalIngreso ? totalMargen / totalIngreso : null)}</small>
                        </td>
                      </tr>
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