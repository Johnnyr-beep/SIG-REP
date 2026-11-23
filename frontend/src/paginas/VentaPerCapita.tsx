/** Venta acumulada por empleado, comparada entre puntos de venta. */

import { useCumplimiento } from "@/api/consultas";
import { AvisoError, Cargando, Tarjeta, Vacio } from "@/componentes/comunes";
import { BarraFiltros, useFiltros } from "@/componentes/filtros";
import { dinero, numero } from "@/utilidades/formato";

export function VentaPerCapita() {
  const control = useFiltros();
  const filtros = { ...control.filtros, medida: "valor" as const };
  const { data, isLoading, error } = useCumplimiento(filtros);

  const filas = (data?.filas ?? [])
    .map((fila) => ({
      ...fila,
      ventaPorEmpleado:
        fila.numero_empleados != null && fila.numero_empleados > 0
          ? Number(fila.venta) / fila.numero_empleados
          : null,
    }))
    .sort((primera, segunda) => {
      if (primera.ventaPorEmpleado === null && segunda.ventaPorEmpleado === null)
        return 0;
      if (primera.ventaPorEmpleado === null) return 1;
      if (segunda.ventaPorEmpleado === null) return -1;
      return segunda.ventaPorEmpleado - primera.ventaPorEmpleado;
    });
  const empleadosConfigurados = filas.filter(
    (fila) => fila.numero_empleados != null && fila.numero_empleados > 0,
  ).length;
  const coberturaCompleta = filas.length > 0 && empleadosConfigurados === filas.length;
  const ventaTotal = filas.reduce((total, fila) => total + Number(fila.venta), 0);
  const empleadosTotal = coberturaCompleta
    ? filas.reduce((total, fila) => total + (fila.numero_empleados ?? 0), 0)
    : null;
  const ventaPerCapitaTotal =
    empleadosTotal != null && empleadosTotal > 0
      ? ventaTotal / empleadosTotal
      : null;

  return (
    <div className="pila">
      <BarraFiltros control={control} mostrar={{ medida: false, categoria: false }} />
      <AvisoError error={error} />
      {isLoading ? <Cargando texto="Calculando venta por empleado..." /> : null}

      {data ? (
        <Tarjeta
          titulo="Venta por empleado por punto de venta"
          descripcion={`Venta acumulada al ${data.fecha_corte}, dividida entre los empleados configurados.`}
          sinRelleno
        >
          {filas.length === 0 ? (
            <Vacio
              titulo="Sin puntos de venta"
              detalle="No hay puntos que coincidan con los filtros seleccionados."
            />
          ) : (
            <div className="tabla-envoltorio">
              <table className="tabla">
                <caption className="solo-lectores">
                  Venta acumulada por empleado, ordenada de mayor a menor por punto de venta.
                </caption>
                <thead>
                  <tr>
                    <th scope="col">Punto de venta</th>
                    <th scope="col" className="numero">Venta acumulada</th>
                    <th scope="col" className="numero">Empleados</th>
                    <th scope="col" className="numero">Venta por empleado</th>
                  </tr>
                </thead>
                <tbody>
                  {filas.map((fila) => (
                    <tr key={fila.punto_venta}>
                      <th scope="row">
                        {fila.nombre}
                        <span className="tenue mono"> ({fila.punto_venta})</span>
                      </th>
                      <td className="numero">{dinero(fila.venta)}</td>
                      <td className="numero">{numero(fila.numero_empleados)}</td>
                      <td className="numero">
                        {fila.ventaPorEmpleado === null
                          ? "N/D"
                          : dinero(String(fila.ventaPorEmpleado))}
                      </td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr className="fila-totales">
                    <th scope="row">Total</th>
                    <td className="numero">{dinero(String(ventaTotal))}</td>
                    <td className="numero">
                      {empleadosTotal == null ? (
                        <span title="Completa la cantidad de empleados de cada punto para calcular el total por empleado.">
                          {numero(empleadosConfigurados)} de {numero(filas.length)} configurados
                        </span>
                      ) : numero(empleadosTotal)}
                    </td>
                    <td className="numero">
                      {ventaPerCapitaTotal == null
                        ? "N/D"
                        : dinero(String(ventaPerCapitaTotal))}
                    </td>
                  </tr>
                </tfoot>
              </table>
            </div>
          )}
          <p className="tenue">
            La venta por empleado requiere una cantidad de empleados configurada mayor que cero.
          </p>
        </Tarjeta>
      ) : null}
    </div>
  );
}
