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
  const arbol = construirArbol(datos.detalle_companias);
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
        <table className={`tabla tabla--compacta rentabilidad-mes__tabla rentabilidad-carnes__tabla rentabilidad-carnes__tabla--${modo}`}>
          <thead>
            <tr>
              <th>Compañía / categoría / producto</th>
              {modo === "mes" ? (
                <>
                  <th className="numero">Q (KG)</th>
                  <th className="numero">Ingresos</th>
                  <th className="numero">UT.</th>
                  <th aria-label="Estado de rentabilidad" />
                  <th className="numero">% Rent.</th>
                  <th className="numero">Costo unit. prom.</th>
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
