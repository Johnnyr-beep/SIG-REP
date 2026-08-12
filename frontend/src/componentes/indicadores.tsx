/**
 * El bloque de indicadores de §4, en una sola pieza.
 *
 * El contrato define `FilaIndicadores` una vez y lo repite idéntico en compañía,
 * grupo, punto de venta y categoría. La interfaz hace lo mismo: un solo juego de
 * encabezados y un solo componente de celdas. Añadir un indicador es tocar este
 * archivo, y aparece a la vez en todos los niveles de todas las pantallas.
 */

import type { ReactNode } from "react";

import type { FilaIndicadores, Medida, ParametrosCalculo, Semaforo } from "@/api/tipos";
import { Pista } from "@/componentes/comunes";
import { FORMULAS, aspectoSemaforo, unidadDe } from "@/utilidades/dominio";
import { SIN_DATO, dias, fecha, porMedida, porcentaje, puntos } from "@/utilidades/formato";

// ── Semáforo ─────────────────────────────────────────────────────────────────

/**
 * Estado del punto de venta, legible sin distinguir colores.
 *
 * Lleva siempre símbolo y texto; el color es el tercer refuerzo, no el único.
 * En la versión compacta el texto se conserva para el lector de pantalla aunque
 * la celda solo muestre el símbolo, porque una tabla de dieciséis filas con la
 * palabra repetida se vuelve ilegible.
 */
export function Semaforo({ estado, compacto }: { estado: Semaforo; compacto?: boolean }) {
  const aspecto = aspectoSemaforo(estado);

  return (
    <span
      className={`semaforo semaforo--${aspecto.tono}${compacto ? " semaforo--compacto" : ""}`}
      title={aspecto.descripcion}
    >
      <span className="semaforo__simbolo" aria-hidden="true">
        {aspecto.simbolo}
      </span>
      {compacto ? (
        <span className="solo-lectores">{aspecto.etiqueta}</span>
      ) : (
        <span>{aspecto.etiqueta}</span>
      )}
    </span>
  );
}

// ── Encabezados y celdas ─────────────────────────────────────────────────────

interface DefinicionColumna {
  clave: string;
  titulo: string;
  /** Fórmula de §4 que la produce; se muestra en la pista del encabezado. */
  formula?: string;
  /** La columna solo tiene sentido midiendo en pesos (margen). */
  soloValor?: boolean;
}

const COLUMNAS: DefinicionColumna[] = [
  { clave: "presupuesto", titulo: "Presupuesto" },
  { clave: "venta", titulo: "Venta" },
  { clave: "cumplimiento", titulo: "Cumpl.", formula: FORMULAS.cumplimiento },
  { clave: "ideal", titulo: "Ideal", formula: FORMULAS.ideal },
  { clave: "brecha", titulo: "Brecha", formula: FORMULAS.brecha },
  { clave: "semaforo", titulo: "Estado" },
  { clave: "proyeccion", titulo: "Proyección", formula: FORMULAS.proyeccion },
  { clave: "cumplimiento_proyectado", titulo: "% Proy.", formula: FORMULAS.cumplimiento_proyectado },
  { clave: "venta_diaria_promedio", titulo: "Venta diaria", formula: FORMULAS.venta_diaria_promedio },
  {
    clave: "venta_diaria_requerida",
    titulo: "V. diaria requerida",
    formula: FORMULAS.venta_diaria_requerida,
  },
  { clave: "venta_anio_anterior", titulo: "Año anterior" },
  { clave: "crecimiento", titulo: "Crecimiento", formula: FORMULAS.crecimiento },
  { clave: "margen_valor", titulo: "Margen", formula: FORMULAS.margen_valor, soloValor: true },
  {
    clave: "margen_porcentaje",
    titulo: "Margen %",
    formula: FORMULAS.margen_porcentaje,
    soloValor: true,
  },
];

/** Encabezados de la tabla de indicadores, con la fórmula de cada columna. */
export function EncabezadosIndicadores({ medida }: { medida: Medida }) {
  return (
    <>
      {COLUMNAS.map((columna) => (
        <th key={columna.clave} scope="col" className="numero">
          <span className="encabezado">
            <span>
              {columna.titulo}
              {columna.clave === "presupuesto" || columna.clave === "venta" ? (
                <span className="encabezado__unidad"> ({unidadDe(medida)})</span>
              ) : null}
            </span>
            {columna.formula ? (
              <Pista etiqueta={columna.titulo} alineacion="derecha">
                <p className="formula">{columna.formula}</p>
                {columna.soloValor && medida === "kilos" ? (
                  <p className="tenue">
                    El margen es un concepto monetario: midiendo en kilos no aplica y se muestra «—».
                  </p>
                ) : null}
              </Pista>
            ) : null}
          </span>
        </th>
      ))}
    </>
  );
}

/** Número de columnas que ocupa el bloque; necesario para los `colSpan`. */
export const COLUMNAS_INDICADORES = COLUMNAS.length;

/**
 * Las celdas de una fila de indicadores.
 *
 * Cada valor `null` se pinta «—»: es el contrato y es la regla de §7. Nunca un
 * cero, que en un reporte de cumplimiento significa «vendió cero», ni un vacío,
 * que parece un fallo de la pantalla.
 */
export function CeldasIndicadores({ fila, medida }: { fila: FilaIndicadores; medida: Medida }) {
  return (
    <>
      <td className="numero">{porMedida(fila.presupuesto, medida)}</td>
      <td className="numero">{porMedida(fila.venta, medida)}</td>
      <td className="numero numero--destacado">{porcentaje(fila.cumplimiento)}</td>
      <td className="numero suave">{porcentaje(fila.ideal)}</td>
      <td className={`numero ${claseBrecha(fila.brecha)}`}>{puntos(fila.brecha)}</td>
      <td>
        <Semaforo estado={fila.semaforo} compacto />
      </td>
      <td className="numero">{porMedida(fila.proyeccion, medida)}</td>
      <td className="numero">{porcentaje(fila.cumplimiento_proyectado)}</td>
      <td className="numero">{porMedida(fila.venta_diaria_promedio, medida)}</td>
      <td className="numero numero--destacado">{porMedida(fila.venta_diaria_requerida, medida)}</td>
      <td className="numero suave">{porMedida(fila.venta_anio_anterior, medida)}</td>
      <td className="numero">{porcentaje(fila.crecimiento)}</td>
      <td className="numero suave">{porMedida(fila.margen_valor, "valor")}</td>
      <td className="numero">{porcentaje(fila.margen_porcentaje)}</td>
    </>
  );
}

/** La brecha se colorea, pero su signo ya se lee en el texto («+1,2 pp»). */
function claseBrecha(brecha: string | null): string {
  if (brecha === null || brecha === "") return "suave";
  return brecha.trim().startsWith("-") ? "texto-peligro" : "texto-exito";
}

// ── Trazabilidad del cálculo ─────────────────────────────────────────────────

/**
 * De dónde salen los números de la pantalla.
 *
 * §4.2 lo exige y es la diferencia con el Excel que SIGREP reemplaza: días
 * hábiles, días trabajados, fecha de corte y umbrales del semáforo, a la vista,
 * para que la gerencia pueda rehacer el cálculo a mano si desconfía. Un
 * indicador sin sus parámetros es un número sin origen.
 */
export function PieCalculo({
  parametros,
  medida,
  extra,
}: {
  parametros: ParametrosCalculo | null | undefined;
  medida: Medida;
  extra?: ReactNode;
}) {
  if (!parametros) {
    return (
      <p className="tenue">
        El backend no envió <code>parametros_calculo</code> en esta respuesta, así que no se puede
        mostrar de dónde salen los números. Los indicadores siguen siendo los que devolvió la API.
      </p>
    );
  }

  const umbrales = parametros.umbrales ?? {};

  return (
    <div className="pie-calculo">
      <dl className="pie-calculo__lista">
        <div>
          <dt>Fecha de corte</dt>
          <dd>{fecha(parametros.fecha_corte)}</dd>
        </div>
        <div>
          <dt>Días hábiles (H)</dt>
          <dd>{dias(parametros.dias_habiles)}</dd>
        </div>
        <div>
          <dt>Días trabajados (T)</dt>
          <dd>{dias(parametros.dias_trabajados)}</dd>
        </div>
        <div>
          <dt>Medida</dt>
          <dd>{medida === "kilos" ? "Kilos" : "Pesos"}</dd>
        </div>
      </dl>

      {Object.keys(umbrales).length > 0 ? (
        <p className="pie-calculo__umbrales">
          <strong>Umbrales del semáforo:</strong>{" "}
          {Object.entries(umbrales)
            .map(([nombre, valor]) => `${nombre}: ${valor}`)
            .join(" · ")}
        </p>
      ) : null}

      <p className="pie-calculo__formulas">
        {FORMULAS.cumplimiento} · {FORMULAS.ideal} · {FORMULAS.proyeccion} ·{" "}
        {FORMULAS.venta_diaria_requerida}
      </p>

      {extra}
    </div>
  );
}

// ── Indicador destacado ──────────────────────────────────────────────────────

export function Indicador({
  etiqueta,
  valor,
  nota,
  pista,
  tono,
}: {
  etiqueta: string;
  valor: ReactNode;
  nota?: ReactNode;
  pista?: ReactNode;
  tono?: "exito" | "aviso" | "peligro";
}) {
  return (
    <div className={`indicador${tono ? ` indicador--${tono}` : ""}`}>
      <span className="indicador__etiqueta">
        {etiqueta}
        {pista ? <Pista etiqueta={etiqueta}>{pista}</Pista> : null}
      </span>
      <span className="indicador__valor">{valor}</span>
      {nota ? <span className="indicador__nota">{nota}</span> : null}
    </div>
  );
}

/** Texto auxiliar para las notas: «— » cuando no hay dato que comparar. */
export function notaComparativa(cumplimiento: string | null, ideal: string | null): string {
  if (cumplimiento === null || ideal === null) return `Ideal ${SIN_DATO}`;
  return `Ideal del período: ${porcentaje(ideal)}`;
}
