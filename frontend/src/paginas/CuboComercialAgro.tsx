/**
 * Cubo comercial configurable, equivalente al Filtro Cubo de SIESA.
 *
 * La pantalla no vuelve a llamar al ERP: lee las ventas que SIGREP ya sincronizó
 * desde SIESA. Así conserva un corte reproducible y no pone al usuario a
 * esperar una consulta remota cada vez que cambia la jerarquía.
 */

import { useMemo } from "react";
import { useSearchParams } from "react-router-dom";

import { useCuboAgro } from "@/api/consultasAgro";
import type { DimensionCuboAgro, FilaCuboAgro } from "@/api/tiposAgro";
import { AvisoError, Cargando, Tarjeta, Vacio } from "@/componentes/comunes";
import { BarraFiltrosAgro, filtrosAgroDe, useFiltros } from "@/componentes/filtros";
import {
  DIMENSIONES_CUBO,
  esDimensionCubo,
  etiquetaDimensionCubo,
} from "@/utilidades/dominioAgro";
import { dinero, kilos, numero } from "@/utilidades/formato";

const DIMENSIONES_POR_DEFECTO: DimensionCuboAgro[] = [
  "tipo_comercial",
  "grupo",
  "tipo_item",
];
const MAXIMO_DIMENSIONES = 3;

export function CuboComercialAgro() {
  const control = useFiltros();
  const [parametros, setParametros] = useSearchParams();
  const dimensiones = dimensionesDe(parametros.get("dimensiones"));
  const filtroAgro = useMemo(() => filtrosAgroDe(control.filtros), [control.filtros]);
  const consulta = useCuboAgro(filtroAgro, dimensiones.join(","));

  function fijarDimensiones(siguientes: DimensionCuboAgro[]) {
    setParametros(
      (actuales) => {
        const nuevos = new URLSearchParams(actuales);
        nuevos.set("dimensiones", siguientes.join(","));
        return nuevos;
      },
      { replace: true },
    );
  }

  function alternar(dimension: DimensionCuboAgro) {
    if (dimensiones.includes(dimension)) {
      const siguientes = dimensiones.filter((actual) => actual !== dimension);
      if (siguientes.length > 0) fijarDimensiones(siguientes);
      return;
    }
    if (dimensiones.length < MAXIMO_DIMENSIONES) fijarDimensiones([...dimensiones, dimension]);
  }

  function mover(indice: number, direccion: -1 | 1) {
    const destino = indice + direccion;
    if (destino < 0 || destino >= dimensiones.length) return;
    const siguientes = [...dimensiones];
    const actual = siguientes[indice];
    const vecino = siguientes[destino];
    if (!actual || !vecino) return;
    siguientes[indice] = vecino;
    siguientes[destino] = actual;
    fijarDimensiones(siguientes);
  }

  const data = consulta.data;
  return (
    <div className="pila">
      <BarraFiltrosAgro control={control} mostrar={{ rango: true, medida: false }} />

      <section className="cubo__configuracion" aria-labelledby="cubo-titulo">
        <div className="cubo__introduccion">
          <p className="inteligencia__eyebrow">Cubo comercial</p>
          <h2 id="cubo-titulo">Explore la venta desde cualquier jerarquía</h2>
          <p className="suave">
            Seleccione hasta tres dimensiones. El orden define el desglose de la tabla,
            igual que en el Filtro Cubo de SIESA.
          </p>
        </div>

        <fieldset className="cubo__dimensiones">
          <legend>Dimensiones del cubo</legend>
          <div className="cubo__opciones">
            {DIMENSIONES_CUBO.map((opcion) => {
              const seleccionada = dimensiones.includes(opcion.valor);
              const deshabilitada = !seleccionada && dimensiones.length === MAXIMO_DIMENSIONES;
              return (
                <label
                  key={opcion.valor}
                  className={`cubo__opcion${seleccionada ? " cubo__opcion--seleccionada" : ""}`}
                  title={opcion.ayuda}
                >
                  <input
                    type="checkbox"
                    checked={seleccionada}
                    disabled={deshabilitada}
                    onChange={() => alternar(opcion.valor)}
                  />
                  <span>{opcion.etiqueta}</span>
                </label>
              );
            })}
          </div>
        </fieldset>

        <ol className="cubo__orden" aria-label="Orden de agrupación">
          {dimensiones.map((dimension, indice) => (
            <li key={dimension}>
              <span className="cubo__paso">{indice + 1}</span>
              <strong>{etiquetaDimensionCubo(dimension)}</strong>
              <span className="cubo__orden-acciones">
                <button
                  className="boton boton--sutil boton--pequeno"
                  type="button"
                  onClick={() => mover(indice, -1)}
                  disabled={indice === 0}
                  aria-label={`Subir ${etiquetaDimensionCubo(dimension)}`}
                >
                  ↑
                </button>
                <button
                  className="boton boton--sutil boton--pequeno"
                  type="button"
                  onClick={() => mover(indice, 1)}
                  disabled={indice === dimensiones.length - 1}
                  aria-label={`Bajar ${etiquetaDimensionCubo(dimension)}`}
                >
                  ↓
                </button>
              </span>
            </li>
          ))}
        </ol>
      </section>

      <AvisoError error={consulta.error} />
      {consulta.isLoading ? <Cargando texto="Construyendo el cubo comercial…" /> : null}

      {data ? (
        <>
          {data.truncado ? (
            <div className="aviso aviso--atencion" role="note">
              <div>
                <strong>Se muestran las {numero(data.limite)} combinaciones con mayor venta.</strong>
                <p>
                  El total conserva todo el corte. Para ver más detalle, reduzca el rango,
                  seleccione un centro o use una jerarquía menos específica.
                </p>
              </div>
            </div>
          ) : null}
          <Tarjeta
            titulo="Resultados del cubo"
            descripcion={`Corte al ${data.fecha_corte}. Importes netos de impuestos.`}
            sinRelleno
          >
            {data.filas.length === 0 ? (
              <Vacio
                titulo="Sin ventas para este corte"
                detalle="No hay líneas comerciales que coincidan con los filtros seleccionados."
              />
            ) : (
              <TablaCubo filas={data.filas} total={data.total} dimensiones={data.dimensiones} />
            )}
          </Tarjeta>
        </>
      ) : null}
    </div>
  );
}

function TablaCubo({
  filas,
  total,
  dimensiones,
}: {
  filas: FilaCuboAgro[];
  total: FilaCuboAgro;
  dimensiones: DimensionCuboAgro[];
}) {
  return (
    <div className="tabla-envoltorio tabla-envoltorio--alta">
      <table className="tabla tabla--anclada cubo__tabla">
        <caption className="solo-lectores">
          Cubo comercial por {dimensiones.map(etiquetaDimensionCubo).join(", ")}.
        </caption>
        <thead>
          <tr>
            {dimensiones.map((dimension, indice) => (
              <th key={dimension} scope="col" className={indice === 0 ? "columna-ancla" : undefined}>
                {etiquetaDimensionCubo(dimension)}
              </th>
            ))}
            <th className="numero" scope="col">Cantidad inv.</th>
            <th className="numero" scope="col">Peso kg</th>
            <th className="numero" scope="col">Valor bruto</th>
            <th className="numero" scope="col">Valor subtotal</th>
            <th className="numero" scope="col">Valor neto</th>
            <th className="numero" scope="col">Costo total</th>
            <th className="numero" scope="col">Utilidad bruta</th>
            <th className="numero" scope="col">Líneas</th>
          </tr>
        </thead>
        <tbody>
          <FilaMedidas fila={total} dimensiones={dimensiones} total />
          {filas.map((fila) => (
            <FilaMedidas
              key={fila.claves.join("·")}
              fila={fila}
              dimensiones={dimensiones}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function FilaMedidas({
  fila,
  dimensiones,
  total = false,
}: {
  fila: FilaCuboAgro;
  dimensiones: DimensionCuboAgro[];
  total?: boolean;
}) {
  return (
    <tr className={total ? "fila-total" : undefined}>
      {total ? (
        <>
          <th scope="row" className="columna-ancla">TOTAL DEL CORTE</th>
          {dimensiones.slice(1).map((dimension) => <td key={dimension} className="tenue">completo</td>)}
        </>
      ) : (
        fila.nombres.map((nombre, indice) => (
          <th
            key={`${fila.claves.join("·")}-${indice}`}
            scope={indice === 0 ? "row" : undefined}
            className={indice === 0 ? "columna-ancla" : "columna-texto"}
          >
            {nombre}
          </th>
        ))
      )}
      <td className="numero">{numero(fila.cantidad_inv, 3)}</td>
      <td className="numero">{kilos(fila.kilos_total, 3)}</td>
      <td className="numero">{dinero(fila.valor_bruto)}</td>
      <td className="numero">{dinero(fila.valor_subtotal)}</td>
      <td className="numero"><strong>{dinero(fila.total_neto)}</strong></td>
      <td className="numero">{fila.total_costo === null ? "—" : dinero(fila.total_costo)}</td>
      <td className="numero">{fila.utilidad_bruta === null ? "—" : dinero(fila.utilidad_bruta)}</td>
      <td className="numero">{numero(fila.lineas_facturadas)}</td>
    </tr>
  );
}

function dimensionesDe(valor: string | null): DimensionCuboAgro[] {
  const pedidas = (valor ?? "")
    .split(",")
    .filter(esDimensionCubo)
    .filter((dimension, indice, lista) => lista.indexOf(dimension) === indice)
    .slice(0, MAXIMO_DIMENSIONES);
  return pedidas.length > 0 ? pedidas : DIMENSIONES_POR_DEFECTO;
}
