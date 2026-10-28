import { useMemo, useState } from "react";

import { useCxcClientes } from "@/api/consultasFinanciero";
import { AvisoError, Cargando, Tarjeta, Vacio } from "@/componentes/comunes";
import { numero } from "@/utilidades/formato";

const FILAS_POR_PAGINA = 50;
const RANGOS_ANTIGUEDAD = [
  {
    valor: "1-30",
    etiqueta: "Vencido 1–30 días",
    columnas: ["vencido130", "total130", "totalvencido130", "saldo130"],
  },
  {
    valor: "31-60",
    etiqueta: "Vencido 31–60 días",
    columnas: ["vencido3160", "total3160", "totalvencido3160", "saldo3160"],
  },
  {
    valor: "61-90",
    etiqueta: "Vencido 61–90 días",
    columnas: ["vencido6190", "total6190", "totalvencido6190", "saldo6190"],
  },
  {
    valor: "mas-90",
    etiqueta: "Vencido más de 90 días",
    columnas: ["vencidomas90", "vencido90mas", "totalmas90", "totalvencidomas90", "saldo90mas"],
  },
] as const;

function fechaLocal(): string {
  const hoy = new Date();
  return `${hoy.getFullYear()}-${String(hoy.getMonth() + 1).padStart(2, "0")}-${String(hoy.getDate()).padStart(2, "0")}`;
}

function normalizar(valor: string): string {
  return valor
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]/gi, "")
    .toLocaleLowerCase();
}

function etiquetaColumna(columna: string): string {
  const clave = normalizar(columna);
  const etiquetas: Record<string, string> = {
    cia: "Compañía",
    compania: "Compañía",
    clasetercero: "Clase de tercero",
    auxiliar: "Auxiliar",
    naturaleza: "Naturaleza",
    nit: "NIT",
    cliente: "Cliente",
    desccliente: "Cliente",
    sucursal: "Sucursal",
    razonsocial: "Razón social",
    razonsocialsucursal: "Razón social sucursal",
    vendedor: "Vendedor",
    centrooperacion: "Centro de operación",
    descco: "Centro de operación",
    unidadnegocio: "Unidad de negocio",
    un: "Unidad de negocio",
    total: "Total COP",
    totalcorriente: "Total corriente COP",
    totalvencido: "Total vencido COP",
    vencido130: "Vencido 1–30 días COP",
    total130: "Vencido 1–30 días COP",
    vencido3160: "Vencido 31–60 días COP",
    total13160: "Vencido 31–60 días COP",
    total3160: "Vencido 31–60 días COP",
    vencido6190: "Vencido 61–90 días COP",
    total6190: "Vencido 61–90 días COP",
    vencidomas90: "Vencido más de 90 días COP",
    vencido90mas: "Vencido más de 90 días COP",
    totalmas90: "Vencido más de 90 días COP",
  };
  return etiquetas[clave] ?? columna.replace(/[_-]+/g, " ").trim();
}

function textoFila(fila: Record<string, string | null>): string {
  return Object.values(fila)
    .filter((valor): valor is string => valor !== null)
    .join(" ")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLocaleLowerCase();
}

function esImporte(columna: string): boolean {
  return /total|corriente|vencid|valor|importe|130|3160|6190|mas90/i.test(normalizar(columna));
}

function valorCelda(columna: string, valor: string | null | undefined): string {
  if (!esImporte(columna)) return valor ?? "—";
  const decimales = valor?.trim().split(/[.,]/)[1]?.length ?? 0;
  return numero(valor, decimales);
}

export function CxcClientes() {
  const [fechaCorte, setFechaCorte] = useState(fechaLocal);
  const [compania, setCompania] = useState("");
  const [naturaleza, setNaturaleza] = useState("");
  const [rangoAntiguedad, setRangoAntiguedad] = useState("");
  const [busqueda, setBusqueda] = useState("");
  const [pagina, setPagina] = useState(1);
  const consulta = useCxcClientes(fechaCorte);

  const columnas = consulta.data?.columnas ?? [];
  const filas = consulta.data?.filas ?? [];
  const columnaCompania = columnas.find((columna) => ["cia", "compania"].includes(normalizar(columna)));
  const columnaNaturaleza = columnas.find((columna) => normalizar(columna) === "naturaleza");
  const filtrosAntiguedad = RANGOS_ANTIGUEDAD.flatMap((rango) => {
    const columna = columnas.find((nombre) =>
      rango.columnas.some((alias) => alias === normalizar(nombre)),
    );
    return columna ? [{ ...rango, columna }] : [];
  });
  const companias = useMemo(
    () =>
      columnaCompania
        ? [...new Set(filas.flatMap((fila) => (fila[columnaCompania] ? [fila[columnaCompania]] : [])))].sort(
            (primera, segunda) => primera.localeCompare(segunda, "es-CO", { numeric: true }),
          )
        : [],
    [columnaCompania, filas],
  );
  const naturalezas = useMemo(
    () =>
      columnaNaturaleza
        ? [...new Set(filas.flatMap((fila) => (fila[columnaNaturaleza] ? [fila[columnaNaturaleza]] : [])))].sort(
            (primera, segunda) => primera.localeCompare(segunda, "es-CO"),
          )
        : [],
    [columnaNaturaleza, filas],
  );
  const filasFiltradas = useMemo(() => {
    const termino = busqueda.trim().normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLocaleLowerCase();
    return filas.filter((fila) => {
      if (compania && columnaCompania && fila[columnaCompania] !== compania) return false;
      if (naturaleza && columnaNaturaleza && fila[columnaNaturaleza] !== naturaleza) return false;
      if (rangoAntiguedad) {
        const columna = filtrosAntiguedad.find((rango) => rango.valor === rangoAntiguedad)?.columna;
        const saldo = columna ? Number(fila[columna]?.replace(",", ".") ?? "") : 0;
        if (!columna || !Number.isFinite(saldo) || saldo === 0) return false;
      }
      return !termino || textoFila(fila).includes(termino);
    });
  }, [busqueda, compania, columnaCompania, columnaNaturaleza, filas, filtrosAntiguedad, naturaleza, rangoAntiguedad]);

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
        titulo="CXC clientes"
        descripcion="Saldos por cliente, sucursal, vendedor y unidad de negocio. Incluye saldo corriente, vencido y antigüedad de cartera a la fecha de corte."
        sinRelleno
        acciones={(
          <form className="formulario formulario--linea" onSubmit={(evento) => evento.preventDefault()}>
            <label className="campo">
              <span>Fecha de corte</span>
              <input
                className="campo__control"
                type="date"
                value={fechaCorte}
                onChange={(evento) => cambiarFiltro(() => setFechaCorte(evento.target.value))}
                required
              />
            </label>
            {columnaCompania ? (
              <label className="campo">
                <span>Compañía</span>
                <select
                  className="campo__control"
                  value={compania}
                  onChange={(evento) => cambiarFiltro(() => setCompania(evento.target.value))}
                >
                  <option value="">Todas</option>
                  {companias.map((opcion) => <option key={opcion} value={opcion}>{opcion}</option>)}
                </select>
              </label>
            ) : null}
            {columnaNaturaleza ? (
              <label className="campo">
                <span>Naturaleza</span>
                <select
                  className="campo__control"
                  value={naturaleza}
                  onChange={(evento) => cambiarFiltro(() => setNaturaleza(evento.target.value))}
                >
                  <option value="">Todas</option>
                  {naturalezas.map((opcion) => <option key={opcion} value={opcion}>{opcion}</option>)}
                </select>
              </label>
            ) : null}
            {filtrosAntiguedad.length > 0 ? (
              <label className="campo">
                <span>Antigüedad vencida</span>
                <select
                  className="campo__control"
                  value={rangoAntiguedad}
                  onChange={(evento) => cambiarFiltro(() => setRangoAntiguedad(evento.target.value))}
                >
                  <option value="">Todos los rangos</option>
                  {filtrosAntiguedad.map((rango) => (
                    <option key={rango.valor} value={rango.valor}>{rango.etiqueta}</option>
                  ))}
                </select>
              </label>
            ) : null}
            <label className="campo">
              <span>Buscar</span>
              <input
                className="campo__control"
                type="search"
                placeholder="Cliente, NIT o sucursal…"
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
        {consulta.isLoading ? <Cargando texto="Consultando saldos CxC en SIESA…" /> : null}
        {!consulta.isLoading && consulta.data && filas.length === 0 ? (
          <Vacio titulo="Sin saldos CxC" detalle="SIESA no devolvió clientes para las compañías consultadas." />
        ) : null}
        {!consulta.isLoading && consulta.data && filas.length > 0 && filasFiltradas.length === 0 ? (
          <Vacio titulo="Sin coincidencias" detalle="Ajusta la compañía, naturaleza o búsqueda." />
        ) : null}
        {!consulta.isLoading && consulta.data && filasFiltradas.length > 0 ? (
          <>
            <div className="tabla-envoltorio tabla-envoltorio--alta">
              <table className="tabla tabla--anclada" aria-busy={consulta.isFetching}>
                <caption className="solo-lectores">
                  Saldos y antigüedad de cuentas por cobrar a clientes al {consulta.data.fecha_corte}.
                </caption>
                <thead>
                  <tr>
                    {columnas.map((columna, indice) => (
                      <th key={`${indice}-${columna}`} scope="col" className={indice === 0 ? "columna-ancla" : undefined}>
                        {etiquetaColumna(columna)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {filasPagina.map((fila, indice) => (
                    <tr key={`${inicio + indice}-${Object.values(fila).slice(0, 3).join("-")}`}>
                      {columnas.map((columna, indiceColumna) => (
                        <td
                          key={`${indiceColumna}-${columna}`}
                          className={esImporte(columna) ? "numero" : undefined}
                        >
                          {valorCelda(columna, fila[columna])}
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