/**
 * El bloque de indicadores de agropecuaria, en una sola pieza.
 *
 * Mismo trato que `indicadores.tsx` en carnes: el contrato define
 * `IndicadoresAgro` una vez y lo repite idéntico en los siete ejes del resumen,
 * en los dos cruces y en el consolidado, así que aquí hay un solo juego de
 * encabezados y un solo componente de celdas. Añadir un indicador es tocar este
 * archivo y aparece a la vez en las tres pantallas.
 *
 * Lo que **no** se duplica de carnes: el semáforo, la barra contra el ideal, la
 * tarjeta, la pista y el pie de cálculo se importan de allí. Solo cambian las
 * columnas, porque los dos bloques de indicadores no son el mismo —agro publica
 * kilos, cantidad, líneas facturadas y participación; carnes publica año
 * anterior y crecimiento—.
 */

import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import type { Medida } from "@/api/tipos";
import type {
  ConciliacionAgro,
  CuadrePresupuestoAgro,
  DimensionPresupuestoAgro,
  IndicadoresAgro,
  ParametrosCalculoAgro,
} from "@/api/tiposAgro";
import { Pista } from "@/componentes/comunes";
import { PieCalculo, Semaforo } from "@/componentes/indicadores";
import { formulaDe } from "@/utilidades/dominioAgro";
import { unidadDe } from "@/utilidades/dominio";
import {
  dinero,
  kilos as formatearKilos,
  numero,
  periodoLargo,
  porMedida,
  porcentaje,
  puntos,
} from "@/utilidades/formato";

// ── Columnas ─────────────────────────────────────────────────────────────────

interface DefinicionColumna {
  clave: string;
  titulo: string;
  /** Solo tiene sentido si el eje tiene presupuesto contra el que medir. */
  requiereMeta?: boolean;
  /** Texto de la pista del encabezado, además de la fórmula. */
  nota?: string;
}

/**
 * Las columnas en el orden en que se leen.
 *
 * Las nueve que dependen del presupuesto van marcadas: en los tres ejes que no
 * se presupuestan —cliente, grupo y tipo de ítem— **no se pintan en absoluto**,
 * en lugar de dejar nueve columnas de guiones. Un guion dice «este dato falta»;
 * la ausencia de la columna, acompañada del aviso que la explica, dice «aquí no
 * hay meta contra la que medir», que es lo cierto.
 */
const COLUMNAS: DefinicionColumna[] = [
  { clave: "presupuesto", titulo: "Presupuesto", requiereMeta: true },
  { clave: "venta", titulo: "Venta" },
  { clave: "cruzada", titulo: "" },
  { clave: "cumplimiento", titulo: "Cumpl.", requiereMeta: true },
  { clave: "ideal", titulo: "Ideal", requiereMeta: true },
  { clave: "brecha", titulo: "Brecha", requiereMeta: true },
  { clave: "semaforo", titulo: "Estado", requiereMeta: true },
  { clave: "proyeccion", titulo: "Proyección", requiereMeta: true },
  { clave: "cumplimiento_proyectado", titulo: "% Proy.", requiereMeta: true },
  {
    clave: "venta_diaria_promedio",
    titulo: "Venta diaria",
    requiereMeta: true,
  },
  {
    clave: "venta_diaria_requerida",
    titulo: "V. diaria requerida",
    requiereMeta: true,
  },
  {
    clave: "cantidad",
    titulo: "Cantidad",
    nota: "Unidades del ítem tal como las entrega la fuente. No son kilos: los kilos van en su propia columna.",
  },
  {
    clave: "lineas_facturadas",
    titulo: "Líneas",
    nota: "Líneas facturadas, no documentos ni tickets. Una venta de ocho productos son ocho líneas y un documento, y la fuente no entrega el documento.",
  },
  {
    clave: "margen_valor",
    titulo: "Margen",
    nota: "Siempre en pesos, aunque el reporte se mire en kilos: el margen es un concepto monetario. Puede ser negativo.",
  },
  { clave: "margen_porcentaje", titulo: "Margen %" },
  { clave: "participacion", titulo: "Particip." },
];

/** Cuántas columnas ocupa el bloque; necesario para los `colSpan`. */
export function columnasIndicadoresAgro(conMeta: boolean): number {
  return COLUMNAS.filter((columna) => conMeta || !columna.requiereMeta).length;
}

/**
 * El título de la columna que acompaña a «Venta».
 *
 * `venta` trae la medida activa y `kilos` trae siempre kilos, así que midiendo
 * en kilos las dos columnas dirían exactamente lo mismo. En vez de repetir la
 * cifra, la columna cambia de contenido: en pesos enseña los kilos y en kilos
 * enseña la venta en pesos, que es el dato que en ese momento no está a la vista
 * y que el contrato publica precisamente para eso (`venta_valor`).
 */
function tituloCruzada(medida: Medida): string {
  return medida === "kilos" ? "Venta ($)" : "Kilos";
}

/**
 * Encabezados del bloque, con la fórmula de cada columna.
 *
 * Las fórmulas salen de `parametros_calculo.formulas` —las que escribió quien
 * las implementó— y no de una copia local: un número acompañado de la fórmula
 * equivocada es peor que un número sin fórmula.
 */
export function EncabezadosIndicadoresAgro({
  medida,
  conMeta,
  formulas,
}: {
  medida: Medida;
  conMeta: boolean;
  formulas?: Record<string, string> | null;
}) {
  return (
    <>
      {COLUMNAS.filter((columna) => conMeta || !columna.requiereMeta).map(
        (columna) => {
          const titulo =
            columna.clave === "cruzada"
              ? tituloCruzada(medida)
              : columna.titulo;
          const formula = formulaDe(formulas, columna.clave);
          const llevaUnidad =
            columna.clave === "presupuesto" || columna.clave === "venta";

          return (
            <th key={columna.clave} scope="col" className="numero">
              <span className="encabezado">
                <span>
                  {titulo}
                  {llevaUnidad ? (
                    <span className="encabezado__unidad">
                      {" "}
                      ({unidadDe(medida)})
                    </span>
                  ) : null}
                </span>
                {formula || columna.nota ? (
                  <Pista etiqueta={titulo} alineacion="derecha">
                    {formula ? <p className="formula">{formula}</p> : null}
                    {columna.nota ? (
                      <p className="tenue">{columna.nota}</p>
                    ) : null}
                  </Pista>
                ) : null}
              </span>
            </th>
          );
        },
      )}
    </>
  );
}

/**
 * Las celdas de una fila.
 *
 * Cada valor `null` se pinta «—», nunca un cero: en un reporte de cumplimiento
 * el cero significa «vendió cero», que es una afirmación distinta de «no hay con
 * qué compararlo».
 */
export function CeldasIndicadoresAgro({
  fila,
  medida,
  conMeta,
  sujeto,
}: {
  fila: IndicadoresAgro;
  medida: Medida;
  conMeta: boolean;
  /** Qué es esta fila —«el vendedor», «la especie»— para el texto del semáforo. */
  sujeto?: string;
}) {
  return (
    <>
      {conMeta ? (
        <td className="numero">{porMedida(fila.presupuesto, medida)}</td>
      ) : null}
      <td className="numero numero--destacado">
        {porMedida(fila.venta, medida)}
      </td>
      <td className="numero suave">
        {medida === "kilos"
          ? dinero(fila.venta_valor)
          : formatearKilos(fila.kilos)}
      </td>

      {conMeta ? (
        <>
          <td className="numero numero--destacado">
            {porcentaje(fila.cumplimiento)}
          </td>
          <td className="numero suave">{porcentaje(fila.ideal)}</td>
          <td className={`numero ${claseSigno(fila.brecha)}`}>
            {puntos(fila.brecha)}
          </td>
          <td>
            <Semaforo estado={fila.semaforo} compacto sujeto={sujeto} />
          </td>
          <td className="numero">{porMedida(fila.proyeccion, medida)}</td>
          <td className="numero">{porcentaje(fila.cumplimiento_proyectado)}</td>
          <td className="numero">
            {porMedida(fila.venta_diaria_promedio, medida)}
          </td>
          <td className="numero numero--destacado">
            {porMedida(fila.venta_diaria_requerida, medida)}
          </td>
        </>
      ) : null}

      <td className="numero suave">{numero(fila.cantidad)}</td>
      <td className="numero suave">{numero(fila.lineas_facturadas)}</td>
      {/* El margen viaja siempre en pesos, aunque la pantalla mida en kilos. */}
      <td className={`numero ${claseSigno(fila.margen_valor)}`}>
        {dinero(fila.margen_valor)}
      </td>
      <td className={`numero ${claseSigno(fila.margen_porcentaje)}`}>
        {porcentaje(fila.margen_porcentaje)}
      </td>
      <td className="numero">{porcentaje(fila.participacion)}</td>
    </>
  );
}

/**
 * Tiñe una cifra con signo sin depender de que se lea el signo.
 *
 * El margen negativo existe y es legítimo —la venta entre compañías del grupo
 * sale por debajo del costo—, así que no se recorta a cero ni se marca como
 * error: se pinta en negativo y se colorea para que no pase por bueno de un
 * vistazo. El texto ya lleva el «−» delante; el color es el segundo refuerzo.
 */
function claseSigno(valor: string | null): string {
  if (valor === null || valor === "") return "suave";
  return valor.trim().startsWith("-") ? "texto-peligro" : "";
}

// ── El eje que no tiene meta ─────────────────────────────────────────────────

/**
 * Por qué esta tabla no trae cumplimiento.
 *
 * Es la explicación que evita la lectura equivocada: sin ella, un eje sin
 * columnas de meta parece un reporte a medio hacer. Cliente, grupo y tipo de
 * ítem son ejes de **lectura**, no de meta, y no es que falte capturarla —nadie
 * presupuesta 686 clientes—.
 */
export function AvisoEjeSinMeta({ eje }: { eje: string }) {
  return (
    <div className="aviso aviso--info" role="note">
      <div>
        <strong>
          Aquí no hay presupuesto, así que no hay cumplimiento que mostrar.
        </strong>
        <p>
          El negocio fija la meta por centro de operación, especie, tipo
          comercial y vendedor. Agrupando por {eje} se puede <em>ver</em> la
          venta, pero no hay meta contra la que compararla, así que la tabla no
          trae presupuesto, cumplimiento, ideal, brecha, semáforo ni proyección.
          No es un dato pendiente de cargar: es que ahí no hay vara.
        </p>
      </div>
    </div>
  );
}

/**
 * El eje **sí** se presupuesta, pero nadie ha capturado la meta del período.
 *
 * Es el otro caso, y decir el de arriba en su lugar es mentir. Agrupando por
 * centro de operación hay vara —el negocio la fija por ahí—; lo que falta es
 * escribirla. El backend no distingue los dos casos en la respuesta: en los dos
 * manda `presupuesto` vacío y el semáforo en `SIN_PRESUPUESTO`, así que quien
 * decide qué texto va es la pantalla, con `dimensionDeEje`.
 *
 * Lleva enlace a la captura porque este aviso aparece con la base recién
 * creada, que es justo cuando el usuario no sabe adónde ir.
 */
export function AvisoSinPresupuestoCapturado({
  eje,
  dimension,
  periodo,
}: {
  /** «centro», «vendedor»: cómo se llama una fila de este eje. */
  eje: string;
  /** La dimensión de presupuesto contra la que se mediría. */
  dimension: DimensionPresupuestoAgro;
  /** Para llevar el enlace al mismo mes que se está mirando. */
  periodo: string;
}) {
  return (
    <div className="aviso aviso--atencion" role="note">
      <div>
        <strong>
          Todavía no hay presupuesto capturado para este período, así que no hay
          cumplimiento que calcular.
        </strong>
        <p>
          Por {eje} sí se fija meta —es una de las cuatro descomposiciones del
          presupuesto—, pero nadie la ha escrito para{" "}
          {periodoLargo(periodo)}. Mientras siga así, la tabla enseña la venta y
          deja fuera presupuesto, cumplimiento, ideal, brecha, semáforo y
          proyección: publicar un cero ahí sería afirmar que la meta es cero.
        </p>
        <p>
          <Link
            className="boton boton--pequeno"
            to={`/agro/presupuesto?periodo=${periodo}&dimension=${dimension}`}
          >
            Capturar el presupuesto de {periodoLargo(periodo)}
          </Link>
        </p>
      </div>
    </div>
  );
}

// ── Cuadre entre las cuatro dimensiones ──────────────────────────────────────

/**
 * El descuadre entre descomposiciones, donde no se pueda pasar por alto.
 *
 * Las cuatro dimensiones reparten **el mismo dinero**; si sus totales difieren,
 * una de las capturas está mal y cualquier cumplimiento leído contra ella es
 * falso. Por eso el aviso es `role="alert"` y va arriba, y no una nota al pie:
 * quien mire un reporte descuadrado tiene que enterarse antes de sacar
 * conclusiones, no después.
 *
 * Cuando cuadra no se calla del todo —se publica en tono discreto— porque
 * «cuadra» también es información: dice que las cuatro capturas coinciden.
 */
export function AvisoCuadre({
  cuadre,
  discretoSiCuadra = true,
}: {
  cuadre: CuadrePresupuestoAgro | null | undefined;
  /** Con `false` el caso conforme se dibuja igual de visible que el descuadre. */
  discretoSiCuadra?: boolean;
}) {
  if (!cuadre) return null;

  if (cuadre.cuadra) {
    const texto = `Las cuatro descomposiciones del presupuesto cuadran entre sí. ${cuadre.mensaje}`;
    return discretoSiCuadra ? (
      <p className="tenue">{texto}</p>
    ) : (
      <div className="aviso aviso--exito" role="status">
        <div>
          <strong>El presupuesto cuadra.</strong>
          <p>{cuadre.mensaje}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="aviso aviso--error" role="alert">
      <div>
        <strong>
          Las cuatro descomposiciones del presupuesto no dan el mismo total.
          Diferencia: {dinero(cuadre.diferencia_monto)} y{" "}
          {formatearKilos(cuadre.diferencia_kilos)}.
        </strong>
        <p>{cuadre.mensaje}</p>
        <p>
          Vendedor, centro de operación, especie y tipo comercial reparten{" "}
          <em>el mismo</em> dinero, así que si sus totales difieren una de las
          cuatro capturas está mal. Mientras siga así, todo cumplimiento de esta
          unidad se está midiendo contra una meta que depende de por dónde se
          mire. El sistema no reparte la diferencia por su cuenta: eso sería
          inventarse la meta de alguien.
        </p>
        {cuadre.dimensiones.length > 0 ? (
          <ul className="lista-simple">
            {cuadre.dimensiones.map((dimension) => (
              <li key={dimension.dimension}>
                {dimension.etiqueta}
                <strong className="empujar">
                  {dinero(dimension.total_monto)}
                </strong>
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    </div>
  );
}

// ── Conciliación con el origen ───────────────────────────────────────────────

/**
 * Cuánta venta de impuesto se quedó fuera de los totales.
 *
 * Va a la vista y no escondida en una pista: es lo que permite cuadrar la cifra
 * del reporte contra el ERP sin buscar la diferencia a ciegas. Las filas de
 * `TipoItem = IMPUESTO` se ingieren y se guardan marcadas —no se descartan— y se
 * excluyen de todo total: no es venta, es recaudo a nombre de terceros.
 */
export function NotaConciliacion({
  conciliacion,
}: {
  conciliacion: ConciliacionAgro;
}) {
  return (
    <div className="conciliacion">
      <p className="conciliacion__cifra">
        <strong>Excluido de los totales por ser impuesto:</strong>{" "}
        {dinero(conciliacion.impuesto_valor)} ·{" "}
        {formatearKilos(conciliacion.impuesto_kilos)} ·{" "}
        {numero(conciliacion.impuesto_lineas)} líneas facturadas.
      </p>
      <p className="tenue">{conciliacion.nota}</p>
      <p className="tenue">
        Las «líneas facturadas» de aquí no son las mismas que el conteo de{" "}
        <em>filas</em> de impuesto que publica una corrida de ingesta: una fila
        del origen puede traer varias líneas facturadas, así que los dos números
        son correctos y distintos.
      </p>
    </div>
  );
}

// ── Pie de cálculo ───────────────────────────────────────────────────────────

/**
 * De dónde salen los números de la pantalla, para agropecuaria.
 *
 * Reutiliza el `PieCalculo` de carnes —fecha de corte, H, T, medida y
 * umbrales— y le añade lo que solo publica esta unidad: las fórmulas tal como
 * las envía el backend y la conciliación del impuesto. Un número sin origen es
 * exactamente el problema que SIGREP viene a resolver.
 *
 * **El cuadre no va aquí.** Las tres pantallas que usan este pie ya lo publican
 * arriba del todo con `AvisoCuadre`, que es donde corresponde: un descuadre
 * invalida la lectura del reporte entero y hay que enterarse antes de leerlo, no
 * después. Repetirlo al pie duplicaba el mismo `role="alert"` en la misma
 * pantalla —el lector de pantalla lo anunciaba dos veces— y de paso hacía
 * parecer que eran dos descuadres distintos.
 */
export function PieCalculoAgro({
  parametros,
  medida,
  extra,
}: {
  parametros: ParametrosCalculoAgro;
  medida: Medida;
  extra?: ReactNode;
}) {
  return (
    <PieCalculo
      parametros={parametros}
      medida={medida}
      formulas={parametros.formulas}
      extra={
        <>
          {parametros.dimension_presupuesto ? (
            <p className="tenue">
              El cumplimiento de esta pantalla se mide dentro de una sola
              dimensión de presupuesto:{" "}
              <strong>
                {parametros.dimension_presupuesto.replaceAll("_", " ")}
              </strong>
              . Las cuatro dimensiones reparten el mismo dinero, así que nunca
              se suman entre sí.
            </p>
          ) : null}
          <NotaConciliacion conciliacion={parametros.conciliacion} />
          {extra}
        </>
      }
    />
  );
}
