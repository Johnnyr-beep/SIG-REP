/** Costos y margen de Carnes Santacruz, calculados sobre la venta cargada. */

import { useSearchParams } from "react-router-dom";
import { MODO_EJEMPLOS } from "@/api/cliente";
import { useState } from "react";
import { useCostos } from "@/api/consultas";
import type { FilaCostos } from "@/api/tipos";
import { useAuth } from "@/auth/ContextoAuth";
import { AvisoError, Cargando, Tarjeta, Vacio } from "@/componentes/comunes";
import { BarraFiltros, useFiltros } from "@/componentes/filtros";
import { Indicador, PieCalculo } from "@/componentes/indicadores";
import { dinero, numero, porcentaje } from "@/utilidades/formato";
import { AcumulacionTpv } from "./AcumulacionTpv";

export function Costos() {
  const [parametros, fijarParametros] = useSearchParams();
  const { tienePermiso } = useAuth();
  const vistaTpv = parametros.get("vista_costos") === "tpv";

  function cambiarVista(tpv: boolean) {
    const siguientes = new URLSearchParams(parametros);
    if (tpv) siguientes.set("vista_costos", "tpv");
    else siguientes.delete("vista_costos");
    fijarParametros(siguientes);
  }

  if (!MODO_EJEMPLOS && !tienePermiso("PERMISO_COSTO_POR_PDV")) return <CostosMargen />;

  return (
    <div className="pila">
      <section className="filtros" aria-label="Vistas de costos">
        <fieldset className="segmentado">
          <legend className="solo-lectores">Vista de costos</legend>
          <label className={`segmentado__opcion${!vistaTpv ? " segmentado__opcion--activa" : ""}`}>
            <input type="radio" name="vista-costos" checked={!vistaTpv} onChange={() => cambiarVista(false)} />
            Costos y margen
          </label>
          <label className={`segmentado__opcion${vistaTpv ? " segmentado__opcion--activa" : ""}`}>
            <input type="radio" name="vista-costos" checked={vistaTpv} onChange={() => cambiarVista(true)} />
            Acumulación y cierre de TPV
          </label>
        </fieldset>
      </section>
      {vistaTpv ? <AcumulacionTpv /> : <CostosMargen />}
    </div>
  );
}

function CostosMargen() {
  const control = useFiltros();
  const { filtros } = control;
  const { data, isLoading, error } = useCostos(filtros);
  const { tienePermiso } = useAuth();
  const tonoMargen =
    data?.consolidado.margen_porcentaje == null
      ? undefined
      : data.consolidado.margen_porcentaje.trim().startsWith("-")
        ? "peligro"
        : "exito";

  return (
    <div className="pila">
      <BarraFiltros control={control} mostrar={{ categoria: true, medida: false }} />
      <AvisoError error={error} />
      {isLoading ? <Cargando texto="Calculando costos y margen…" /> : null}
      {data ? (
        <>
          <Tarjeta
            titulo="Costos y margen"
            descripcion={`Venta y costo acumulados al ${data.fecha_corte}. El margen solo se publica con costo completo.`}
            pie={<PieCalculo parametros={data.parametros_calculo} medida="valor" />}
          >
            <div className="rejilla rejilla--indicadores">
              <Indicador etiqueta="Venta acumulada" valor={dinero(data.consolidado.venta)} tono="exito" />
              <Indicador etiqueta="Costo acumulado" valor={dinero(data.consolidado.costo)} tono="aviso" />
              <Indicador etiqueta="Margen" valor={porcentaje(data.consolidado.margen_porcentaje)} nota={dinero(data.consolidado.margen_valor)} tono={tonoMargen} />
            </div>
          </Tarjeta>
          {tienePermiso("PERMISO_COSTO_POR_GRUPO") ? (
            <TablaCostos titulo="Costo por grupo" etiqueta="Grupo" filas={data.grupos} />
          ) : null}
          {tienePermiso("PERMISO_COSTO_POR_PDV") ? (
            <TablaCostos titulo="Costo por punto de venta" etiqueta="Punto de venta" filas={data.puntos_venta} />
          ) : null}
          {tienePermiso("PERMISO_COSTO_POR_CATEGORIA") ? (
            <TablaCostos titulo="Costo por categoría" etiqueta="Categoría" filas={data.categorias} />
          ) : null}
          {tienePermiso("PERMISO_COSTO_POR_PRODUCTO") ? (
            <TablaCostos
              titulo="Costo por producto"
              etiqueta="Producto"
              alta
              variante="productos"
              filas={data.productos.map((producto) => ({
                ...producto,
                nombre: producto.referencia
                  ? `${producto.referencia} · ${producto.nombre}`
                  : producto.nombre,
              }))}
            />
          ) : null}
        </>
      ) : null}
    </div>
  );
}

function TablaCostos({ titulo, etiqueta, filas, alta = false, variante }: { titulo: string; etiqueta: string; filas: (FilaCostos & { nombre: string; referencia?: string | null })[]; alta?: boolean; variante?: string }) {
  const [busqueda, setBusqueda] = useState("");
  const [filtroCosto, setFiltroCosto] = useState("todos");
  const esProducto = variante === "productos";
  const patron = busqueda.trim().normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLocaleLowerCase("es");
  const filasVisibles = filas.filter((fila) => {
    const texto = `${fila.referencia ?? ""} ${fila.nombre}`.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLocaleLowerCase("es");
    const coincideBusqueda = !esProducto || patron === "" || texto.includes(patron);
    const coincideCosto = !esProducto || filtroCosto === "todos" || (filtroCosto === "con-costo" ? fila.costo != null : fila.costo == null);
    return coincideBusqueda && coincideCosto;
  });

  return (
    <Tarjeta titulo={titulo} sinRelleno>
      {filas.length === 0 ? (
        <Vacio titulo="Sin costo en el corte" detalle="Ninguna línea coincide con los filtros seleccionados." />
      ) : (
        <>
          {esProducto ? (
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
                <select className="campo__control" value={filtroCosto} onChange={(evento) => setFiltroCosto(evento.target.value)}>
                  <option value="todos">Todos los productos</option>
                  <option value="con-costo">Con costo</option>
                  <option value="sin-costo">Sin costo</option>
                </select>
              </label>
              <span className="tenue" role="status" aria-live="polite">
                {numero(String(filasVisibles.length))} de {numero(String(filas.length))} productos
              </span>
            </section>
          ) : null}
          {filasVisibles.length === 0 ? (
            <Vacio titulo="Sin productos que coincidan" detalle="Cambia la búsqueda o el filtro de disponibilidad de costo." />
          ) : (
            <div className={alta ? "tabla-envoltorio tabla-envoltorio--alta" : "tabla-envoltorio"}>
              <table className={variante ? `tabla tabla--costos tabla--costos--${variante}` : "tabla tabla--costos"}>
                <colgroup>
                  <col className="tabla--costos__nombre" />
                  <col className="tabla--costos__importe" />
                  <col className="tabla--costos__importe" />
                  <col className="tabla--costos__importe" />
                  <col className="tabla--costos__importe" />
                  <col className="tabla--costos__porcentaje" />
                  <col className="tabla--costos__importe" />
                  <col className="tabla--costos__porcentaje" />
                </colgroup>
                <thead>
                  <tr>
                    <th scope="col">{etiqueta}</th>
                    <th scope="col" className="numero">Venta</th>
                    <th scope="col" className="numero">Kilos</th>
                    <th scope="col" className="numero">Venta kilo</th>
                    <th scope="col" className="numero">Costo</th>
                    <th scope="col" className="numero">Costo %</th>
                    <th scope="col" className="numero">Margen</th>
                    <th scope="col" className="numero">Margen %</th>
                  </tr>
                </thead>
                <tbody>{filasVisibles.map((fila) => (
                  <tr key={fila.nombre}>
                    <th scope="row" title={fila.nombre}>{fila.nombre}</th>
                    <td className="numero">{dinero(fila.venta)}</td>
                    <td className="numero">{numero(fila.kilos)}</td>
                    <td className="numero">{dinero(fila.venta_por_kilo)}</td>
                    <td className="numero">{dinero(fila.costo)}</td>
                    <td className="numero">{porcentaje(fila.costo_porcentaje)}</td>
                    <td className="numero">{dinero(fila.margen_valor)}</td>
                    <td className="numero">{porcentaje(fila.margen_porcentaje)}</td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          )}
        </>
      )}
    </Tarjeta>
  );
}