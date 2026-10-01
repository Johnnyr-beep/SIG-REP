import { useState } from "react";

import { useRentabilidadMes } from "@/api/consultasFinanciero";
import type { FilaRentabilidadMes, PuntoRentabilidadMes } from "@/api/tipos";
import { AvisoError, Cargando, Tarjeta, Vacio } from "@/componentes/comunes";
import { BarrasRanking, ColumnasComparadas } from "@/componentes/graficos";
import type { FilaRanking } from "@/componentes/graficos";

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

function porcentaje(valor: string | null): string {
  if (valor === null) return "—";
  return `${new Intl.NumberFormat("es-CO", { maximumFractionDigits: 1 }).format(Number(valor) * 100)} %`;
}

function cantidad(valor: string): string {
  return new Intl.NumberFormat("es-CO", { maximumFractionDigits: 0 }).format(Number(valor));
}

function filaRanking(fila: FilaRentabilidadMes): FilaRanking {
  return {
    clave: fila.etiqueta,
    etiqueta: fila.etiqueta,
    valor: fila.venta,
    participacion: fila.participacion,
  };
}

function LineaRentabilidadDiaria({ puntos }: { puntos: PuntoRentabilidadMes[] }) {
  const ancho = 640;
  const alto = 190;
  const margen = { arriba: 16, derecha: 12, abajo: 28, izquierda: 38 };
  const valores = puntos.map((punto) =>
    punto.rentabilidad === null ? null : Number(punto.rentabilidad) * 100,
  );
  const disponibles = valores.filter((valor): valor is number => valor !== null);

  if (disponibles.length === 0) {
    return <p className="tenue">Sin costo completo para calcular la rentabilidad diaria.</p>;
  }

  const minimo = Math.min(0, ...disponibles);
  const maximo = Math.max(10, ...disponibles);
  const rango = maximo - minimo || 1;
  const util = {
    ancho: ancho - margen.izquierda - margen.derecha,
    alto: alto - margen.arriba - margen.abajo,
  };
  const x = (indice: number) =>
    margen.izquierda + (puntos.length <= 1 ? util.ancho / 2 : (indice / (puntos.length - 1)) * util.ancho);
  const y = (valor: number) => margen.arriba + ((maximo - valor) / rango) * util.alto;
  const segmentos: string[][] = [];
  let segmento: string[] = [];
  valores.forEach((valor, indice) => {
    if (valor === null) {
      if (segmento.length) segmentos.push(segmento);
      segmento = [];
      return;
    }
    segmento.push(`${x(indice)},${y(valor)}`);
  });
  if (segmento.length) segmentos.push(segmento);

  const marcas = [0, Math.floor((puntos.length - 1) / 2), Math.max(0, puntos.length - 1)];
  const resumen = disponibles.map((valor) => `${valor.toFixed(1)} %`).join(", ");

  return (
    <figure className="rentabilidad-mes__linea">
      <svg
        viewBox={`0 0 ${ancho} ${alto}`}
        className="rentabilidad-mes__linea-svg"
        role="img"
        aria-label={`Rentabilidad diaria porcentual. Valores disponibles: ${resumen}.`}
      >
        {[0, 0.5, 1].map((fraccion) => {
          const valor = minimo + rango * fraccion;
          const posicion = y(valor);
          return (
            <g key={fraccion}>
              <line
                x1={margen.izquierda}
                x2={ancho - margen.derecha}
                y1={posicion}
                y2={posicion}
                className="rentabilidad-mes__guia"
              />
              <text x={margen.izquierda - 6} y={posicion + 4} textAnchor="end" className="rentabilidad-mes__eje">
                {valor.toFixed(0)}%
              </text>
            </g>
          );
        })}
        {segmentos.map((segmentosLinea, indice) => (
          <polyline
            key={indice}
            points={segmentosLinea.join(" ")}
            className="rentabilidad-mes__trazo"
          />
        ))}
        {marcas.map((indice) => {
          const punto = puntos[indice];
          return punto ? (
            <text key={indice} x={x(indice)} y={alto - 7} textAnchor="middle" className="rentabilidad-mes__eje">
              {Number(punto.fecha.slice(8, 10))}
            </text>
          ) : null;
        })}
      </svg>
      <figcaption>Rentabilidad diaria (%)</figcaption>
    </figure>
  );
}

export function RentabilidadMes() {
  const [periodo, setPeriodo] = useState(periodoActual);
  const consulta = useRentabilidadMes(aPeriodoApi(periodo));
  const datos = consulta.data;

  return (
    <main className="rentabilidad-mes">
      <header className="rentabilidad-mes__cabecera">
        <div>
          <p className="rentabilidad-mes__eyebrow">AGROPECUARIA · CIA 3 · SIESA</p>
          <h2>Venta - Rentabilidad mes</h2>
          {datos ? <p className="tenue">Corte del {datos.fecha_inicio} al {datos.fecha_fin}.</p> : null}
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
      {consulta.isLoading ? <Cargando texto="Consultando rentabilidad mensual…" /> : null}
      {datos && datos.lineas_facturadas === 0 ? (
        <Vacio titulo="Sin facturas para este mes" detalle="SIESA no devolvió líneas comerciales en el período elegido." />
      ) : null}

      {datos && datos.lineas_facturadas > 0 ? (
        <>
          <section className="rentabilidad-mes__kpis" aria-label="Indicadores del mes">
            <article className="rentabilidad-mes__kpi rentabilidad-mes__kpi--venta">
              <span>Vlr. facturado</span>
              <strong>{millones(datos.venta)}</strong>
              <small>{cantidad(datos.kilos)} kg · {datos.lineas_facturadas.toLocaleString("es-CO")} líneas</small>
            </article>
            <article className="rentabilidad-mes__kpi">
              <span>Rentabilidad</span>
              <strong>{porcentaje(datos.rentabilidad)}</strong>
              <small>Margen bruto {millones(datos.margen_bruto)}</small>
            </article>
            <article className="rentabilidad-mes__kpi rentabilidad-mes__kpi--costo">
              <span>Costo</span>
              <strong>{millones(datos.costo)}</strong>
              <small>{datos.costo === null ? "Costo incompleto en la fuente" : "Facturación menos costo"}</small>
            </article>
            <article className="rentabilidad-mes__kpi">
              <span>Facturas</span>
              <strong>{cantidad(String(datos.lineas_facturadas))}</strong>
              <small>líneas facturadas, no documentos</small>
            </article>
          </section>

          <section className="rentabilidad-mes__estructura" aria-label="Detalle de venta y rentabilidad">
            <div className="rentabilidad-mes__columna">
              <Tarjeta titulo="Rentabilidad diaria" descripcion="Porcentaje calculado con el costo disponible de cada día.">
                <LineaRentabilidadDiaria puntos={datos.diario} />
              </Tarjeta>
              <Tarjeta titulo="Venta diaria" descripcion="Venta neta por fecha, en millones de pesos.">
                <ColumnasComparadas
                  columnas={datos.diario.map((punto) => ({
                    clave: punto.fecha,
                    etiqueta: String(Number(punto.fecha.slice(8, 10))),
                    valor: punto.venta,
                  }))}
                  titulo="Venta neta diaria"
                  formatear={millones}
                  etiquetaValor="Venta"
                  notaSinReferencia=""
                />
              </Tarjeta>
            </div>

            <div className="rentabilidad-mes__columna">
              <Tarjeta titulo="Total facturado por tipo de ítem" descripcion="Venta neta y rentabilidad ponderada.">
                <div className="tabla-envoltorio">
                  <table className="tabla rentabilidad-mes__tabla">
                    <thead><tr><th>Tipo ítem</th><th className="numero">Vlr_FactMM</th><th className="numero">%Rent</th></tr></thead>
                    <tbody>
                      {datos.tipos_item.map((fila) => (
                        <tr key={fila.etiqueta}>
                          <th scope="row">{fila.etiqueta}</th>
                          <td className="numero">{millones(fila.venta)}</td>
                          <td className="numero">{porcentaje(fila.rentabilidad)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Tarjeta>

              <Tarjeta titulo="Facturación bienes" descripcion="Venta neta por especie y tipo comercial.">
                <div className="tabla-envoltorio">
                  <table className="tabla rentabilidad-mes__tabla">
                    <thead><tr><th>Especie / tipo comercial</th><th className="numero">Vlr_FactMM</th><th className="numero">%Rent</th></tr></thead>
                    <tbody>
                      {datos.especies.filter((especie) => especie.comerciales.length > 0).flatMap((especie) => [
                        <tr key={`especie-${especie.etiqueta}`} className="rentabilidad-mes__grupo">
                          <th scope="row">{especie.etiqueta}</th>
                          <td className="numero">{millones(especie.venta)}</td>
                          <td className="numero">{porcentaje(especie.rentabilidad)}</td>
                        </tr>,
                        ...especie.comerciales.map((fila) => (
                          <tr key={`${especie.etiqueta}-${fila.etiqueta}`}>
                            <th scope="row" className="rentabilidad-mes__subfila">{fila.etiqueta}</th>
                            <td className="numero">{millones(fila.venta)}</td>
                            <td className="numero">{porcentaje(fila.rentabilidad)}</td>
                          </tr>
                        )),
                      ])}
                    </tbody>
                  </table>
                </div>
              </Tarjeta>
            </div>

            <div className="rentabilidad-mes__columna">
              <Tarjeta titulo="Ranking clientes" descripcion="Clientes con mayor venta neta del mes.">
                <BarrasRanking filas={datos.clientes.map(filaRanking)} titulo="Clientes por venta" formatear={millones} />
              </Tarjeta>
              <Tarjeta titulo="Ranking productos" descripcion="Productos con mayor venta neta del mes.">
                <BarrasRanking filas={datos.productos.map(filaRanking)} titulo="Productos por venta" formatear={millones} />
              </Tarjeta>
            </div>
          </section>
        </>
      ) : null}
    </main>
  );
}