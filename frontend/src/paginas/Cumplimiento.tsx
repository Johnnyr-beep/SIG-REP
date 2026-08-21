/**
 * Cumplimiento por punto de venta — la tabla del Excel, viva.
 *
 * Mismas columnas que el libro que reemplaza, más las dos que allí estaban mal
 * (proyección y venta diaria requerida, §4.2), calculadas por el backend con las
 * fórmulas escritas y con `H` y `T` a la vista en el pie. Cada fila se despliega
 * a sus categorías: el punto puede ir bien y la res ir mal, y ese es justamente
 * el análisis que hoy exige rehacer una tabla dinámica.
 */

import { Fragment, useMemo, useState } from "react";

import { useCumplimiento, useExportar } from "@/api/consultas";
import type { FilaPuntoVentaReporte } from "@/api/tipos";
import { AvisoError, Cargando, Tarjeta, Vacio } from "@/componentes/comunes";
import { BarraFiltros, useFiltros } from "@/componentes/filtros";
import {
  COLUMNAS_INDICADORES,
  CeldasIndicadores,
  EncabezadosIndicadores,
  PieCalculo,
} from "@/componentes/indicadores";
import { claveDe, etiquetaDe } from "@/utilidades/dominio";

export function Cumplimiento() {
  const control = useFiltros();
  const { filtros } = control;
  const { data, isLoading, error } = useCumplimiento(filtros);
  const exportar = useExportar();

  const [desplegadas, setDesplegadas] = useState<ReadonlySet<string>>(
    new Set(),
  );

  const medida = data?.medida ?? filtros.medida;
  const filas = useMemo(() => data?.filas ?? [], [data]);
  const todasDesplegadas =
    filas.length > 0 && desplegadas.size === filas.length;

  function alternar(clave: string) {
    setDesplegadas((anteriores) => {
      const siguientes = new Set(anteriores);
      if (siguientes.has(clave)) siguientes.delete(clave);
      else siguientes.add(clave);
      return siguientes;
    });
  }

  function alternarTodas() {
    setDesplegadas(
      todasDesplegadas
        ? new Set()
        : new Set(
            filas.map((fila, indice) =>
              claveDe(fila.punto_venta, String(indice)),
            ),
          ),
    );
  }

  return (
    <div className="pila">
      <BarraFiltros
        control={control}
        mostrar={{ categoria: true }}
        acciones={
          <>
            <button
              type="button"
              className="boton boton--pequeno"
              onClick={alternarTodas}
              disabled={filas.length === 0}
            >
              {todasDesplegadas ? "Contraer todo" : "Desplegar categorías"}
            </button>
            <button
              type="button"
              className="boton boton--pequeno"
              onClick={() =>
                exportar.mutate({ reporte: "cumplimiento", filtros })
              }
              disabled={exportar.isPending}
            >
              {exportar.isPending ? "Generando…" : "Exportar a Excel"}
            </button>
          </>
        }
      />

      <AvisoError error={error} />
      <AvisoError error={exportar.error} />

      {isLoading ? <Cargando texto="Calculando el cumplimiento…" /> : null}

      {data ? (
        <Tarjeta
          titulo="Cumplimiento por punto de venta"
          descripcion="Pulse el nombre de un punto para ver el detalle por categoría."
          sinRelleno
          pie={
            <PieCalculo parametros={data.parametros_calculo} medida={medida} />
          }
        >
          {filas.length === 0 ? (
            <Vacio
              titulo="Sin puntos de venta"
              detalle="Ningún punto coincide con los filtros seleccionados."
            />
          ) : (
            <div className="tabla-envoltorio tabla-envoltorio--alta">
              <table className="tabla tabla--anclada">
                <caption className="solo-lectores">
                  Cumplimiento contra presupuesto por punto de venta y
                  categoría, al {data.fecha_corte}.
                </caption>
                <thead>
                  <tr>
                    <th scope="col" className="columna-ancla">
                      Punto de venta
                    </th>
                    <EncabezadosIndicadores medida={medida} />
                  </tr>
                </thead>
                <tbody>
                  {filas.map((fila, indice) => (
                    <FilaPdv
                      key={claveDe(fila.punto_venta, String(indice))}
                      fila={fila}
                      medida={medida}
                      desplegada={desplegadas.has(
                        claveDe(fila.punto_venta, String(indice)),
                      )}
                      onAlternar={() =>
                        alternar(claveDe(fila.punto_venta, String(indice)))
                      }
                    />
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

function FilaPdv({
  fila,
  medida,
  desplegada,
  onAlternar,
}: {
  fila: FilaPuntoVentaReporte;
  medida: "valor" | "kilos";
  desplegada: boolean;
  onAlternar: () => void;
}) {
  // La referencia viaja plana: `punto_venta` es el código C.O. y `nombre` la
  // etiqueta. Leer `punto_venta` como etiqueta llenaría la tabla de códigos.
  const nombre = fila.nombre;
  const codigo = fila.punto_venta;
  const categorias = fila.categorias ?? [];
  const tieneDetalle = categorias.length > 0;

  return (
    <Fragment>
      <tr className="fila-padre">
        <th scope="row" className="columna-ancla">
          {tieneDetalle ? (
            <button
              type="button"
              className="desplegar"
              onClick={onAlternar}
              aria-expanded={desplegada}
            >
              <span className="desplegar__signo" aria-hidden="true">
                {desplegada ? "−" : "+"}
              </span>
              <span>
                {nombre}
                {codigo ? (
                  <span className="tenue mono"> · {codigo}</span>
                ) : null}
              </span>
            </button>
          ) : (
            <span className="desplegar desplegar--inerte">
              <span className="desplegar__signo" aria-hidden="true">
                ·
              </span>
              <span>
                {nombre}
                {codigo ? (
                  <span className="tenue mono"> · {codigo}</span>
                ) : null}
              </span>
            </span>
          )}
        </th>
        <CeldasIndicadores fila={fila} medida={medida} />
      </tr>

      {desplegada
        ? categorias.map((categoria, indice) => (
            <tr
              key={claveDe(categoria.categoria, String(indice))}
              className="fila-hija"
            >
              <th scope="row" className="columna-ancla columna-ancla--hija">
                <span className="fila-hija__nombre">
                  {etiquetaDe(categoria.categoria)}
                </span>
              </th>
              <CeldasIndicadores fila={categoria} medida={medida} />
            </tr>
          ))
        : null}

      {desplegada && categorias.length === 0 ? (
        <tr className="fila-hija">
          <td
            className="columna-ancla columna-ancla--hija"
            colSpan={COLUMNAS_INDICADORES + 1}
          >
            <span className="tenue">
              Este punto de venta no tiene desglose por categoría.
            </span>
          </td>
        </tr>
      ) : null}
    </Fragment>
  );
}
