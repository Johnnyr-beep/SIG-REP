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

// ── Anillo de cumplimiento ───────────────────────────────────────────────────

/**
 * El cumplimiento como anillo, con la marca del ideal en el borde.
 *
 * Es la misma lectura que `BarraContraIdeal` en otra forma, y existe porque en
 * agropecuaria se enseñan **dos a la vez** —pesos y kilos— y dos barras
 * apiladas se leen como una sola serie partida. Dos anillos uno al lado del
 * otro se leen como lo que son: dos medidas del mismo mes.
 *
 * La marca del ideal no es decoración. Sin ella un 53 % no dice nada: puede ser
 * ir bien el día 12 e ir mal el día 28. Con la marca, la pregunta se responde
 * mirando: ¿el relleno pasó de la muesca?
 */
export function AnilloCumplimiento({
  cumplimiento,
  ideal,
  etiqueta,
  semaforo,
  razonSinDato = "no hay presupuesto capturado",
}: {
  cumplimiento: string | null;
  ideal?: string | null;
  /** «Pesos», «Kilos»: va debajo del anillo. */
  etiqueta: string;
  semaforo?: Semaforo;
  /**
   * Por qué no hay cifra, para el lector de pantalla y la nota del pie.
   *
   * El motivo habitual es que nadie capturó el presupuesto, pero no es el
   * único: los dos anillos de agropecuaria salen de dos consultas distintas y
   * mientras la segunda viaja el anillo de kilos también está sin cifra.
   * Afirmar ahí «no hay presupuesto capturado» es decir algo falso durante un
   * segundo y luego desdecirse, que es peor que no decir nada.
   */
  razonSinDato?: string;
}) {
  const RADIO = 52;
  const GROSOR = 12;
  const PERIMETRO = 2 * Math.PI * RADIO;

  // El anillo se llena hasta el 100 %; por encima se queda lleno y la cifra
  // escrita al lado dice el resto. Un anillo que diera más de una vuelta
  // mostraría un 120 % igual que un 20 %.
  const proporcion = proporcionParaGrafico(cumplimiento);
  const aspecto = semaforo ? aspectoSemaforo(semaforo) : null;
  const sinDato = cumplimiento === null;

  const gradosIdeal = ideal ? proporcionParaGrafico(ideal) * 360 : null;

  return (
    <figure className="anillo">
      <svg
        viewBox="0 0 140 140"
        className="anillo__figura"
        role="img"
        aria-label={
          sinDato
            ? `${etiqueta}: sin cumplimiento que mostrar, ${razonSinDato}.`
            : `${etiqueta}: ${porcentaje(cumplimiento)} del presupuesto` +
              (ideal ? `, con un ideal de ${porcentaje(ideal)}.` : ".")
        }
      >
        {/* El surco: siempre completo, para que el relleno se lea como fracción
            de algo y no como una forma suelta. */}
        <circle
          cx="70"
          cy="70"
          r={RADIO}
          className="anillo__surco"
          strokeWidth={GROSOR}
          fill="none"
        />
        {sinDato ? null : (
          <circle
            cx="70"
            cy="70"
            r={RADIO}
            className={`anillo__relleno${aspecto ? ` anillo__relleno--${aspecto.tono}` : ""}`}
            strokeWidth={GROSOR}
            fill="none"
            strokeLinecap="round"
            strokeDasharray={`${PERIMETRO * proporcion} ${PERIMETRO}`}
            transform="rotate(-90 70 70)"
          />
        )}
        {gradosIdeal === null ? null : (
          <line
            x1="70"
            y1={70 - RADIO - GROSOR / 2 - 2}
            x2="70"
            y2={70 - RADIO + GROSOR / 2 + 2}
            className="anillo__ideal"
            transform={`rotate(${gradosIdeal} 70 70)`}
          />
        )}
        {/* Un cumplimiento de cuatro cifras —«1.240,5 %», que sale de una meta
            capturada de menos— no cabe a tamaño completo dentro de 140 unidades
            de lienzo y se derramaba fuera del anillo. La cifra se encoge; el
            anillo no se toca. */}
        <text
          x="70"
          y="76"
          className={`anillo__cifra${sinDato || porcentaje(cumplimiento).length <= 7 ? "" : " anillo__cifra--larga"}`}
          textAnchor="middle"
        >
          {sinDato ? SIN_DATO : porcentaje(cumplimiento)}
        </text>
      </svg>
      <figcaption className="anillo__etiqueta">
        {etiqueta}
        {/* El «—» del centro no explica nada por sí solo. El motivo va escrito
            debajo, no solo en el `aria-label`: quien mira la pantalla tiene el
            mismo derecho a saberlo que quien la escucha. */}
        {sinDato ? (
          <span className="anillo__razon">{razonSinDato}</span>
        ) : null}
      </figcaption>
    </figure>
  );
}

// ── Tendencia acumulada ──────────────────────────────────────────────────────

export interface PuntoAcumulado {
  fecha: string;
  /** Venta acumulada hasta ese día, inclusive. `null` si el día no tiene dato. */
  acumulado: string | null;
  /** Meta acumulada hasta ese día. `null` si no hay presupuesto. */
  meta: string | null;
}

/**
 * Venta acumulada contra meta acumulada, día a día.
 *
 * **Las dos series son acumuladas, y esa es toda la gracia.** El reporte del que
 * nace esta figura dibujaba la venta *de cada día* contra la meta *acumulada*, y
 * eso no se puede comparar: la venta de un día es 1/31 del mes y la meta al día
 * 21 son 21/31, así que la serie de venta sale pegada al suelo aunque el mes
 * vaya bien. Un gráfico que dice «vamos fatal» en un mes bueno no es un gráfico,
 * es una alarma que la gente aprende a ignorar.
 *
 * Acumuladas las dos, **la distancia vertical entre las líneas es exactamente
 * lo que falta para la meta**, y se lee sin números.
 */
export function TendenciaAcumulada({
  puntos,
  titulo,
  formatear,
}: {
  puntos: PuntoAcumulado[];
  titulo: string;
  formatear: (valor: string | null) => string;
}) {
  const ANCHO = 720;
  const ALTO = 220;
  const MARGEN = { arriba: 12, derecha: 8, abajo: 28, izquierda: 8 };

  if (puntos.length === 0) {
    return <p className="tenue">Sin días en el rango seleccionado.</p>;
  }

  // Un lienzo con las guías puestas y ninguna línea dentro se lee como una
  // figura rota, no como «todavía no hay venta cargada». Con la base recién
  // creada eso es lo que salía: treinta días de rango y ni un dato.
  const hayVenta = puntos.some((punto) => punto.acumulado !== null);
  if (!hayVenta) {
    return (
      <p className="tenue">
        Todavía no hay venta cargada en este rango, así que no hay línea que
        dibujar. La venta entra por la pantalla de ingesta.
      </p>
    );
  }

  // La escala la fija el mayor de las dos series: si la fijara solo la venta, la
  // meta se saldría del marco, y si la fijara solo la meta, un mes que la supera
  // se vería recortado justo cuando es la buena noticia.
  const techo = Math.max(
    ...puntos.map((p) =>
      Math.max(Number(p.acumulado ?? 0), Number(p.meta ?? 0)),
    ),
    1,
  );

  const util = {
    ancho: ANCHO - MARGEN.izquierda - MARGEN.derecha,
    alto: ALTO - MARGEN.arriba - MARGEN.abajo,
  };
  const x = (indice: number) =>
    MARGEN.izquierda +
    (puntos.length === 1
      ? util.ancho / 2
      : (indice / (puntos.length - 1)) * util.ancho);
  const y = (valor: string | null) =>
    MARGEN.arriba + util.alto * (1 - proporcionParaGrafico(valor, techo));

  const linea = (clave: "acumulado" | "meta") =>
    puntos
      .map((punto, indice) =>
        punto[clave] === null ? null : `${x(indice)},${y(punto[clave])}`,
      )
      .filter((par): par is string => par !== null)
      .join(" ");

  const ultimo = puntos[puntos.length - 1];
  const hayMeta = puntos.some((punto) => punto.meta !== null);

  const indiceUnico = puntos.findIndex((punto) => punto.acumulado !== null);
  const puntosDibujados = puntos.filter(
    (punto) => punto.acumulado !== null,
  ).length;

  return (
    <figure className="tendencia">
      <svg
        viewBox={`0 0 ${ANCHO} ${ALTO}`}
        className="tendencia__figura"
        role="img"
        aria-label={
          `${titulo}. Venta acumulada al cierre del rango: ${formatear(ultimo?.acumulado ?? null)}` +
          (hayMeta
            ? `, contra una meta acumulada de ${formatear(ultimo?.meta ?? null)}.`
            : ".")
        }
      >
        {[0.25, 0.5, 0.75].map((fraccion) => (
          <line
            key={fraccion}
            x1={MARGEN.izquierda}
            x2={ANCHO - MARGEN.derecha}
            y1={MARGEN.arriba + util.alto * fraccion}
            y2={MARGEN.arriba + util.alto * fraccion}
            className="tendencia__guia"
          />
        ))}

        {hayMeta ? (
          <polyline
            points={linea("meta")}
            className="tendencia__meta"
            fill="none"
          />
        ) : null}
        <polyline
          points={linea("acumulado")}
          className="tendencia__venta"
          fill="none"
        />

        {/* El día 1 del mes la serie tiene un solo punto y una polilínea de un
            punto no dibuja nada: el gerente abría el tablero el primero y veía
            el recuadro vacío. Con un punto suelto hay marca. */}
        {puntosDibujados === 1 ? (
          <circle
            cx={x(indiceUnico)}
            cy={y(puntos[indiceUnico]?.acumulado ?? null)}
            r="4"
            className="tendencia__punto"
          />
        ) : null}
      </svg>

      <figcaption className="tendencia__leyenda">
        <span className="tendencia__clave tendencia__clave--venta">
          Venta acumulada
        </span>
        {hayMeta ? (
          <span className="tendencia__clave tendencia__clave--meta">
            Meta acumulada
          </span>
        ) : (
          <span className="tenue">Sin meta: no hay presupuesto capturado</span>
        )}
      </figcaption>
    </figure>
  );
}
