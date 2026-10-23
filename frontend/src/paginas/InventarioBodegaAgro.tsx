import { useMemo, useState } from "react";

import { useExistenciasBodegaAgro } from "@/api/consultas";
import { AvisoError, Cargando, Tarjeta, Vacio } from "@/componentes/comunes";

const FILAS_POR_PAGINA = 50;

function normalizar(valor: string): string {
  return valor
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]/gi, "")
    .toLocaleLowerCase();
}

function buscarColumnaBodega(columnas: string[]): string | null {
  const preferidas = ["bodegadescripcion", "descripcionbodega", "nombrebodega"];
  for (const preferida of preferidas) {
    const columna = columnas.find((nombre) => normalizar(nombre) === preferida);
    if (columna) return columna;
  }
  return columnas.find((nombre) => {
    const clave = normalizar(nombre);
    return ["bodega", "bodegacodigo", "codigobodega", "almacen", "codigoalmacen"].includes(clave);
  }) ?? null;
}

function buscarColumnasCentroOperacion(columnas: string[]): {
  codigo: string | null;
  descripcion: string | null;
} {
  const codigo = columnas.find((nombre) =>
    ["co", "cocodigo", "coid", "codigocentrooperacion", "centrooperacioncodigo"].includes(
      normalizar(nombre),
    ),
  ) ?? null;
  const descripcion = columnas.find((nombre) =>
    ["codescripcion", "centrooperacion", "centrooperaciondescripcion", "descco"].includes(
      normalizar(nombre),
    ),
  ) ?? null;
  return { codigo, descripcion };
}

function buscarColumnaProducto(columnas: string[]): string | null {
  const preferidas = ["itemdescripcion", "descripcionitem", "producto", "item"];
  for (const preferida of preferidas) {
    const columna = columnas.find((nombre) => normalizar(nombre) === preferida);
    if (columna) return columna;
  }
  return null;
}

function etiquetaColumna(columna: string): string {
  const clave = normalizar(columna);
  const etiquetas: Record<string, string> = {
    cia: "Compañía",
    compania: "Compañía",
    bodega: "Bodega",
    bodegacodigo: "Código bodega",
    bodegadescripcion: "Bodega",
    codigobodega: "Código bodega",
    descripcionbodega: "Bodega",
    co: "Centro de operación",
    cocodigo: "C.O.",
    codescripcion: "Centro de operación",
    coid: "C.O.",
    centrooperacion: "Centro de operación",
    centrooperacioncodigo: "C.O.",
    centrooperaciondescripcion: "Centro de operación",
    descco: "Centro de operación",
    item: "Item ID",
    itemid: "Item ID",
    iditem: "Item ID",
    itemcodigo: "Item ID",
    codigoitem: "Item ID",
    itemreferencia: "Referencia",
    referencia: "Referencia",
    itemdescripcion: "Producto",
    descripcion: "Descripción",
    unidad: "Unidad",
    existencia: "Existencia",
    costo: "Costo",
    costopromedio: "Costo promedio unitario",
    costototal: "Costo total",
  };
  return etiquetas[clave] ?? columna.replace(/[_-]+/g, " ").trim();
}

function valorFila(fila: Record<string, string | null>, columna: string): string {
  return fila[columna] ?? "—";
}

function textoFila(fila: Record<string, string | null>): string {
  return Object.values(fila)
    .filter((valor): valor is string => valor !== null)
    .join(" ")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLocaleLowerCase();
}

export function InventarioBodegaAgro() {
  const consulta = useExistenciasBodegaAgro();
  const [bodega, setBodega] = useState("");
  const [centroOperacion, setCentroOperacion] = useState("");
  const [busqueda, setBusqueda] = useState("");
  const [pagina, setPagina] = useState(1);

  const columnas = consulta.data?.columnas ?? [];
  const filas = consulta.data?.filas ?? [];
  const columnaBodega = buscarColumnaBodega(columnas);
  const columnasCentroOperacion = buscarColumnasCentroOperacion(columnas);
  const columnaCentroOperacionFiltro = columnasCentroOperacion.codigo ?? columnasCentroOperacion.descripcion;
  const columnaProducto = buscarColumnaProducto(columnas);
  const bodegas = useMemo(
    () =>
      columnaBodega
        ? [...new Set(filas.flatMap((fila) => (fila[columnaBodega] ? [fila[columnaBodega]] : [])))].sort(
            (primera, segunda) => primera.localeCompare(segunda, "es-CO", { numeric: true }),
          )
        : [],
    [columnaBodega, filas],
  );
  const centrosOperacion = useMemo(() => {
    if (!columnaCentroOperacionFiltro) return [];
    const opciones = new Map<string, string>();
    for (const fila of filas) {
      const codigo = columnasCentroOperacion.codigo ? fila[columnasCentroOperacion.codigo] : null;
      const descripcion = columnasCentroOperacion.descripcion
        ? fila[columnasCentroOperacion.descripcion]
        : null;
      const valor = codigo || descripcion;
      if (!valor) continue;
      const etiqueta = codigo && descripcion ? `${codigo} · ${descripcion}` : valor;
      opciones.set(valor, etiqueta);
    }
    return [...opciones.entries()]
      .map(([valor, etiqueta]) => ({ valor, etiqueta }))
      .sort((primero, segundo) => primero.etiqueta.localeCompare(segundo.etiqueta, "es-CO", { numeric: true }));
  }, [columnaCentroOperacionFiltro, columnasCentroOperacion.codigo, columnasCentroOperacion.descripcion, filas]);
  const filasFiltradas = useMemo(() => {
    const termino = busqueda.trim().normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLocaleLowerCase();
    return filas.filter((fila) => {
      if (bodega && columnaBodega && fila[columnaBodega] !== bodega) return false;
      if (
        centroOperacion &&
        columnaCentroOperacionFiltro &&
        fila[columnaCentroOperacionFiltro] !== centroOperacion
      ) return false;
      return !termino || textoFila(fila).includes(termino);
    });
  }, [bodega, busqueda, centroOperacion, columnaBodega, columnaCentroOperacionFiltro, filas]);

  const totalPaginas = Math.max(1, Math.ceil(filasFiltradas.length / FILAS_POR_PAGINA));
  const inicio = (pagina - 1) * FILAS_POR_PAGINA;
  const filasPagina = filasFiltradas.slice(inicio, inicio + FILAS_POR_PAGINA);
  const columnaAncla = columnaBodega ?? columnas[0];

  function cambiarFiltro(cambiar: () => void) {
    cambiar();
    setPagina(1);
  }

  return (
    <div className="pila">
      <AvisoError error={consulta.error} />
      <Tarjeta
        titulo="Inventario de Agropecuaria por bodega"
        descripcion="Existencias de SIESA para la compañía 3. Los valores y encabezados se muestran tal como los entrega el origen."
        sinRelleno
        acciones={(
          <form className="formulario formulario--linea" onSubmit={(evento) => evento.preventDefault()}>
            {columnaBodega ? (
              <label className="campo">
                <span>Bodega</span>
                <select
                  className="campo__control"
                  value={bodega}
                  onChange={(evento) => cambiarFiltro(() => setBodega(evento.target.value))}
                >
                  <option value="">Todas</option>
                  {bodegas.map((opcion) => <option key={opcion} value={opcion}>{opcion}</option>)}
                </select>
              </label>
            ) : null}
            {columnaCentroOperacionFiltro ? (
              <label className="campo">
                <span>C.O.</span>
                <select
                  className="campo__control"
                  value={centroOperacion}
                  onChange={(evento) => cambiarFiltro(() => setCentroOperacion(evento.target.value))}
                >
                  <option value="">Todos</option>
                  {centrosOperacion.map((opcion) => (
                    <option key={opcion.valor} value={opcion.valor}>{opcion.etiqueta}</option>
                  ))}
                </select>
              </label>
            ) : null}
            <label className="campo">
              <span>Buscar</span>
              <input
                className="campo__control"
                type="search"
                placeholder="Bodega, referencia o producto…"
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
        )}
      >
        {consulta.isLoading ? <Cargando texto="Consultando existencias de Agropecuaria…" /> : null}
        {!consulta.isLoading && consulta.data && filas.length === 0 ? (
          <Vacio titulo="Sin existencias de Agropecuaria" detalle="SIESA no devolvió filas para la compañía 3." />
        ) : null}
        {!consulta.isLoading && consulta.data && filas.length > 0 && filasFiltradas.length === 0 ? (
          <Vacio titulo="Sin coincidencias" detalle="Ajusta la bodega o el texto de búsqueda." />
        ) : null}
        {!consulta.isLoading && consulta.data && filasFiltradas.length > 0 ? (
          <>
            <div className="tabla-envoltorio tabla-envoltorio--alta">
              <table className="tabla tabla--anclada" aria-busy={consulta.isFetching}>
                <caption className="solo-lectores">
                  Existencias de inventario por bodega para Agropecuaria, compañía 3.
                </caption>
                <thead>
                  <tr>
                    {columnas.map((columna) => (
                      <th
                        key={columna}
                        scope="col"
                        className={columna === columnaAncla ? "columna-ancla" : undefined}
                      >
                        {etiquetaColumna(columna)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {filasPagina.map((fila, indice) => (
                    <tr key={`${inicio + indice}-${valorFila(fila, columnaBodega ?? "bodega")}-${valorFila(fila, columnaProducto ?? "item")}`}>
                      {columnas.map((columna) => (
                        <td
                          key={columna}
                          className={/exist|cantidad|costo|total|disponible/i.test(normalizar(columna)) ? "numero" : undefined}
                        >
                          {valorFila(fila, columna)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="fila" style={{ justifyContent: "space-between", padding: "var(--espacio-3) var(--espacio-4)" }}>
              <span className="tenue">
                {inicio + 1}–{Math.min(inicio + FILAS_POR_PAGINA, filasFiltradas.length)} de {filasFiltradas.length} filas
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