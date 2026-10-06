import { useMemo, useState } from "react";

import { useInventarioPdv } from "@/api/consultas";
import type { FilaInventarioPdv } from "@/api/tipos";
import { AvisoError, Cargando, Tarjeta, Vacio } from "@/componentes/comunes";

const FILAS_POR_PAGINA = 50;

function normalizarBusqueda(valor: string): string {
  return valor.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLocaleLowerCase();
}

function etiquetaColumna(valor: string): string {
  const etiquetas: Record<string, string> = {
    existencia: "Existencia",
    disponible: "Disponible",
    comprometida: "Comprometida",
    pendiente_entrada: "Pendiente de entrada",
    pendiente_salida: "Pendiente de salida",
  };
  return etiquetas[valor] ?? valor.replace(/[_-]+/g, " ").trim();
}

function textoFila(fila: FilaInventarioPdv): string {
  return [
    fila.compania,
    fila.punto_venta,
    fila.codigo_producto,
    fila.referencia,
    fila.unidad,
    fila.existencia,
    fila.disponible,
    fila.comprometida,
    fila.pendiente_entrada,
    fila.pendiente_salida,
    ...Object.values(fila.datos),
  ]
    .filter((valor): valor is string | number => valor !== null && valor !== undefined)
    .join(" ");
}

export function InventarioPdv() {
  const consulta = useInventarioPdv();
  const [compania, setCompania] = useState("");
  const [puntoVenta, setPuntoVenta] = useState("");
  const [producto, setProducto] = useState("");
  const [busqueda, setBusqueda] = useState("");
  const [pagina, setPagina] = useState(1);

  const filas = consulta.data?.filas ?? [];
  const columnasCantidad = useMemo(
    () =>
      (consulta.data?.columnas ?? []).filter((columna) =>
        ["existencia", "disponible", "comprometida", "pendiente_entrada", "pendiente_salida"].includes(columna),
      ),
    [consulta.data?.columnas],
  );
  const columnasAtributos = useMemo(
    () =>
      (consulta.data?.columnas ?? []).filter(
        (columna) =>
          ![
            "referencia",
            "codigo_producto",
            "producto",
            "unidad",
            "existencia",
            "disponible",
            "comprometida",
            "pendiente_entrada",
            "pendiente_salida",
          ].includes(columna) && !/^(id_?)?tpv$/i.test(columna.replace(/[_ -]/g, "")),
      ),
    [consulta.data?.columnas],
  );
  const companias = useMemo(
    () =>
      [...new Set(filas.flatMap((fila) => (fila.compania === null ? [] : [fila.compania])))].sort(
        (a, b) => a - b,
      ),
    [filas],
  );
  const puntosVenta = useMemo(
    () =>
      [...new Set(
        filas
          .filter((fila) => !compania || fila.compania === Number(compania))
          .flatMap((fila) => (fila.punto_venta ? [fila.punto_venta] : [])),
      )].sort((a, b) => a.localeCompare(b)),
    [compania, filas],
  );
  const filasFiltradas = useMemo(() => {
    const termino = normalizarBusqueda(busqueda.trim());
    const terminoProducto = normalizarBusqueda(producto.trim());
    return filas.filter((fila) => {
      if (compania && fila.compania !== Number(compania)) return false;
      if (puntoVenta && fila.punto_venta !== puntoVenta) return false;
      if (terminoProducto && !normalizarBusqueda(fila.producto ?? "").includes(terminoProducto)) {
        return false;
      }
      return !termino || normalizarBusqueda(textoFila(fila)).includes(termino);
    });
  }, [busqueda, compania, filas, producto, puntoVenta]);

  const totalPaginas = Math.max(1, Math.ceil(filasFiltradas.length / FILAS_POR_PAGINA));
  const inicio = (pagina - 1) * FILAS_POR_PAGINA;
  const filasPagina = filasFiltradas.slice(inicio, inicio + FILAS_POR_PAGINA);

  function cambiarFiltro(cambiar: () => void) {
    cambiar();
    setPagina(1);
  }

  return (
    <div className="pila">
      <AvisoError error={consulta.error} />
      <Tarjeta
        titulo="Inventario por punto de venta"
        descripcion="Una fila por producto y punto de venta; las filas repetidas del mismo artículo dentro del punto se consolidan."
        sinRelleno
        acciones={
          <form
            className="formulario formulario--linea"
            onSubmit={(evento) => evento.preventDefault()}
          >
            <label className="campo">
              <span>Compañía</span>
              <select
                className="campo__control"
                value={compania}
                onChange={(evento) => cambiarFiltro(() => {
                  setCompania(evento.target.value);
                  setPuntoVenta("");
                })}
              >
                <option value="">Todas</option>
                {companias.map((codigo) => (
                  <option key={codigo} value={codigo}>{codigo}</option>
                ))}
              </select>
            </label>
            <label className="campo">
              <span>Punto de venta</span>
              <select
                className="campo__control"
                value={puntoVenta}
                onChange={(evento) => cambiarFiltro(() => setPuntoVenta(evento.target.value))}
              >
                <option value="">Todos</option>
                {puntosVenta.map((nombre) => (
                  <option key={nombre} value={nombre}>{nombre}</option>
                ))}
              </select>
            </label>
            <label className="campo">
              <span>Producto</span>
              <input
                className="campo__control"
                type="search"
                placeholder="Nombre del producto…"
                value={producto}
                onChange={(evento) => cambiarFiltro(() => setProducto(evento.target.value))}
              />
            </label>
            <label className="campo">
              <span>Buscar</span>
              <input
                className="campo__control"
                type="search"
                placeholder="Código o referencia…"
                value={busqueda}
                onChange={(evento) => cambiarFiltro(() => setBusqueda(evento.target.value))}
              />
            </label>
            <button
              type="button"
              className="boton boton--pequeno"
              onClick={() => void consulta.refetch()}
              disabled={consulta.isFetching}
            >
              {consulta.isFetching ? "Actualizando…" : "Actualizar"}
            </button>
          </form>
        }
      >
        {consulta.isLoading ? <Cargando texto="Consultando inventario en SIESA…" /> : null}
        {!consulta.isLoading && consulta.data && filas.length === 0 ? (
          <Vacio
            titulo="Sin filas de inventario"
            detalle="SIESA no devolvió existencias para las compañías disponibles."
          />
        ) : null}
        {!consulta.isLoading && consulta.data && filas.length > 0 && filasFiltradas.length === 0 ? (
          <Vacio
            titulo="Sin coincidencias"
            detalle="Ajusta los filtros de producto, búsqueda, compañía o punto de venta."
          />
        ) : null}
        {!consulta.isLoading && consulta.data && filasFiltradas.length > 0 ? (
          <>
            <div className="tabla-envoltorio tabla-envoltorio--alta">
              <table className="tabla tabla--anclada" aria-busy={consulta.isFetching}>
                <caption className="solo-lectores">
                  Inventario agrupado por punto de venta y producto, sin mostrar códigos de TPV.
                </caption>
                <thead>
                  <tr>
                    <th scope="col" className="columna-ancla">Punto de venta</th>
                    <th scope="col">Compañía</th>
                    <th scope="col">Código producto</th>
                    <th scope="col">Referencia</th>
                    <th scope="col">Producto</th>
                    <th scope="col">Unidad</th>
                    {columnasCantidad.map((columna) => (
                      <th key={columna} scope="col" className="numero">
                        {etiquetaColumna(columna)}
                      </th>
                    ))}
                    {columnasAtributos.map((columna) => (
                      <th key={columna} scope="col">{etiquetaColumna(columna)}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {filasPagina.map((fila, indice) => (
                    <tr
                      key={`${fila.compania ?? ""}-${fila.punto_venta ?? ""}-${fila.codigo_producto ?? fila.referencia ?? ""}-${inicio + indice}`}
                    >
                      <th scope="row" className="columna-ancla">{fila.punto_venta ?? "—"}</th>
                      <td>{fila.compania ?? "—"}</td>
                      <td>{fila.codigo_producto ?? "—"}</td>
                      <td>{fila.referencia ?? "—"}</td>
                      <td>{fila.producto ?? "—"}</td>
                      <td>{fila.unidad ?? "—"}</td>
                      {columnasCantidad.map((columna) => (
                        <td key={columna} className="numero">
                          {fila[
                            columna as
                              | "existencia"
                              | "disponible"
                              | "comprometida"
                              | "pendiente_entrada"
                              | "pendiente_salida"
                          ] ?? "—"}
                        </td>
                      ))}
                      {columnasAtributos.map((columna) => (
                        <td key={columna}>{fila.datos[columna] ?? "—"}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="fila" style={{ justifyContent: "space-between", padding: "var(--espacio-3) var(--espacio-4)" }}>
              <span className="tenue">
                {inicio + 1}–{Math.min(inicio + FILAS_POR_PAGINA, filasFiltradas.length)} de {filasFiltradas.length} filas de producto
                {filasFiltradas.length !== consulta.data.total ? ` · ${consulta.data.total} en total` : ""}
              </span>
              <div className="fila">
                <button
                  type="button"
                  className="boton boton--pequeno"
                  onClick={() => setPagina((actual) => Math.max(1, actual - 1))}
                  disabled={pagina <= 1}
                >
                  Anterior
                </button>
                <span className="tenue">Página {pagina} de {totalPaginas}</span>
                <button
                  type="button"
                  className="boton boton--pequeno"
                  onClick={() => setPagina((actual) => Math.min(totalPaginas, actual + 1))}
                  disabled={pagina >= totalPaginas}
                >
                  Siguiente
                </button>
              </div>
            </div>
          </>
        ) : null}
      </Tarjeta>
    </div>
  );
}