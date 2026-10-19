import { useMemo, useState } from "react";

import { useCxpProveedores } from "@/api/consultasFinanciero";
import { AvisoError, Cargando, Tarjeta, Vacio } from "@/componentes/comunes";

const FILAS_POR_PAGINA = 50;
const RANGOS_VENCIDOS = [
  { desde: 0, hasta: 10, etiqueta: "0–10 días vencidos" },
  { desde: 11, hasta: 20, etiqueta: "11–20 días vencidos" },
  { desde: 21, hasta: 30, etiqueta: "21–30 días vencidos" },
  { desde: 31, hasta: 60, etiqueta: "31–60 días vencidos" },
  { desde: 61, hasta: 90, etiqueta: "61–90 días vencidos" },
  { desde: 91, hasta: 9999, etiqueta: "91–9999 días vencidos" },
];

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
    co: "Centro de operación",
    descco: "Centro de operación",
    centrooperacion: "Centro de operación",
    unidadnegocio: "Unidad de negocio",
    feproveedor: "F.E. proveedor",
    descfeproveedor: "Descripción F.E. proveedor",
    desctipoproveedor: "Descripción tipo proveedor",
    auxiliar: "Auxiliar",
    naturaleza: "Naturaleza",
    proveedor: "Proveedor",
    descproveedor: "Proveedor",
    razonsocial: "Razón social",
    razonsocialsucursal: "Razón social sucursal",
    nit: "NIT",
    tercero: "Tercero",
    sucursal: "Sucursal",
    documento: "Documento",
    fechacorte: "Fecha de corte",
    fechavencimiento: "Fecha de vencimiento",
    total: "Total",
    totalcorriente: "Total corriente",
    totalvencido: "Total vencido",
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

function numeroDiaUtc(año: number, mes: number, dia: number): number | null {
  const marca = Date.UTC(año, mes - 1, dia);
  const fecha = new Date(marca);
  if (
    fecha.getUTCFullYear() !== año ||
    fecha.getUTCMonth() !== mes - 1 ||
    fecha.getUTCDate() !== dia
  ) {
    return null;
  }
  return marca;
}

function fechaComoDiaUtc(valor: string): number | null {
  const iso = /^(\d{4})[-/](\d{1,2})[-/](\d{1,2})/.exec(valor.trim());
  if (iso) return numeroDiaUtc(Number(iso[1]), Number(iso[2]), Number(iso[3]));

  const local = /^(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})$/.exec(valor.trim());
  if (local) return numeroDiaUtc(Number(local[3]), Number(local[2]), Number(local[1]));
  return null;
}

function diasVencidosDeFila(
  fila: Record<string, string | null>,
  columnaDiasVencidos: string | undefined,
  columnaFechaVencimiento: string | undefined,
  fechaCorte: string,
): number | null {
  if (columnaDiasVencidos) {
    const valor = fila[columnaDiasVencidos];
    if (valor === null || valor === undefined || valor.trim() === "") return null;
    const dias = Number(valor.replace(",", "."));
    return Number.isFinite(dias) ? Math.trunc(dias) : null;
  }

  if (!columnaFechaVencimiento || !fila[columnaFechaVencimiento]) return null;
  const vencimiento = fechaComoDiaUtc(fila[columnaFechaVencimiento]);
  const corte = fechaComoDiaUtc(fechaCorte);
  if (vencimiento === null || corte === null) return null;
  return Math.floor((corte - vencimiento) / 86_400_000);
}

export function CxpProveedores() {
  const [fechaCorte, setFechaCorte] = useState(fechaLocal);
  const [compania, setCompania] = useState("");
  const [naturaleza, setNaturaleza] = useState("");
  const [rangoVencido, setRangoVencido] = useState("");
  const [busqueda, setBusqueda] = useState("");
  const [pagina, setPagina] = useState(1);
  const consulta = useCxpProveedores(fechaCorte);

  const columnas = consulta.data?.columnas ?? [];
  const filas = consulta.data?.filas ?? [];
  const columnaCompania = columnas.find((columna) => ["cia", "compania"].includes(normalizar(columna)));
  const columnaNaturaleza = columnas.find((columna) => normalizar(columna) === "naturaleza");
  const columnaDiasVencidos = columnas.find((columna) =>
    ["diasvencidos", "diasvencido", "diasdemora", "diasmora", "diasdeatraso"].includes(normalizar(columna)),
  );
  const columnaFechaVencimiento = columnas.find((columna) =>
    ["fechavencimiento", "fechavencida", "fechaexigibilidad", "fechavence"].includes(normalizar(columna)),
  );
  const fechaCorteEfectiva = consulta.data?.fecha_corte ?? fechaCorte;
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
      if (rangoVencido) {
        const rango = RANGOS_VENCIDOS.find(({ etiqueta }) => etiqueta === rangoVencido);
        const dias = diasVencidosDeFila(
          fila,
          columnaDiasVencidos,
          columnaFechaVencimiento,
          fechaCorteEfectiva,
        );
        if (!rango || dias === null || dias < rango.desde || dias > rango.hasta) return false;
      }
      return !termino || textoFila(fila).includes(termino);
    });
  }, [
    busqueda,
    compania,
    columnaCompania,
    columnaDiasVencidos,
    columnaFechaVencimiento,
    columnaNaturaleza,
    fechaCorteEfectiva,
    filas,
    naturaleza,
    rangoVencido,
  ]);

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
        titulo="CXP proveedores"
        descripcion="Saldos por proveedor, sucursal, centro de operación y unidad de negocio. Los totales corriente y vencido se calculan a la fecha de corte."
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
            {columnaDiasVencidos || columnaFechaVencimiento ? (
              <label className="campo">
                <span>Días vencidos</span>
                <select
                  className="campo__control"
                  value={rangoVencido}
                  onChange={(evento) => cambiarFiltro(() => setRangoVencido(evento.target.value))}
                >
                  <option value="">Todos</option>
                  {RANGOS_VENCIDOS.map((rango) => (
                    <option key={rango.etiqueta} value={rango.etiqueta}>{rango.etiqueta}</option>
                  ))}
                </select>
              </label>
            ) : null}
            <label className="campo">
              <span>Buscar</span>
              <input
                className="campo__control"
                type="search"
                placeholder="Proveedor, razón social o auxiliar…"
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
        {consulta.isLoading ? <Cargando texto="Consultando saldos CXP en SIESA…" /> : null}
        {!consulta.isLoading && consulta.data && filas.length === 0 ? (
          <Vacio titulo="Sin saldos CXP" detalle="SIESA no devolvió proveedores para las compañías consultadas." />
        ) : null}
        {!consulta.isLoading && consulta.data && filas.length > 0 && filasFiltradas.length === 0 ? (
          <Vacio titulo="Sin coincidencias" detalle="Ajusta la compañía o el texto de búsqueda." />
        ) : null}
        {!consulta.isLoading && consulta.data && filasFiltradas.length > 0 ? (
          <>
            <div className="tabla-envoltorio tabla-envoltorio--alta">
              <table className="tabla tabla--anclada" aria-busy={consulta.isFetching}>
                <caption className="solo-lectores">
                  Saldos de cuentas por pagar a proveedores al {consulta.data.fecha_corte}.
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
                          className={/saldo|total|corriente|vencid|valor|importe/i.test(normalizar(columna)) ? "numero" : undefined}
                        >
                          {fila[columna] ?? "—"}
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