import { useState } from "react";

import { useRentabilidadDia } from "@/api/consultasFinanciero";
import type { FilaGrupoRentabilidadDia, FilaMatrizRentabilidadDia } from "@/api/tipos";
import { AvisoError, Cargando, Vacio } from "@/componentes/comunes";
import { useMarcaElegida } from "@/marca/ContextoMarca";

import { BarrasVentaDiaria, LineaRentabilidadDiaria } from "./RentabilidadMes";

interface FilaMatrizArbol {
  fila: FilaMatrizRentabilidadDia;
  clave: string;
  nivel: number;
  hijos?: FilaMatrizArbol[];
}

function filasDeBienes(especies: FilaGrupoRentabilidadDia[]): FilaMatrizArbol[] {
  return especies.map((especie) => ({
    fila: especie,
    clave: `especie:${especie.etiqueta}`,
    nivel: 0,
    hijos: especie.detalle.map((comercial) => ({
      fila: comercial,
      clave: `comercial:${especie.etiqueta}:${comercial.etiqueta}`,
      nivel: 1,
      hijos: comercial.productos.map((producto) => ({
        fila: producto,
        clave: `producto:${especie.etiqueta}:${comercial.etiqueta}:${producto.etiqueta}`,
        nivel: 2,
      })),
    })),
  }));
}

function periodoActual(): string {
  const ahora = new Date();
  return `${ahora.getFullYear()}-${String(ahora.getMonth() + 1).padStart(2, "0")}`;
}

function aPeriodoApi(periodo: string): string {
  return periodo.replace("-", "");
}

function millones(valor: string | null): string {
  if (valor === null) return "—";
  return `$ ${new Intl.NumberFormat("es-CO", { maximumFractionDigits: 3 }).format(Number(valor) / 1_000_000)} mill.`;
}

function millonesTabla(valor: string): string {
  return `$ ${new Intl.NumberFormat("es-CO", { maximumFractionDigits: 2 }).format(Number(valor) / 1_000_000)}`;
}

function porcentaje(valor: string | null): string {
  if (valor === null) return "—";
  return `${new Intl.NumberFormat("es-CO", { maximumFractionDigits: 1 }).format(Number(valor) * 100)} %`;
}

function cantidad(valor: string): string {
  return new Intl.NumberFormat("es-CO", { maximumFractionDigits: 0 }).format(Number(valor));
}

function costoKilo(valor: string | null): string {
  if (valor === null) return "—";
  return `$ ${new Intl.NumberFormat("es-CO", { maximumFractionDigits: 1 }).format(Number(valor))}`;
}

function TablaMatriz({
  titulo,
  filas,
  dias,
  total,
  valoresTotal,
  encabezado,
  filasJerarquicas = false,
}: {
  titulo: string;
  filas: FilaMatrizArbol[];
  dias: number[];
  total: string;
  valoresTotal?: string[];
  encabezado: string;
  filasJerarquicas?: boolean;
}) {
  const [abiertas, setAbiertas] = useState<Set<string>>(() => new Set());
  const visibles: FilaMatrizArbol[] = [];
  const agregarVisibles = (filasAnidadas: FilaMatrizArbol[]) => {
    for (const fila of filasAnidadas) {
      visibles.push(fila);
      if (fila.hijos?.length && abiertas.has(fila.clave)) agregarVisibles(fila.hijos);
    }
  };
  agregarVisibles(filas);

  function alternar(clave: string) {
    setAbiertas((actuales) => {
      const nuevas = new Set(actuales);
      if (nuevas.has(clave)) nuevas.delete(clave);
      else nuevas.add(clave);
      return nuevas;
    });
  }

  return (
    <section className="rentabilidad-mes__panel">
      <h2 className="rentabilidad-mes__titulo-panel">{titulo}</h2>
      <div className="tabla-envoltorio rentabilidad-dia__envoltorio">
        <table className="tabla tabla--compacta rentabilidad-mes__tabla rentabilidad-dia__tabla">
          <thead>
            <tr>
              <th scope="col">{encabezado}</th>
              <th scope="col" className="numero">Total</th>
              {dias.map((dia) => <th className="numero" scope="col" key={dia}>{dia}</th>)}
            </tr>
          </thead>
          <tbody>
            {visibles.map((fila) => (
              <tr className={`rentabilidad-dia__nivel-${fila.nivel}`} key={fila.clave}>
                <th scope="row">
                  {filasJerarquicas && fila.hijos?.length ? (
                    <button
                      type="button"
                      aria-expanded={abiertas.has(fila.clave)}
                      aria-label={`${abiertas.has(fila.clave) ? "Ocultar" : "Mostrar"} detalle de ${fila.fila.etiqueta}`}
                      onClick={() => alternar(fila.clave)}
                    >
                      <span aria-hidden="true">{abiertas.has(fila.clave) ? "⊟" : "⊞"}</span>
                      {fila.fila.etiqueta}
                    </button>
                  ) : fila.fila.etiqueta}
                </th>
                <td className="numero">{millonesTabla(fila.fila.venta)}</td>
                {dias.map((_, indice) => (
                  <td className="numero" key={`${fila.clave}-${indice}`}>
                    {millonesTabla(fila.fila.valores[indice] ?? "0")}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <th scope="row">Total</th>
              <td className="numero">{millonesTabla(total)}</td>
              {dias.map((_, indice) => (
                <td className="numero" key={`total-${indice}`}>
                  {millonesTabla(
                    valoresTotal?.[indice] ??
                      filas.reduce(
                        (suma, fila) => suma + Number(fila.fila.valores[indice] ?? 0),
                        0,
                      ).toString(),
                  )}
                </td>
              ))}
            </tr>
          </tfoot>
        </table>
      </div>
    </section>
  );
}

export function RentabilidadDia() {
  const marca = useMarcaElegida();
  const [periodo, setPeriodo] = useState(periodoActual);
  const consulta = useRentabilidadDia(aPeriodoApi(periodo));
  const datos = consulta.data;
  const dias = datos?.diario.map((punto) => Number(punto.fecha.slice(8, 10))) ?? [];
  const valoresBienes = datos?.diario.map((_, indice) =>
    datos.especies_bienes.reduce(
      (suma, especie) => suma + Number(especie.valores[indice] ?? 0),
      0,
    ).toString(),
  ) ?? [];
  const totalBienes = datos?.especies_bienes.reduce((suma, especie) => suma + Number(especie.venta), 0).toString() ?? "0";

  return (
    <main className="rentabilidad-mes rentabilidad-dia">
      <header className="rentabilidad-mes__cabecera">
        <div className="rentabilidad-mes__marca">
          <img src={marca.logo} alt="" />
          <h1>VENTA - RENTABILIDAD DÍA</h1>
        </div>
        <label className="campo rentabilidad-mes__periodo">
          <span>Mes</span>
          <input
            className="campo__control"
            type="month"
            value={periodo}
            onChange={(evento) => setPeriodo(evento.target.value)}
          />
        </label>
      </header>

      <AvisoError error={consulta.error} />
      {consulta.isLoading ? <Cargando texto="Consultando rentabilidad diaria…" /> : null}
      {datos && datos.lineas_facturadas === 0 ? (
        <Vacio titulo="Sin facturas para este mes" detalle="SIESA no devolvió líneas comerciales en el período elegido." />
      ) : null}

      {datos && datos.lineas_facturadas > 0 ? (
        <>
          <section className="rentabilidad-mes__indicadores" aria-label="Indicadores del mes">
            <article className="rentabilidad-mes__indicador rentabilidad-mes__indicador--venta">
              <strong>{millones(datos.venta)}</strong>
              <span>Vlr Facturado</span>
            </article>
            <article className="rentabilidad-mes__indicador rentabilidad-mes__indicador--rentabilidad">
              <strong>{porcentaje(datos.rentabilidad)}</strong>
              <span>%Rent</span>
            </article>
          </section>

          <section className="rentabilidad-mes__especies" aria-label="Indicadores por especie">
            <article className="rentabilidad-mes__especie-resumen">
              <strong>{cantidad(datos.canal_cerdo)}</strong>
              <span>CANALES CERDO</span>
              <small><strong>{costoKilo(datos.costo_kg_cerdo)}</strong><span>Costo_KG_PROM</span></small>
            </article>
            <article className="rentabilidad-mes__especie-resumen">
              <strong>{cantidad(datos.canal_res)}</strong>
              <span>CANALES RES</span>
              <small><strong>{costoKilo(datos.costo_kg_res)}</strong><span>Costo_KG_PROM</span></small>
            </article>
          </section>

          <section className="rentabilidad-mes__graficos-diarios" aria-label="Evolución diaria">
            <div className="rentabilidad-mes__grafico-diario">
              <h2 className="rentabilidad-mes__titulo-panel">Rentabilidad diaria</h2>
              <LineaRentabilidadDiaria puntos={datos.diario} />
            </div>
            <div className="rentabilidad-mes__grafico-diario">
              <h2 className="rentabilidad-mes__titulo-panel">Venta diaria</h2>
              <BarrasVentaDiaria puntos={datos.diario} />
            </div>
          </section>

          <TablaMatriz
            titulo="Total Fact Agropecuaria"
            filas={filasDeBienes(datos.especies_bienes)}
            dias={dias}
            total={totalBienes}
            valoresTotal={valoresBienes}
            encabezado="Especie / tipo comercial"
            filasJerarquicas
          />
          <TablaMatriz
            titulo="Facturación BIENES"
            filas={datos.vendedores_clases.map((fila) => ({
              fila,
              clave: `clase:${fila.etiqueta}`,
              nivel: 0,
            }))}
            dias={dias}
            total={totalBienes}
            valoresTotal={valoresBienes}
            encabezado="Clase vendedor"
          />
        </>
      ) : null}
    </main>
  );
}