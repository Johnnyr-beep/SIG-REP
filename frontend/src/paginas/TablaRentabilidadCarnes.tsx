import { useState } from "react";

import type {
  FilaCategoriaCarnes,
  FilaCompaniaCarnes,
  FilaMetricasCarnes,
  FilaProductoCarnes,
  RespuestaRentabilidadCarnes,
} from "@/api/tipos";

interface NodoCarnes {
  clave: string;
  fila: FilaMetricasCarnes;
  nivel: number;
  hijos: NodoCarnes[];
}

type CampoOrdenCarnes =
  | "kilos"
  | "venta"
  | "margen_bruto"
  | "rentabilidad"
  | "costo_unitario_promedio";

interface OrdenCarnes {
  campo: CampoOrdenCarnes;
  direccion: "desc" | "asc";
}

function construirArbol(companias: FilaCompaniaCarnes[]): NodoCarnes[] {
  return companias.map((compania) => ({
    clave: `cia:${compania.compania}`,
    fila: { ...compania, etiqueta: `${compania.compania} · ${compania.etiqueta}` },
    nivel: 0,
    hijos: compania.categorias.map((categoria: FilaCategoriaCarnes) => ({
      clave: `cia:${compania.compania}:categoria:${categoria.etiqueta}`,
      fila: categoria,
      nivel: 1,
      hijos: categoria.productos.map((producto: FilaProductoCarnes) => ({
        clave: `cia:${compania.compania}:categoria:${categoria.etiqueta}:producto:${producto.etiqueta}`,
        fila: producto,
        nivel: 2,
        hijos: [],
      })),
    })),
  }));
}

function ordenarArbol(nodos: NodoCarnes[], orden: OrdenCarnes | null): NodoCarnes[] {
  if (orden === null) return nodos;

  return [...nodos]
    .sort((primero, segundo) => {
      const valorPrimero = primero.fila[orden.campo];
      const valorSegundo = segundo.fila[orden.campo];
      if (valorPrimero === null || valorSegundo === null) {
        if (valorPrimero === valorSegundo) return primero.fila.etiqueta.localeCompare(segundo.fila.etiqueta, "es-CO", { numeric: true });
        return valorPrimero === null ? 1 : -1;
      }

      const diferencia = Number(valorPrimero) - Number(valorSegundo);
      if (diferencia === 0) return primero.fila.etiqueta.localeCompare(segundo.fila.etiqueta, "es-CO", { numeric: true });
      return orden.direccion === "desc" ? -diferencia : diferencia;
    })
    .map((nodo) => ({ ...nodo, hijos: ordenarArbol(nodo.hijos, orden) }));
}

function EncabezadoOrdenableCarnes({
  etiqueta,
  campo,
  orden,
  alOrdenar,
}: {
  etiqueta: string;
  campo: CampoOrdenCarnes;
  orden: OrdenCarnes | null;
  alOrdenar: (campo: CampoOrdenCarnes) => void;
}) {
  const direccion = orden?.campo === campo ? orden.direccion : null;
  const siguiente = direccion === "desc" ? "asc" : "desc";
  return (
    <th className="numero" aria-sort={direccion === "desc" ? "descending" : direccion === "asc" ? "ascending" : "none"}>
      <button
        type="button"
        className="rentabilidad-mes__orden-total"
        aria-label={`Ordenar ${etiqueta} de ${siguiente === "desc" ? "mayor a menor" : "menor a mayor"}`}
        onClick={() => alOrdenar(campo)}
      >
        {etiqueta}<span aria-hidden="true">{direccion === "desc" ? "↓" : direccion === "asc" ? "↑" : "↕"}</span>
      </button>
    </th>
  );
}

function formatear(valor: string | null, decimales = 2): string {
  if (valor === null) return "—";
  return new Intl.NumberFormat("es-CO", { maximumFractionDigits: decimales }).format(Number(valor));
}

function formatearMillones(valor: string | null): string {
  if (valor === null) return "—";
  return `$ ${new Intl.NumberFormat("es-CO", { maximumFractionDigits: 2 }).format(Number(valor) / 1_000_000)}`;
}

function porcentaje(valor: string | null): string {
  return valor === null ? "—" : `${formatear(String(Number(valor) * 100), 1)} %`;
}

function SemaforoRentabilidadCarnes({ valor }: { valor: string | null }) {
  const rentabilidad = valor === null ? null : Number(valor);
  const negativa = rentabilidad !== null && rentabilidad < 0;
  const estado = rentabilidad === null ? "neutro" : negativa ? "rojo" : "verde";
  const etiqueta =
    rentabilidad === null
      ? "Costo incompleto; rentabilidad no calculada"
      : negativa
        ? `Rentabilidad negativa: ${porcentaje(valor)}`
        : `Rentabilidad no negativa: ${porcentaje(valor)}`;

  return (
    <span
      className={`rentabilidad-mes__semaforo rentabilidad-mes__semaforo--${estado}`}
      role="img"
      aria-label={etiqueta}
      title={etiqueta}
    >
      <span aria-hidden="true">{rentabilidad === null ? "○" : negativa ? "×" : "✓"}</span>
    </span>
  );
}

export function TablaRentabilidadCarnes({
  datos,
  modo,
}: {
  datos: RespuestaRentabilidadCarnes;
  modo: "dia" | "mes";
}) {
  const [abiertas, setAbiertas] = useState<Set<string>>(() => new Set());
  const [orden, setOrden] = useState<OrdenCarnes | null>(null);
  const arbol = ordenarArbol(construirArbol(datos.detalle_companias), orden);
  const visibles: NodoCarnes[] = [];

  function agregarVisibles(nodos: NodoCarnes[]) {
    for (const nodo of nodos) {
      visibles.push(nodo);
      if (abiertas.has(nodo.clave)) agregarVisibles(nodo.hijos);
    }
  }

  function alternar(clave: string) {
    setAbiertas((actuales) => {
      const nuevas = new Set(actuales);
      if (nuevas.has(clave)) nuevas.delete(clave);
      else nuevas.add(clave);
      return nuevas;
    });
  }

  function alternarOrden(campo: CampoOrdenCarnes) {
    setOrden((actual) => ({
      campo,
      direccion: actual?.campo === campo && actual.direccion === "desc" ? "asc" : "desc",
    }));
  }

  agregarVisibles(arbol);

  return (
    <section className="rentabilidad-mes__panel">
      <h2 className="rentabilidad-mes__titulo-panel">
        {modo === "dia" ? "Facturación Carnes por día" : "Rentabilidad Carnes por compañía"}
      </h2>
      <p className="rentabilidad-mes__descripcion-grafico">
        Consolidado de 4, 6 y 7; detalle expandible por compañía, categoría y producto.
      </p>
      <div className="tabla-envoltorio rentabilidad-mes__envoltorio-metricas">
        <table className={`tabla tabla--compacta rentabilidad-mes__tabla rentabilidad-carnes__tabla rentabilidad-carnes__tabla--${modo}${modo === "dia" ? " rentabilidad-dia__tabla" : ""}`}>
          <thead>
            <tr>
              <th>Compañía / categoría / producto</th>
              {modo === "mes" ? (
                <>
                  <EncabezadoOrdenableCarnes etiqueta="Q (KG)" campo="kilos" orden={orden} alOrdenar={alternarOrden} />
                  <EncabezadoOrdenableCarnes etiqueta="Ingresos" campo="venta" orden={orden} alOrdenar={alternarOrden} />
                  <EncabezadoOrdenableCarnes etiqueta="UT." campo="margen_bruto" orden={orden} alOrdenar={alternarOrden} />
                  <th aria-label="Estado de rentabilidad" />
                  <EncabezadoOrdenableCarnes etiqueta="% Rent." campo="rentabilidad" orden={orden} alOrdenar={alternarOrden} />
                  <EncabezadoOrdenableCarnes etiqueta="Costo unit. prom." campo="costo_unitario_promedio" orden={orden} alOrdenar={alternarOrden} />
                </>
              ) : datos.fechas.map((fecha) => (
                <th className="numero" key={fecha} title={fecha}>{fecha.slice(8, 10)}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visibles.map((nodo) => {
              const tieneHijos = nodo.hijos.length > 0;
              const abierta = abiertas.has(nodo.clave);
              return (
                <tr
                  className={nodo.nivel === 0 ? "rentabilidad-mes__grupo" : nodo.nivel === 1 ? "rentabilidad-mes__grupo-centro" : "rentabilidad-mes__producto"}
                  key={nodo.clave}
                >
                  <th scope="row" className={nodo.nivel > 0 ? "rentabilidad-mes__subfila" : undefined}>
                    {tieneHijos ? (
                      <button type="button" aria-expanded={abierta} onClick={() => alternar(nodo.clave)}>
                        <span aria-hidden="true">{abierta ? "⊟" : "⊞"}</span>{nodo.fila.etiqueta}
                      </button>
                    ) : <span>{nodo.fila.etiqueta}</span>}
                  </th>
                  {modo === "mes" ? (
                    <>
                      <td className="numero">{formatear(nodo.fila.kilos)}</td>
                      <td className="numero">{formatearMillones(nodo.fila.venta)}</td>
                      <td className="numero">{formatearMillones(nodo.fila.margen_bruto)}</td>
                      <td className="rentabilidad-mes__celda-semaforo">
                        <SemaforoRentabilidadCarnes valor={nodo.fila.rentabilidad} />
                      </td>
                      <td className="numero">{porcentaje(nodo.fila.rentabilidad)}</td>
                      <td className="numero">{formatear(nodo.fila.costo_unitario_promedio)}</td>
                    </>
                  ) : datos.fechas.map((_, indice) => (
                    <td className="numero" key={`${nodo.clave}:${indice}`}>
                      {formatearMillones(nodo.fila.ventas_por_dia[indice] ?? "0")}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
          {modo === "mes" ? (
            <tfoot>
              <tr>
                <th scope="row">Total Carnes</th>
                <td className="numero">{formatear(datos.kilos)}</td>
                <td className="numero">{formatearMillones(datos.venta)}</td>
                <td className="numero">{formatearMillones(datos.margen_bruto)}</td>
                <td className="rentabilidad-mes__celda-semaforo">
                  <SemaforoRentabilidadCarnes valor={datos.rentabilidad} />
                </td>
                <td className="numero">{porcentaje(datos.rentabilidad)}</td>
                <td className="numero">{formatear(datos.costo_unitario_promedio)}</td>
              </tr>
            </tfoot>
          ) : (
            <tfoot>
              <tr>
                <th scope="row">Total Carnes</th>
                {datos.diario.map((punto) => (
                  <td className="numero" key={punto.fecha}>{formatearMillones(punto.venta)}</td>
                ))}
              </tr>
            </tfoot>
          )}
        </table>
      </div>
    </section>
  );
}
