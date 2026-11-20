/**
 * Clientes y vendedores.
 *
 * Es el reporte que el Excel no tiene: el catálogo de clientes trae canal y
 * vendedor asignado, así que la misma venta se puede leer por cliente, por
 * vendedor, por canal o por condición de pago sin rehacer una tabla dinámica.
 */

import { useSearchParams } from "react-router-dom";

import { useClientes, useExportar, useVentasFacturadasPorCanal } from "@/api/consultas";
import { useAuth } from "@/auth/ContextoAuth";
import { AvisoError, Cargando, Tarjeta, Vacio } from "@/componentes/comunes";
import { BarraFiltros, useFiltros } from "@/componentes/filtros";
import { BarraParticipacion } from "@/componentes/graficos";
import { PieCalculo } from "@/componentes/indicadores";
import { CORTES_CLIENTES, esCorteClientes } from "@/utilidades/dominio";
import { dinero, kilos, periodoLargo, porcentaje } from "@/utilidades/formato";

export function Clientes() {
  const control = useFiltros();
  const { filtros } = control;
  const [parametros, setParametros] = useSearchParams();

  const porParametro = parametros.get("por");
  const por = esCorteClientes(porParametro) ? porParametro : "cliente";

  const esCanalFacturado = por === "canal";
  const { data, isLoading, error } = useClientes(filtros, por, !esCanalFacturado);
  const canalesFacturados = useVentasFacturadasPorCanal(
    filtros.periodo,
    esCanalFacturado,
  );
  const exportar = useExportar();
  const { tienePermiso } = useAuth();

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
        mostrar={esCanalFacturado
          ? { corte: false, grupo: false, puntoVenta: false, categoria: false, medida: false }
          : { categoria: true }}
        acciones={!esCanalFacturado && tienePermiso("PERMISO_DESCARGAR_CLIENTES") ? (
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
        ) : undefined}
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

      <AvisoError error={esCanalFacturado ? canalesFacturados.error : error} />
      {!esCanalFacturado ? <AvisoError error={exportar.error} /> : null}

      {(esCanalFacturado ? canalesFacturados.isLoading : isLoading) ? (
        <Cargando texto={esCanalFacturado ? "Consultando facturación por canal…" : "Agrupando la venta…"} />
      ) : null}

      {esCanalFacturado && canalesFacturados.data ? (
        <Tarjeta
          titulo="Venta facturada por canal"
          descripcion={canalesFacturados.data.periodo !== canalesFacturados.data.periodo_solicitado
            ? `Sin datos para ${periodoLargo(canalesFacturados.data.periodo_solicitado)}. Se muestra el último mes disponible: ${periodoLargo(canalesFacturados.data.periodo)} · Fuente: facturación SIESA.`
            : `Mes completo ${periodoLargo(canalesFacturados.data.periodo)} · Fuente: facturación SIESA. No aplica corte diario, punto de venta ni categoría.`}
          sinRelleno
        >
          {canalesFacturados.data.filas.length === 0 ? (
            <Vacio
              titulo="Sin ventas facturadas por canal en este mes"
              detalle="La fuente SIESA no reporta filas para el período seleccionado."
            />
          ) : (
            <div className="tabla-envoltorio">
              <table className="tabla">
                <thead>
                  <tr>
                    <th scope="col">Canal</th>
                    <th scope="col" className="numero">Venta neta</th>
                    <th scope="col" className="columna-participacion">Participación</th>
                  </tr>
                </thead>
                <tbody>
                  {canalesFacturados.data.filas.map((fila) => (
                    <tr key={fila.canal}>
                      <th scope="row">{fila.canal}</th>
                      <td className="numero">{dinero(fila.venta)}</td>
                      <td className="columna-participacion">
                        <div className="participacion">
                          <span className="participacion__cifra">{porcentaje(fila.participacion)}</span>
                          <BarraParticipacion valor={fila.participacion} />
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr>
                    <th scope="row">Total facturado</th>
                    <td className="numero">{dinero(canalesFacturados.data.total_venta)}</td>
                    <td className="numero">{porcentaje("1")}</td>
                  </tr>
                </tfoot>
              </table>
            </div>
          )}
        </Tarjeta>
      ) : null}

      {!esCanalFacturado && data ? (
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
