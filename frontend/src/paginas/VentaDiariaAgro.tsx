/**
 * Venta día a día por centro de operación.
 *
 * La unidad de esta pantalla es el centro —301 Planta y 302 Montería— y no una
 * zona: son los dos únicos que tienen calendario propio, y por eso son también
 * los únicos contra los que se puede derivar una línea de referencia diaria.
 *
 * Dos cosas que vienen del backend y **no** se recalculan aquí:
 *
 * - La fila de totales llega en `totales`, en un campo propio y no mezclada
 *   entre las filas. Sumarla en el navegador sería sumar cadenas convertidas a
 *   `number`, que es exactamente como se corrompe un importe de miles de
 *   millones de pesos.
 * - El presupuesto diario sale de la dimensión `centro_operacion`, la única que
 *   reparte la meta por algo que tiene días hábiles. Llega `null` mientras nadie
 *   lo capture, y `null` se pinta «—»: no hay meta todavía, que no es lo mismo
 *   que una meta de cero.
 */

import { useMemo } from "react";

import { useExportarAgro, useVentaDiariaAgro } from "@/api/consultasAgro";
import { AvisoError, Cargando, Tarjeta, Vacio } from "@/componentes/comunes";
import { useAuth } from "@/auth/ContextoAuth";
import {
  BarraFiltrosAgro,
  filtrosAgroDe,
  useFiltros,
} from "@/componentes/filtros";
import {
  AvisoCuadre,
  NotaConciliacion,
  PieCalculoAgro,
} from "@/componentes/indicadoresAgro";
import {
  diaDelMes,
  esDomingo,
  mesCorto,
  porMedida,
} from "@/utilidades/formato";

export function VentaDiariaAgro() {
  const { tienePermiso, usuario } = useAuth();
  const granular = usuario?.rol === "CONSULTA" && usuario.permisos.some((codigo) => codigo.startsWith("PERMISO_AGRO_"));
  const control = useFiltros();
  const { filtros } = control;

  const filtrosAgro = useMemo(() => filtrosAgroDe(filtros), [filtros]);
  const { data, isLoading, error } = useVentaDiariaAgro(filtrosAgro);
  const exportar = useExportarAgro();

  const medida = data?.medida ?? filtros.medida;
  const filas = data?.filas ?? [];
  const fechas = data?.fechas ?? [];

  return (
    <div className="pila">
      <BarraFiltrosAgro
        control={control}
        mostrar={{ rango: true }}
        acciones={
          !granular || tienePermiso("PERMISO_AGRO_DESCARGAR_VENTA_DIARIA") ? (
            <button
              type="button"
              className="boton boton--pequeno"
              onClick={() =>
                exportar.mutate({ reporte: "venta-diaria", filtros: filtrosAgro })
              }
              disabled={exportar.isPending || !data}
            >
              {exportar.isPending ? "Generando…" : "Exportar a Excel"}
            </button>
          ) : null
        }
      />

      <AvisoError error={error} />
      <AvisoError error={exportar.error} />

      {isLoading ? <Cargando texto="Armando la serie diaria…" /> : null}

      {data ? (
        <>
          <AvisoCuadre cuadre={data.parametros_calculo.cuadre} />

          <Tarjeta
            titulo="Venta diaria por centro de operación"
            descripcion={`Del ${data.desde} al ${data.hasta}, ambos días incluidos.`}
            sinRelleno
            pie={
              <PieCalculoAgro
                parametros={data.parametros_calculo}
                medida={medida}
                extra={
                  <NotaConciliacion
                    conciliacion={data.parametros_calculo.conciliacion}
                  />
                }
              />
            }
          >
            {filas.length === 0 || fechas.length === 0 ? (
              <Vacio
                titulo="Sin venta en el rango"
                detalle="Ningún centro registró venta entre las fechas seleccionadas."
              />
            ) : (
              <div className="tabla-envoltorio tabla-envoltorio--alta">
                <table className="tabla tabla--anclada tabla--compacta">
                  <caption className="solo-lectores">
                    Venta por día y centro de operación, del {data.desde} al{" "}
                    {data.hasta}.
                  </caption>
                  <thead>
                    <tr>
                      <th scope="col" className="columna-ancla">
                        Centro
                      </th>
                      <th
                        scope="col"
                        title="Presupuesto mensual del centro dividido por sus días hábiles."
                      >
                        Ppto. diario
                      </th>
                      {fechas.map((fecha) => (
                        <th
                          key={fecha}
                          scope="col"
                          className={
                            esDomingo(fecha) ? "columna-domingo" : undefined
                          }
                          title={fecha}
                        >
                          {diaDelMes(fecha)}
                          <span className="tenue"> {mesCorto(fecha)}</span>
                        </th>
                      ))}
                      <th scope="col">Total</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filas.map((fila) => (
                      <tr key={fila.centro}>
                        <th scope="row" className="columna-ancla">
                          {fila.nombre}
                          <span className="tenue mono"> · {fila.centro}</span>
                        </th>
                        <td className="numero tenue">
                          {porMedida(
                            data.presupuesto_diario_por_centro[fila.centro] ??
                              null,
                            medida,
                          )}
                        </td>
                        {fila.valores.map((valor, indice) => (
                          <td
                            key={fechas[indice] ?? indice}
                            className={
                              esDomingo(fechas[indice] ?? "")
                                ? "numero columna-domingo"
                                : "numero"
                            }
                          >
                            {porMedida(valor, medida)}
                          </td>
                        ))}
                        <td className="numero">
                          {porMedida(fila.total, medida)}
                        </td>
                      </tr>
                    ))}

                    {/* La fila que pidió el usuario: la suma de todos los
                        centros por día. Llega calculada del backend y se pinta
                        tal cual, para que el archivo exportado, la pantalla y la
                        API no puedan decir tres cosas distintas. */}
                    <tr className="fila-total">
                      <th scope="row" className="columna-ancla">
                        TOTAL · {filas.length} centro
                        {filas.length === 1 ? "" : "s"}
                      </th>
                      <td className="numero tenue">
                        {porMedida(data.totales.presupuesto_diario, medida)}
                      </td>
                      {data.totales.valores.map((valor, indice) => (
                        <td
                          key={fechas[indice] ?? indice}
                          className={
                            esDomingo(fechas[indice] ?? "")
                              ? "numero columna-domingo"
                              : "numero"
                          }
                        >
                          {porMedida(valor, medida)}
                        </td>
                      ))}
                      <td className="numero">
                        {porMedida(data.totales.total, medida)}
                      </td>
                    </tr>
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
