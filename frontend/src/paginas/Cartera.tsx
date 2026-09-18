/**
 * Cartera por cliente — Grupo Santacruz.
 *
 * Saldo por tercero de las cuentas del grupo PUC 13 (deudores), a corte de un
 * período. El libro mayor no trae fecha de vencimiento ni factura individual
 * —solo el saldo acumulado del mes—, así que esto es saldo total por cliente,
 * no cartera vencida por edades (30/60/90 días).
 */

import { useMemo, useState } from "react";

import { useCartera } from "@/api/consultasFinanciero";
import { AvisoError, Cargando, Tarjeta, Vacio } from "@/componentes/comunes";
import { dinero } from "@/utilidades/formato";

function aPeriodoApi(mes: string): string {
  return mes.replace("-", "");
}

function periodoActual(): string {
  const hoy = new Date();
  return `${hoy.getFullYear()}-${String(hoy.getMonth() + 1).padStart(2, "0")}`;
}

export function Cartera() {
  const [mes, setMes] = useState(periodoActual());
  const [busqueda, setBusqueda] = useState("");
  const consulta = useCartera({ periodo: aPeriodoApi(mes) });

  const filas = consulta.data?.filas ?? [];

  const filasFiltradas = useMemo(() => {
    const texto = busqueda.trim().toLowerCase();
    if (!texto) return filas;
    return filas.filter((fila) =>
      [fila.id_tercero, fila.razon_social]
        .filter(Boolean)
        .some((campo) => campo!.toLowerCase().includes(texto)),
    );
  }, [filas, busqueda]);

  const totalSaldo = filasFiltradas.reduce((total, fila) => total + Number(fila.saldo), 0);

  return (
    <div className="pila">
      <Tarjeta
        titulo="Cartera por cliente"
        descripcion="Saldo por tercero de las cuentas de deudores (grupo 13), a corte del período elegido."
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
                placeholder="Cliente o NIT…"
                value={busqueda}
                onChange={(evento) => setBusqueda(evento.target.value)}
              />
            </label>
          </form>
        }
      >
        <AvisoError error={consulta.error} />
        {consulta.isLoading ? <Cargando texto="Cargando la cartera…" /> : null}

        {!consulta.isLoading && filas.length === 0 ? (
          <Vacio
            titulo="Sin saldo de cartera en este período"
            detalle="El libro mayor no trae movimientos del grupo 13 (deudores) para el mes elegido."
          />
        ) : null}

        {!consulta.isLoading && filas.length > 0 ? (
          <div className="tabla-envoltorio tabla-envoltorio--alta">
            <table className="tabla tabla--anclada">
              <caption className="solo-lectores">
                Saldo de cartera por cliente, cuentas de deudores del libro mayor.
              </caption>
              <thead>
                <tr>
                  <th scope="col" className="columna-ancla">Cliente</th>
                  <th scope="col">NIT / identificación</th>
                  <th scope="col" className="numero">Saldo</th>
                </tr>
              </thead>
              <tbody>
                {filasFiltradas.map((fila) => (
                  <tr key={fila.id_tercero}>
                    <th scope="row" className="columna-ancla">
                      {fila.razon_social ?? "—"}
                    </th>
                    <td>{fila.id_tercero}</td>
                    <td className="numero">{dinero(fila.saldo)}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr>
                  <td colSpan={2} className="columna-ancla">
                    {filasFiltradas.length} de {filas.length} clientes
                  </td>
                  <td className="numero">{dinero(String(totalSaldo))}</td>
                </tr>
              </tfoot>
            </table>
          </div>
        ) : null}
      </Tarjeta>
    </div>
  );
}
