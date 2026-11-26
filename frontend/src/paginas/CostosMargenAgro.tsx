import { useMemo, useState } from "react";

import { useCostosMargenAgro } from "@/api/consultasAgro";
import type { FilaCostoAgro } from "@/api/tiposAgro";
import { AvisoError, Cargando, Tarjeta, Vacio } from "@/componentes/comunes";
import { BarraFiltrosAgro, filtrosAgroDe, useFiltros } from "@/componentes/filtros";
import { Indicador } from "@/componentes/indicadores";
import { dinero, porcentaje } from "@/utilidades/formato";

function normalizar(texto: string): string {
  return texto.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLocaleLowerCase("es");
}

function TablaCostosAgro({
  titulo,
  filas,
  productos = false,
}: {
  titulo: string;
  filas: FilaCostoAgro[];
  productos?: boolean;
}) {
  const [busqueda, setBusqueda] = useState("");
  const [disponibilidad, setDisponibilidad] = useState<"todos" | "con-costo" | "sin-costo">("todos");
  const patron = normalizar(busqueda.trim());

  const visibles = useMemo(
    () => filas.filter((fila) => {
      const coincide = !patron || normalizar(`${fila.clave} ${fila.nombre}`).includes(patron);
      const coincideCosto =
        disponibilidad === "todos" ||
        (disponibilidad === "con-costo" ? fila.costo != null : fila.costo == null);
      return coincide && coincideCosto;
    }),
    [filas, patron, disponibilidad],
  );

  return (
    <Tarjeta titulo={titulo} sinRelleno>
      {filas.length === 0 ? (
        <Vacio titulo="Sin costos en el corte" detalle="No hay líneas con costo en los filtros seleccionados." />
      ) : (
        <>
          {productos ? (
            <section className="filtros" aria-label="Buscar y filtrar productos">
              <label className="filtros__campo">
                <span>Buscar producto</span>
                <input
                  className="campo__control"
                  type="search"
                  placeholder="Referencia o nombre…"
                  value={busqueda}
                  onChange={(evento) => setBusqueda(evento.target.value)}
                />
              </label>
              <label className="filtros__campo">
                <span>Disponibilidad de costo</span>
                <select
                  className="campo__control"
                  value={disponibilidad}
                  onChange={(evento) => setDisponibilidad(evento.target.value as "todos" | "con-costo" | "sin-costo")}
                >
                  <option value="todos">Todos los productos</option>
                  <option value="con-costo">Con costo</option>
                  <option value="sin-costo">Sin costo</option>
                </select>
              </label>
              <span className="tenue" role="status">
                {visibles.length} de {filas.length} productos
              </span>
            </section>
          ) : (
            <section className="filtros" aria-label={`Buscar ${titulo}`}>
              <label className="filtros__campo">
                <span>Buscar</span>
                <input
                  className="campo__control"
                  type="search"
                  placeholder="Código o nombre…"
                  value={busqueda}
                  onChange={(evento) => setBusqueda(evento.target.value)}
                />
              </label>
            </section>
          )}

          {visibles.length === 0 ? (
            <Vacio titulo="Sin resultados" detalle="Cambia la búsqueda o el filtro de costo." />
          ) : (
            <div className="tabla-envoltorio">
              <table className="tabla tabla--costos">
                <thead>
                  <tr>
                    <th scope="col">{productos ? "Producto" : "Descripción"}</th>
                    <th scope="col" className="numero">Venta</th>
                    <th scope="col" className="numero">Costo</th>
                    <th scope="col" className="numero">Margen</th>
                    <th scope="col" className="numero">Margen %</th>
                  </tr>
                </thead>
                <tbody>
                  {visibles.map((fila) => (
                    <tr key={fila.clave}>
                      <th scope="row" title={fila.nombre}>{fila.nombre}</th>
                      <td className="numero">{dinero(fila.venta)}</td>
                      <td className="numero">{fila.costo == null ? "—" : dinero(fila.costo)}</td>
                      <td className="numero">{fila.margen_valor == null ? "—" : dinero(fila.margen_valor)}</td>
                      <td className="numero">{fila.margen_porcentaje == null ? "—" : porcentaje(fila.margen_porcentaje)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </Tarjeta>
  );
}

export function CostosMargenAgro() {
  const control = useFiltros();
  const filtros = useMemo(() => filtrosAgroDe(control.filtros), [control.filtros]);
  const { data, isLoading, error } = useCostosMargenAgro(filtros);

  return (
    <div className="pila">
      <BarraFiltrosAgro control={control} mostrar={{ rango: true, centro: true }} />
      <AvisoError error={error} />
      {isLoading ? <Cargando texto="Calculando costos y margen…" /> : null}

      {data ? (
        <>
          <Tarjeta
            titulo="Costos y margen"
            descripcion={`Venta, costo, impuesto y margen acumulados al ${data.fecha_corte}.`}
            sinRelleno
          >
            <div className="rejilla rejilla--indicadores">
              <Indicador etiqueta="Venta" valor={dinero(data.consolidado.venta)} tono="exito" />
              <Indicador
                etiqueta="Costo"
                valor={data.consolidado.costo == null ? "—" : dinero(data.consolidado.costo)}
                tono="aviso"
              />
              <Indicador etiqueta="Impuesto" valor={dinero(data.consolidado.impuesto)} tono="peligro" />
              <Indicador
                etiqueta="Margen"
                valor={data.consolidado.margen_porcentaje == null ? "—" : porcentaje(data.consolidado.margen_porcentaje)}
                nota={data.consolidado.margen_valor == null ? undefined : dinero(data.consolidado.margen_valor)}
                tono={data.consolidado.margen_porcentaje?.trim().startsWith("-") ? "peligro" : "exito"}
              />
            </div>
          </Tarjeta>

          <TablaCostosAgro titulo="Costo por centro de operación" filas={data.centros} />
          <TablaCostosAgro titulo="Costo por categoría" filas={data.categorias} />
          <TablaCostosAgro titulo="Costo por producto" filas={data.productos} productos />
        </>
      ) : null}
    </div>
  );
}
