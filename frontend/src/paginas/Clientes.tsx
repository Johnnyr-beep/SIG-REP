/**
 * Clientes y vendedores.
 *
 * Es el reporte que el Excel no tiene: el catálogo de clientes trae canal y
 * vendedor asignado, así que la misma venta se puede leer por cliente, por
 * vendedor, por canal o por condición de pago sin rehacer una tabla dinámica.
 */

import { useSearchParams } from "react-router-dom";

import { useClientes, useExportar } from "@/api/consultas";
import { AvisoError, Cargando, Tarjeta, Vacio } from "@/componentes/comunes";
import { BarraFiltros, useFiltros } from "@/componentes/filtros";
import { BarraParticipacion } from "@/componentes/graficos";
import { PieCalculo } from "@/componentes/indicadores";
import { CORTES_CLIENTES, esCorteClientes } from "@/utilidades/dominio";
import { dinero, kilos, porcentaje } from "@/utilidades/formato";

export function Clientes() {
  const control = useFiltros();
  const { filtros } = control;
  const [parametros, setParametros] = useSearchParams();

  const porParametro = parametros.get("por");
  const por = esCorteClientes(porParametro) ? porParametro : "cliente";

  const { data, isLoading, error } = useClientes(filtros, por);
  const exportar = useExportar();

  function cambiarCorte(valor: string) {
    setParametros(
      (anteriores) => {
        const siguientes = new URLSearchParams(anteriores);
        siguientes.set("por", valor);
        return siguientes;
      },
      { replace: true },
    );
  }

  return (
    <div className="pila">
      <BarraFiltros
        control={control}
        mostrar={{ categoria: true }}
        acciones={
          <button
            type="button"
            className="boton boton--pequeno"
            onClick={() =>
              exportar.mutate({ reporte: "clientes", filtros, extra: { por } })
            }
            disabled={exportar.isPending}
          >
            {exportar.isPending ? "Generando…" : "Exportar a Excel"}
          </button>
        }
      />

      <section className="filtros" aria-label="Corte del reporte">
        <div className="filtros__campo">
          <span>Agrupar por</span>
          <fieldset className="segmentado">
            <legend className="solo-lectores">Criterio de agrupación</legend>
            {CORTES_CLIENTES.map((opcion) => (
              <label
                key={opcion.valor}
                className={`segmentado__opcion${por === opcion.valor ? " segmentado__opcion--activa" : ""}`}
              >
                <input
                  type="radio"
                  name="por"
                  value={opcion.valor}
                  checked={por === opcion.valor}
                  onChange={() => cambiarCorte(opcion.valor)}
                />
                {opcion.etiqueta}
              </label>
            ))}
          </fieldset>
        </div>
      </section>

      <AvisoError error={error} />
      <AvisoError error={exportar.error} />

      {isLoading ? <Cargando texto="Agrupando la venta…" /> : null}

      {data ? (
        <Tarjeta
          titulo={`Venta por ${CORTES_CLIENTES.find((opcion) => opcion.valor === por)?.etiqueta.toLowerCase() ?? "cliente"}`}
          descripcion="Ordenado por participación en la venta del período."
          sinRelleno
          pie={
            <PieCalculo
              parametros={data.parametros_calculo}
              medida={data.medida ?? filtros.medida}
              extra={
                <p className="tenue">
                  Las filas cuya clase de cliente no pertenece al catálogo se
                  agrupan como «SIN CLASIFICAR»; el detalle de por qué está en
                  la pantalla de ingesta.
                </p>
              }
            />
          }
        >
          {data.filas.length === 0 ? (
            <Vacio
              titulo="Sin venta en el período"
              detalle="Ningún registro coincide con los filtros seleccionados."
            />
          ) : (
            <div className="tabla-envoltorio">
              <table className="tabla">
                <thead>
                  <tr>
                    <th scope="col">Nombre</th>
                    <th scope="col">Clave</th>
                    <th scope="col" className="numero">
                      Venta
                    </th>
                    <th scope="col" className="numero">
                      Kilos
                    </th>
                    <th scope="col" className="numero">
                      Margen %
                    </th>
                    <th scope="col" className="columna-participacion">
                      Participación
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {data.filas.map((fila) => (
                    <tr key={`${fila.clave}-${fila.nombre}`}>
                      <th scope="row">{fila.nombre}</th>
                      <td className="mono tenue">{fila.clave}</td>
                      <td className="numero">{dinero(fila.venta)}</td>
                      <td className="numero">{kilos(fila.kilos)}</td>
                      <td className="numero">
                        {porcentaje(fila.margen_porcentaje)}
                      </td>
                      <td className="columna-participacion">
                        <div className="participacion">
                          <span className="participacion__cifra">
                            {porcentaje(fila.participacion)}
                          </span>
                          <BarraParticipacion valor={fila.participacion} />
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Tarjeta>
      ) : null}
    </div>
  );
}
