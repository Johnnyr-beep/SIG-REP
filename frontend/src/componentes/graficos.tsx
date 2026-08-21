/**
 * Gráficos, en SVG y CSS propios.
 *
 * No se añade una librería de gráficos: la superficie visual de SIGREP son
 * barras contra una referencia y una serie de columnas diarias, y cualquier
 * paquete del mercado pesa más que toda la aplicación para dibujarlas. El SVG
 * además se adapta solo al modo oscuro, porque toma los colores del tema.
 *
 * Ninguna figura inventa una cifra: si el dato es `null` se dibuja la forma
 * vacía, del mismo tamaño y en la misma posición, sin número.
 *
 * Las figuras llevan `role="img"` con su `aria-label`, de modo que el lector de
 * pantalla recibe el mismo contenido que el ojo, y la cifra siempre está además
 * escrita en texto al lado.
 */

import {
  SIN_DATO,
  porcentaje,
  proporcionParaGrafico,
} from "@/utilidades/formato";
import type { Semaforo } from "@/api/tipos";
import { aspectoSemaforo } from "@/utilidades/dominio";

// ── Barra de cumplimiento contra el ideal ────────────────────────────────────

/**
 * La figura central del tablero.
 *
 * El relleno es el cumplimiento sobre el presupuesto del mes; la marca vertical
 * es el ideal, es decir dónde debería ir hoy. Toda la lectura gerencial de la
 * pantalla es «¿el relleno llegó a la marca?», y esa pregunta se responde de un
 * vistazo sin leer un solo número.
 */
export function BarraContraIdeal({
  cumplimiento,
  ideal,
  semaforo,
  etiqueta,
  compacta,
}: {
  cumplimiento: string | null;
  ideal: string | null;
  semaforo: Semaforo;
  /** Qué se está midiendo; entra en la descripción accesible. */
  etiqueta: string;
  compacta?: boolean;
}) {
  const aspecto = aspectoSemaforo(semaforo);
  const anchoRelleno = proporcionParaGrafico(cumplimiento) * 100;
  const posicionIdeal =
    ideal === null ? null : proporcionParaGrafico(ideal) * 100;

  const descripcion =
    cumplimiento === null
      ? `${etiqueta}: sin cumplimiento calculable.`
      : `${etiqueta}: cumplimiento ${porcentaje(cumplimiento)}, ideal ${porcentaje(ideal)}. ${aspecto.descripcion}`;

  return (
    <div
      className={`barra-ideal${compacta ? " barra-ideal--compacta" : ""}`}
      role="img"
      aria-label={descripcion}
    >
      <div className="barra-ideal__pista">
        {cumplimiento === null ? (
          <div className="barra-ideal__vacia" />
        ) : (
          <div
            className={`barra-ideal__relleno barra-ideal__relleno--${aspecto.tono}`}
            style={{ width: `${anchoRelleno}%` }}
          />
        )}
        {posicionIdeal === null ? null : (
          <div
            className="barra-ideal__marca"
            style={{ left: `${posicionIdeal}%` }}
          >
            <span className="barra-ideal__marca-linea" />
          </div>
        )}
      </div>
      {compacta ? null : (
        <div className="barra-ideal__pie">
          <span>0 %</span>
          <span className="barra-ideal__nota">▏ ideal {porcentaje(ideal)}</span>
          <span>100 %</span>
        </div>
      )}
    </div>
  );
}

// ── Barra de participación ───────────────────────────────────────────────────

/**
 * Barra simple que acompaña a un porcentaje ya escrito al lado.
 *
 * Va oculta a los lectores de pantalla a propósito: repetir el mismo dato como
 * `progressbar` solo añade ruido cuando la cifra está en la celda contigua.
 */
export function BarraParticipacion({ valor }: { valor: string | null }) {
  if (valor === null)
    return <div className="barra barra--vacia" aria-hidden="true" />;

  return (
    <div className="barra" aria-hidden="true">
      <div
        className="barra__relleno"
        style={{ width: `${proporcionParaGrafico(valor) * 100}%` }}
      />
    </div>
  );
}

// ── Columnas de venta diaria ─────────────────────────────────────────────────

const ANCHO = 640;
const ALTO = 170;
const MARGEN_X = 8;
const MARGEN_ARRIBA = 12;
const MARGEN_ABAJO = 26;

export interface ColumnaDiaria {
  fecha: string;
  etiqueta: string;
  /** Venta del día, como cadena decimal de la API. */
  valor: string | null;
  esDomingo: boolean;
  /**
   * Presupuesto diario de **este** día.
   *
   * Existe porque el rango puede cruzar de mes y el presupuesto es mensual: un
   * día de julio no se mide contra el presupuesto de agosto. Cuando se omite se
   * usa la referencia general, que es el caso normal de un rango dentro de un
   * solo mes.
   */
  referencia?: string | null;
}

/**
 * Venta día a día con el presupuesto diario derivado como línea de referencia.
 *
 * La referencia es el número que el negocio no tenía bien en el Excel: verla
 * cruzando las columnas convierte «vendimos 50 millones» en «vendimos 50 de los
 * 58 que tocaban».
 */
export function ColumnasDiarias({
  columnas,
  referencia,
  titulo,
  formatear,
}: {
  columnas: ColumnaDiaria[];
  /** Presupuesto diario general; `null` si el PDV no tiene presupuesto. */
  referencia: string | null;
  titulo: string;
  formatear: (valor: string | null) => string;
}) {
  if (columnas.length === 0) {
    return <p className="tenue">Sin días en el período seleccionado.</p>;
  }

  // La referencia se resuelve columna a columna: en un rango que cruza de mes la
  // línea no es una recta, sino un escalón en el cambio de período. Dibujarla
  // recta sería pintar la referencia equivocada sobre los días del otro mes.
  const referencias = columnas.map((columna) =>
    columna.referencia === undefined ? referencia : columna.referencia,
  );
  const distintas = new Set(referencias.map((valor) => valor ?? ""));
  const uniforme = distintas.size <= 1;

  const valores = columnas.map((columna) => Number(columna.valor ?? 0));
  const maximoDatos = Math.max(
    ...valores,
    ...referencias.map((valor) => Number(valor ?? 0)),
  );
  // Un 12 % de aire arriba evita que la columna más alta toque el borde y que
  // la línea de referencia se confunda con el marco.
  const escala = maximoDatos > 0 ? maximoDatos * 1.12 : 1;

  const utilAlto = ALTO - MARGEN_ARRIBA - MARGEN_ABAJO;
  const paso = (ANCHO - MARGEN_X * 2) / columnas.length;
  const anchoColumna = Math.max(4, paso * 0.62);

  function alturaDe(valor: string | null): number | null {
    if (valor === null) return null;
    return (
      MARGEN_ARRIBA + utilAlto - proporcionParaGrafico(valor, escala) * utilAlto
    );
  }

  const resumen = columnas
    .map((columna) => `${columna.etiqueta}: ${formatear(columna.valor)}`)
    .join("; ");

  const lecturaReferencia = uniforme
    ? `Referencia diaria ${formatear(referencias[0] ?? null)}.`
    : "La referencia diaria cambia con el mes de cada día.";

  return (
    <div className="columnas">
      <svg
        className="columnas__lienzo"
        viewBox={`0 0 ${ANCHO} ${ALTO}`}
        role="img"
        aria-label={`${titulo}. ${lecturaReferencia} ${resumen}.`}
      >
        {columnas.map((columna, indice) => {
          const suReferencia = referencias[indice] ?? null;
          const alturaColumna =
            columna.valor === null
              ? 0
              : proporcionParaGrafico(columna.valor, escala) * utilAlto;
          const x = MARGEN_X + paso * indice + (paso - anchoColumna) / 2;
          const y = MARGEN_ARRIBA + utilAlto - alturaColumna;
          const yReferencia = alturaDe(suReferencia);
          const bajoReferencia =
            suReferencia !== null &&
            columna.valor !== null &&
            Number(columna.valor) < Number(suReferencia);

          return (
            <g key={columna.fecha}>
              {columna.esDomingo ? (
                <rect
                  className="columnas__domingo"
                  x={MARGEN_X + paso * indice}
                  y={MARGEN_ARRIBA}
                  width={paso}
                  height={utilAlto}
                />
              ) : null}
              <rect
                className={`columnas__barra${bajoReferencia ? " columnas__barra--baja" : ""}`}
                x={x}
                y={y}
                width={anchoColumna}
                height={Math.max(alturaColumna, columna.valor === null ? 0 : 1)}
                rx="2"
              />
              <text
                className="columnas__etiqueta"
                x={MARGEN_X + paso * indice + paso / 2}
                y={ALTO - 8}
                textAnchor="middle"
              >
                {columna.etiqueta}
              </text>
              {yReferencia === null ? null : (
                <line
                  className="columnas__referencia"
                  x1={MARGEN_X + paso * indice}
                  x2={MARGEN_X + paso * (indice + 1)}
                  y1={yReferencia}
                  y2={yReferencia}
                />
              )}
            </g>
          );
        })}
      </svg>

      <p className="columnas__leyenda">
        <span className="columnas__muestra" aria-hidden="true" />
        Venta del día
        <span
          className="columnas__muestra columnas__muestra--referencia"
          aria-hidden="true"
        />
        {uniforme
          ? `Presupuesto diario: ${
              referencias[0] == null ? SIN_DATO : formatear(referencias[0])
            }`
          : "Presupuesto diario: cambia con el mes de cada día"}
      </p>
    </div>
  );
}
