import { Fragment, useState } from "react";

import { useRentabilidadMes } from "@/api/consultasFinanciero";
import type {
  FilaEspecieRentabilidadMes,
  FilaRentabilidadMes,
  FilaTipoItemRentabilidadMes,
  PuntoRentabilidadMes,
} from "@/api/tipos";
import { AvisoError, Cargando, Vacio } from "@/componentes/comunes";
import { useMarcaElegida } from "@/marca/ContextoMarca";

const LIMITE_RENTABILIDAD_AMARILLO = 0.2;
const LIMITE_RENTABILIDAD_VERDE = 0.8;

function periodoActual(): string {
  const ahora = new Date();
  return `${ahora.getFullYear()}-${String(ahora.getMonth() + 1).padStart(2, "0")}`;
}

function aPeriodoApi(periodo: string): string {
  return periodo.replace("-", "");
}

function millones(valor: string | null): string {
  if (valor === null) return "—";
  const monto = new Intl.NumberFormat("es-CO", { maximumFractionDigits: 3 }).format(
    Number(valor) / 1_000_000,
  );
  return `$ ${monto} mill.`;
}

function millonesTabla(valor: string | null): string {
  if (valor === null) return "—";
  const monto = new Intl.NumberFormat("es-CO", { maximumFractionDigits: 3 }).format(
    Number(valor) / 1_000_000,
  );
  return `$ ${monto}`;
}

function pesos(valor: number): string {
  return `$ ${new Intl.NumberFormat("es-CO", { maximumFractionDigits: 1 }).format(valor)}`;
}

function porcentaje(valor: string | null): string {
  if (valor === null) return "—";
  return `${new Intl.NumberFormat("es-CO", { maximumFractionDigits: 1 }).format(Number(valor) * 100)} %`;
}

function cantidad(valor: string): string {
  return new Intl.NumberFormat("es-CO", { maximumFractionDigits: 0 }).format(Number(valor));
}

function costoPorKilo(fila: FilaRentabilidadMes): string {
  const kilos = Number(fila.kilos);
  if (fila.costo === null || kilos === 0) return "—";
  return pesos(Number(fila.costo) / kilos);
}

function etiquetaEspecie(etiqueta: string): string {
  return etiqueta.replace(/^\d+\s*-\s*/, "").trim();
}

function especiesResumen(especies: FilaEspecieRentabilidadMes[]): FilaEspecieRentabilidadMes[] {
  const preferidas = ["CERDO", "RES"];
  const resumen = preferidas
    .map((nombre) =>
      especies.find((fila) =>
        etiquetaEspecie(fila.etiqueta).split(/[^A-Z0-9]+/).includes(nombre),
      ),
    )
    .filter((fila): fila is FilaEspecieRentabilidadMes => fila !== undefined);
  return resumen.length > 0 ? resumen : especies.slice(0, 2);
}

function SemaforoRentabilidad({ valor }: { valor: string | null }) {
  if (valor === null) {
    return (
      <span className="rentabilidad-mes__semaforo rentabilidad-mes__semaforo--neutro" role="img" aria-label="Rentabilidad no disponible">
        <span aria-hidden="true">○</span>
      </span>
    );
  }

  const rentabilidad = Number(valor);
  const estado =
    rentabilidad >= LIMITE_RENTABILIDAD_VERDE
      ? "verde"
      : rentabilidad >= LIMITE_RENTABILIDAD_AMARILLO
        ? "amarillo"
        : "rojo";
  const etiqueta =
    estado === "verde" ? "Rentabilidad alta" : estado === "amarillo" ? "Rentabilidad media" : "Rentabilidad baja";
  const simbolo = estado === "verde" ? "✓" : estado === "amarillo" ? "!" : "×";

  return (
    <span
      className={`rentabilidad-mes__semaforo rentabilidad-mes__semaforo--${estado}`}
      role="img"
      aria-label={etiqueta}
      title={`${etiqueta}: ${porcentaje(valor)}. Verde ≥ 80 %, amarillo ≥ 20 %, rojo < 20 %.`}
    >
      <span aria-hidden="true">{simbolo}</span>
    </span>
  );
}

function EstadoRentabilidadCalculada({ valor }: { valor: string | null }) {
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

export function LineaRentabilidadDiaria({ puntos }: { puntos: PuntoRentabilidadMes[] }) {
  const ancho = 420;
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
    margen.izquierda +
    (puntos.length <= 1 ? util.ancho / 2 : (indice / (puntos.length - 1)) * util.ancho);
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
  const baseY = y(0);
  const indiceMayor = valores.indexOf(Math.max(...disponibles));
  const indiceMenor = valores.indexOf(Math.min(...disponibles));
  const indicesPorcentaje = new Set([0, puntos.length - 1, indiceMayor, indiceMenor]);
  for (let indice = 4; indice < puntos.length - 1; indice += 5) {
    if (![...indicesPorcentaje].some((existente) => Math.abs(existente - indice) < 3)) {
      indicesPorcentaje.add(indice);
    }
  }

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
        {segmentos.map((puntosSegmento, indice) => {
          const primero = puntosSegmento[0]?.split(",")[0];
          const ultimo = puntosSegmento[puntosSegmento.length - 1]?.split(",")[0];
          if (primero === undefined || ultimo === undefined) return null;
          return (
            <polygon
              key={`area-${indice}`}
              points={`${primero},${baseY} ${puntosSegmento.join(" ")} ${ultimo},${baseY}`}
              className="rentabilidad-mes__area"
            />
          );
        })}
        {segmentos.map((puntosSegmento, indice) => (
          <polyline
            key={`linea-${indice}`}
            points={puntosSegmento.join(" ")}
            className="rentabilidad-mes__trazo"
          />
        ))}
        {Array.from(indicesPorcentaje).map((indice) => {
          const valor = valores[indice];
          if (valor === null || valor === undefined) return null;
          return (
            <text
              key={`porcentaje-${indice}`}
              x={x(indice)}
              y={Math.max(margen.arriba + 10, y(valor) - 7)}
              textAnchor="middle"
              className="rentabilidad-mes__valor-linea"
            >
              {`${new Intl.NumberFormat("es-CO", { maximumFractionDigits: 1 }).format(valor)} %`}
            </text>
          );
        })}
        {marcas.map((indice) => {
          const punto = puntos[indice];
          return punto ? (
            <text key={indice} x={x(indice)} y={alto - 7} textAnchor="middle" className="rentabilidad-mes__eje">
              {Number(punto.fecha.slice(8, 10))}
            </text>
          ) : null;
        })}
      </svg>
      <figcaption>Día</figcaption>
    </figure>
  );
}

export function BarrasVentaDiaria({ puntos }: { puntos: PuntoRentabilidadMes[] }) {
  const ancho = 420;
  const alto = 190;
  const margen = { arriba: 25, abajo: 28, horizontal: 9 };
  const valores = puntos.map((punto) => Number(punto.venta));
  const maximo = Math.max(...valores, 1) * 1.14;
  const util = ancho - margen.horizontal * 2;
  const paso = util / Math.max(puntos.length, 1);
  const anchoBarra = Math.max(3, paso * 0.62);
  const baseY = alto - margen.abajo;
  const x = (indice: number) => margen.horizontal + paso * indice + (paso - anchoBarra) / 2;
  const y = (valor: number) => margen.arriba + (1 - valor / maximo) * (baseY - margen.arriba);
  const indicesValor = new Set<number>();
  for (let inicio = 0; inicio < puntos.length; inicio += 6) {
    const fin = Math.min(inicio + 6, puntos.length);
    let mayor = inicio;
    for (let indice = inicio + 1; indice < fin; indice += 1) {
      const valor = valores[indice];
      const valorMayor = valores[mayor];
      if (valor !== undefined && valorMayor !== undefined && valor > valorMayor) mayor = indice;
    }
    indicesValor.add(mayor);
  }

  const valoresAccesibles = puntos
    .map((punto) => `${Number(punto.fecha.slice(8, 10))}: ${millones(punto.venta)}`)
    .join("; ");

  return (
    <figure className="rentabilidad-mes__barras">
      <svg
        viewBox={`0 0 ${ancho} ${alto}`}
        className="rentabilidad-mes__barras-svg"
        role="img"
        aria-label={`Venta diaria en millones de pesos. ${valoresAccesibles}.`}
      >
        {[0.25, 0.5, 0.75].map((fraccion) => {
          const posicion = margen.arriba + (baseY - margen.arriba) * fraccion;
          return (
            <line
              key={fraccion}
              x1={margen.horizontal}
              x2={ancho - margen.horizontal}
              y1={posicion}
              y2={posicion}
              className="rentabilidad-mes__guia"
            />
          );
        })}
        {puntos.map((punto, indice) => {
          const valor = valores[indice];
          if (valor === undefined) return null;
          const barraY = y(valor);
          const dia = Number(punto.fecha.slice(8, 10));
          const valorCorto = `$ ${new Intl.NumberFormat("es-CO", { maximumFractionDigits: 0 }).format(valor / 1_000_000)}`;
          return (
            <g key={punto.fecha}>
              <title>{`Día ${dia}: ${millones(punto.venta)}`}</title>
              <rect
                x={x(indice)}
                y={barraY}
                width={anchoBarra}
                height={Math.max(1, baseY - barraY)}
                rx="1.5"
                className="rentabilidad-mes__barra-venta"
              />
              <text
                x={x(indice) + anchoBarra / 2}
                y={alto - 7}
                textAnchor="middle"
                className="rentabilidad-mes__eje"
              >
                {dia}
              </text>
              {indicesValor.has(indice) ? (
                <text
                  x={x(indice) + anchoBarra / 2}
                  y={Math.max(11, barraY - 5)}
                  textAnchor="middle"
                  className="rentabilidad-mes__valor-barra"
                >
                  {valorCorto}
                </text>
              ) : null}
            </g>
          );
        })}
      </svg>
      <figcaption>Venta, en millones de pesos</figcaption>
    </figure>
  );
}

function TablaRanking({
  titulo,
  etiqueta,
  filas,
  totalVenta,
  totalRentabilidad,
  mostrarPosicion = false,
}: {
  titulo: string;
  etiqueta: string;
  filas: FilaRentabilidadMes[];
  totalVenta: string;
  totalRentabilidad: string | null;
  mostrarPosicion?: boolean;
}) {
  return (
    <section className="rentabilidad-mes__panel">
      <h2 className="rentabilidad-mes__titulo-panel">{titulo}</h2>
      <div className="tabla-envoltorio">
        <table className="tabla tabla--compacta rentabilidad-mes__tabla rentabilidad-mes__tabla--ranking">
          <thead>
            <tr>
              <th>{etiqueta}</th>
              {mostrarPosicion ? <th className="numero">Rnk $</th> : null}
              <th className="numero">Vlr_FactMM</th>
              <th className="numero">%Rent</th>
            </tr>
          </thead>
          <tbody>
            {filas.map((fila, indice) => (
              <tr key={fila.etiqueta}>
                <th scope="row">{fila.etiqueta}</th>
                {mostrarPosicion ? <td className="numero">{indice + 1}</td> : null}
                <td className="numero">{millones(fila.venta)}</td>
                <td className="numero">{porcentaje(fila.rentabilidad)}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <th scope="row">Total</th>
              {mostrarPosicion ? <td className="numero">—</td> : null}
              <td className="numero">{millones(totalVenta)}</td>
              <td className="numero">{porcentaje(totalRentabilidad)}</td>
            </tr>
          </tfoot>
        </table>
      </div>
    </section>
  );
}

export function RentabilidadMes() {
  const marca = useMarcaElegida();
  const [periodo, setPeriodo] = useState(periodoActual);
  const [gruposColapsados, setGruposColapsados] = useState<Set<string>>(() => new Set());
  const [comercialesExpandidos, setComercialesExpandidos] = useState<Set<string>>(() => new Set());
  const consulta = useRentabilidadMes(aPeriodoApi(periodo));
  const datos = consulta.data;

  function alternarGrupo(clave: string) {
    setGruposColapsados((actuales) => {
      const nuevos = new Set(actuales);
      if (nuevos.has(clave)) nuevos.delete(clave);
      else nuevos.add(clave);
      return nuevos;
    });
  }

  function alternarComercial(clave: string) {
    setComercialesExpandidos((actuales) => {
      const nuevos = new Set(actuales);
      if (nuevos.has(clave)) nuevos.delete(clave);
      else nuevos.add(clave);
      return nuevos;
    });
  }

  return (
    <main className="rentabilidad-mes">
      <header className="rentabilidad-mes__cabecera">
        <div className="rentabilidad-mes__marca">
          <img src={marca.logo} alt="" />
          <h1>VENTA - RENTABILIDAD MES</h1>
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
            {especiesResumen(datos.especies).map((fila) => {
              const especie = etiquetaEspecie(fila.etiqueta).toUpperCase();
              return (
                <article className="rentabilidad-mes__especie-resumen" key={fila.etiqueta}>
                  <strong>{cantidad(fila.kilos)}</strong>
                  <span>KILOS {especie}</span>
                  <small>
                    <strong>{costoPorKilo(fila)}</strong>
                    <span>Costo_KG_PROM</span>
                  </small>
                </article>
              );
            })}
          </section>

          <section className="rentabilidad-mes__graficos-diarios" aria-label="Evolución diaria">
            <div className="rentabilidad-mes__grafico-diario">
              <h2 className="rentabilidad-mes__titulo-panel">Rentabilidad diaria</h2>
              <p className="rentabilidad-mes__descripcion-grafico">Porcentaje calculado con el costo disponible de cada día.</p>
              <LineaRentabilidadDiaria puntos={datos.diario} />
            </div>
            <div className="rentabilidad-mes__grafico-diario">
              <h2 className="rentabilidad-mes__titulo-panel">Venta diaria</h2>
              <p className="rentabilidad-mes__descripcion-grafico">Facturación neta por día, en millones de pesos.</p>
              <BarrasVentaDiaria puntos={datos.diario} />
            </div>
          </section>

          <section className="rentabilidad-mes__estructura" aria-label="Venta y rentabilidad mensual">
          <div className="rentabilidad-mes__columna rentabilidad-mes__columna--centro">
            <section className="rentabilidad-mes__panel">
              <h2 className="rentabilidad-mes__titulo-panel">Total Fact Agropecuaria</h2>
              <div className="tabla-envoltorio">
                <table className="tabla tabla--compacta rentabilidad-mes__tabla">
                  <thead>
                    <tr><th>TIPO ITEM</th><th className="numero">Vlr_FactMM</th><th aria-label="Semáforo" /><th className="numero">%Rent</th></tr>
                  </thead>
                  <tbody>
                    {datos.tipos_item.map((fila) => {
                      const clave = `tipo:${fila.etiqueta}`;
                      const abierto = !gruposColapsados.has(clave);
                      return (
                        <FragmentoTipoItem
                          key={fila.etiqueta}
                          fila={fila}
                          abierto={abierto}
                          alAlternar={() => alternarGrupo(clave)}
                        />
                      );
                    })}
                  </tbody>
                  <tfoot>
                    <tr><th scope="row">Total</th><td className="numero" title={millones(datos.venta)}>{millonesTabla(datos.venta)}</td><td /><td className="numero">{porcentaje(datos.rentabilidad)}</td></tr>
                  </tfoot>
                </table>
              </div>
            </section>

            <section className="rentabilidad-mes__panel">
              <h2 className="rentabilidad-mes__titulo-panel">Facturación BIENES</h2>
              <div className="tabla-envoltorio">
                <table className="tabla tabla--compacta rentabilidad-mes__tabla">
                  <thead>
                    <tr><th>ESPECIE</th><th className="numero">Vlr_FactMM</th><th aria-label="Semáforo" /><th className="numero">%Rent</th></tr>
                  </thead>
                  <tbody>
                    {datos.especies.map((fila) => {
                      const clave = `especie:${fila.etiqueta}`;
                      const abierto = !gruposColapsados.has(clave);
                      return (
                        <FragmentoEspecie
                          key={fila.etiqueta}
                          fila={fila}
                          abierto={abierto}
                          alAlternar={() => alternarGrupo(clave)}
                          comercialesExpandidos={comercialesExpandidos}
                          alAlternarComercial={alternarComercial}
                        />
                      );
                    })}
                  </tbody>
                  <tfoot>
                    <tr><th scope="row">Total</th><td className="numero" title={millones(datos.especies.reduce((suma, fila) => suma + Number(fila.venta), 0).toString())}>{millonesTabla(datos.especies.reduce((suma, fila) => suma + Number(fila.venta), 0).toString())}</td><td /><td className="numero">{porcentaje(datos.rentabilidad)}</td></tr>
                  </tfoot>
                </table>
              </div>
            </section>
          </div>

          <div className="rentabilidad-mes__columna rentabilidad-mes__columna--derecha">
            <TablaRanking
              titulo="Ranking Clientes"
              etiqueta="Razón social cliente despacho"
              filas={datos.clientes}
              totalVenta={datos.venta}
              totalRentabilidad={datos.rentabilidad}
              mostrarPosicion
            />
            <TablaRanking
              titulo="Ranking Productos"
              etiqueta="Desc. item"
              filas={datos.productos}
              totalVenta={datos.venta}
              totalRentabilidad={datos.rentabilidad}
            />
          </div>
          </section>
        </>
      ) : null}
    </main>
  );
}

function FragmentoTipoItem({
  fila,
  abierto,
  alAlternar,
}: {
  fila: FilaTipoItemRentabilidadMes;
  abierto: boolean;
  alAlternar: () => void;
}) {
  return (
    <>
      <tr className="rentabilidad-mes__grupo">
        <th scope="row">
          <button type="button" aria-expanded={abierto} onClick={alAlternar}>
            <span aria-hidden="true">{abierto ? "⊟" : "⊞"}</span>{fila.etiqueta}
          </button>
        </th>
        <td className="numero" title={millones(fila.venta)}>{millonesTabla(fila.venta)}</td>
        <td />
        <td className="numero">{porcentaje(fila.rentabilidad)}</td>
      </tr>
      {abierto ? fila.centros_operacion.map((centro) => (
        <tr key={`${fila.etiqueta}-${centro.etiqueta}`}>
          <th scope="row" className="rentabilidad-mes__subfila">{centro.etiqueta}</th>
          <td className="numero" title={millones(centro.venta)}>{millonesTabla(centro.venta)}</td>
          <td className="rentabilidad-mes__celda-semaforo"><SemaforoRentabilidad valor={centro.rentabilidad} /></td>
          <td className="numero">{porcentaje(centro.rentabilidad)}</td>
        </tr>
      )) : null}
    </>
  );
}

function FragmentoEspecie({
  fila,
  abierto,
  alAlternar,
  comercialesExpandidos,
  alAlternarComercial,
}: {
  fila: FilaEspecieRentabilidadMes;
  abierto: boolean;
  alAlternar: () => void;
  comercialesExpandidos: Set<string>;
  alAlternarComercial: (clave: string) => void;
}) {
  return (
    <>
      <tr className="rentabilidad-mes__grupo">
        <th scope="row">
          <button type="button" aria-expanded={abierto} onClick={alAlternar}>
            <span aria-hidden="true">{abierto ? "⊟" : "⊞"}</span>{fila.etiqueta}
          </button>
        </th>
        <td className="numero" title={millones(fila.venta)}>{millonesTabla(fila.venta)}</td>
        <td />
        <td className="numero">{porcentaje(fila.rentabilidad)}</td>
      </tr>
      {abierto ? fila.comerciales.map((comercial) => {
        const clave = `comercial:${fila.etiqueta}:${comercial.etiqueta}`;
        const expandido = comercialesExpandidos.has(clave);
        return (
          <Fragment key={clave}>
            <tr className="rentabilidad-mes__grupo-comercial">
              <th scope="row" className="rentabilidad-mes__subfila">
                <button type="button" aria-expanded={expandido} onClick={() => alAlternarComercial(clave)}>
                  <span aria-hidden="true">{expandido ? "⊟" : "⊞"}</span>{comercial.etiqueta}
                </button>
              </th>
              <td className="numero" title={millones(comercial.venta)}>{millonesTabla(comercial.venta)}</td>
              <td className="rentabilidad-mes__celda-semaforo"><EstadoRentabilidadCalculada valor={comercial.rentabilidad} /></td>
              <td className="numero">{porcentaje(comercial.rentabilidad)}</td>
            </tr>
            {expandido ? comercial.productos.map((producto) => (
              <tr className="rentabilidad-mes__producto" key={`${clave}:${producto.etiqueta}`}>
                <th scope="row" className="rentabilidad-mes__subfila">{producto.etiqueta}</th>
                <td className="numero" title={millones(producto.venta)}>{millonesTabla(producto.venta)}</td>
                <td className="rentabilidad-mes__celda-semaforo"><EstadoRentabilidadCalculada valor={producto.rentabilidad} /></td>
                <td className="numero">{porcentaje(producto.rentabilidad)}</td>
              </tr>
            )) : null}
          </Fragment>
        );
      }) : null}
    </>
  );
}