/**
 * Detalle de cuentas — Grupo Santacruz.
 *
 * Un renglón por cuenta (6 dígitos) × centro de costo × tercero, para el
 * balance y el PyG «por tercero» y «por centro de costo» que pide contabilidad.
 * Es el mismo dato que agrega `Resumen financiero` en cuatro cifras; aquí se ve
 * sin agregar, con el filtro de texto como único paso entre las 200-300 filas
 * de un mes normal y lo que alguien busca.
 */

import { useMemo, useState } from "react";

import { useDetalleCuentas } from "@/api/consultasFinanciero";
import { AvisoError, Cargando, Tarjeta, Vacio } from "@/componentes/comunes";
import { dinero } from "@/utilidades/formato";

function aPeriodoApi(mes: string): string {
  return mes.replace("-", "");
}

function periodoActual(): string {
  const hoy = new Date();
  return `${hoy.getFullYear()}-${String(hoy.getMonth() + 1).padStart(2, "0")}`;
}

export function DetalleCuentas() {
  const [mes, setMes] = useState(periodoActual());
  const [busqueda, setBusqueda] = useState("");
  const consulta = useDetalleCuentas({ periodo: aPeriodoApi(mes) });

  const filas = consulta.data?.filas ?? [];

  const filasFiltradas = useMemo(() => {
    const texto = busqueda.trim().toLowerCase();
    if (!texto) return filas;
    return filas.filter((fila) =>
      [
        fila.mayor_iv,
        fila.descripcion,
        fila.centro_costo,
        fila.id_tercero,
        fila.razon_social,
      ]
        .filter(Boolean)
        .some((campo) => campo!.toLowerCase().includes(texto)),
    );
  }, [filas, busqueda]);

  const totalFinal = filasFiltradas.reduce((total, fila) => total + Number(fila.final), 0);

  return (
    <div className="pila">
      <Tarjeta
        titulo="Detalle de cuentas"
        descripcion="Balance y PyG por cuenta, centro de costo y tercero, sin agregar. Base para el análisis por tercero y por centro de costo."
        sinRelleno
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
            <label className="campo">
              <span>Buscar</span>
              <input
                className="campo__control"
                type="search"
                placeholder="Cuenta, centro de costo o tercero…"
                value={busqueda}
                onChange={(evento) => setBusqueda(evento.target.value)}
              />
            </label>
          </form>
        }
      >
        <AvisoError error={consulta.error} />
        {consulta.isLoading ? <Cargando texto="Cargando el detalle de cuentas…" /> : null}

        {!consulta.isLoading && filas.length === 0 ? (
          <Vacio
            titulo="Sin movimientos en este período"
            detalle="El libro mayor no trae filas para el mes elegido."
          />
        ) : null}

        {!consulta.isLoading && filas.length > 0 ? (
          <div className="tabla-envoltorio tabla-envoltorio--alta">
            <table className="tabla tabla--anclada">
              <caption className="solo-lectores">
                Detalle de cuentas del libro mayor por centro de costo y tercero.
              </caption>
              <thead>
                <tr>
                  <th scope="col" className="columna-ancla">Cuenta</th>
                  <th scope="col">Clase</th>
                  <th scope="col">Centro de costo</th>
                  <th scope="col">Tercero</th>
                  <th scope="col" className="numero">Saldo inicial</th>
                  <th scope="col" className="numero">Débitos</th>
                  <th scope="col" className="numero">Créditos</th>
                  <th scope="col" className="numero">Final</th>
                </tr>
              </thead>
              <tbody>
                {filasFiltradas.map((fila, indice) => (
                  <tr key={`${fila.mayor_iv}-${fila.centro_costo ?? ""}-${fila.id_tercero ?? ""}-${indice}`}>
                    <th scope="row" className="columna-ancla">
                      <span title={fila.descripcion ?? undefined}>
                        {fila.mayor_iv ?? fila.mayor_iii}
                      </span>
                    </th>
                    <td>{fila.clase}</td>
                    <td>{fila.centro_costo ?? "—"}</td>
                    <td>{fila.razon_social ?? fila.id_tercero ?? "—"}</td>
                    <td className="numero">{dinero(fila.saldo_inicial)}</td>
                    <td className="numero">{dinero(fila.debitos)}</td>
                    <td className="numero">{dinero(fila.creditos)}</td>
                    <td className="numero">{dinero(fila.final)}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr>
                  <td colSpan={7} className="columna-ancla">
                    {filasFiltradas.length} de {filas.length} filas
                  </td>
                  <td className="numero">{dinero(String(totalFinal))}</td>
                </tr>
              </tfoot>
            </table>
          </div>
        ) : null}
      </Tarjeta>
    </div>
  );
}
