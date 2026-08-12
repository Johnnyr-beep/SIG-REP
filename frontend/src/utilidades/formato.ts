/**
 * Formato de importes, cantidades, porcentajes y fechas.
 *
 * ── Por qué este módulo no usa `Number` ──────────────────────────────────────
 *
 * La API entrega los importes como cadena decimal (`"3278067652.00"`) porque son
 * montos de miles de millones de pesos y el `double` de JavaScript los corrompe:
 * a partir de 2^53 la representación deja de ser exacta y, mucho antes, las
 * fracciones binarias introducen errores al redondear (`1.005` no es `1.005`).
 *
 * Por eso todo el formateo de aquí es **manipulación de cadenas**: se descompone
 * el decimal en signo, parte entera y parte decimal; se redondea desplazando y
 * acarreando dígitos a mano; y se reagrupa con el separador colombiano. En
 * ningún punto del camino el valor pasa por un `float`.
 *
 * La única función que devuelve un `number` es `proporcionParaGrafico`, y es
 * explícitamente para geometría de un SVG —el ancho de una barra en píxeles—,
 * jamás para un dato que el usuario lea como cifra.
 *
 * Formato colombiano: separador de miles «.», decimal «,», moneda COP sin
 * decimales en tablas.
 */

/** Lo que se pinta cuando un indicador es `null`, vacío o indefinido. */
export const SIN_DATO = "—";

const DIGITOS = "0123456789";
const ESPACIO_FIJO = " ";

interface Decimal {
  negativo: boolean;
  /** Parte entera, solo dígitos. */
  entero: string;
  /** Parte decimal, solo dígitos, sin el punto. */
  fraccion: string;
}

/**
 * Convierte la cadena de la API en sus tres piezas.
 *
 * Devuelve `null` ante cualquier entrada que no sea un decimal reconocible
 * —incluidos `null`, `undefined`, `""` y basura— para que el llamador pinte
 * «—» en lugar de arriesgar un «NaN» en pantalla.
 */
function descomponer(valor: string | number | null | undefined): Decimal | null {
  if (valor === null || valor === undefined) return null;

  const texto = String(valor).trim();
  if (texto === "") return null;

  const partes = /^([+-]?)(\d*)(?:[.,](\d*))?$/.exec(texto);
  if (!partes) return null;

  const signo = partes[1] ?? "";
  const entero = partes[2] ?? "";
  const fraccion = partes[3] ?? "";
  if (entero === "" && fraccion === "") return null;

  return {
    negativo: signo === "-",
    entero: entero === "" ? "0" : entero,
    fraccion,
  };
}

/** Suma uno a una cadena de dígitos propagando el acarreo. Sin aritmética real. */
function incrementar(digitos: string): string {
  const salida = digitos.split("");
  let posicion = salida.length - 1;

  while (posicion >= 0) {
    const digito = salida[posicion] ?? "0";
    if (digito === "9") {
      salida[posicion] = "0";
      posicion -= 1;
    } else {
      salida[posicion] = DIGITOS.charAt(DIGITOS.indexOf(digito) + 1);
      break;
    }
  }

  if (posicion < 0) salida.unshift("1");
  return salida.join("");
}

/**
 * Redondea a `decimales` posiciones por el método comercial (medio arriba).
 *
 * Trabaja sobre la concatenación de entero y decimales conservados: sumar uno a
 * esa cadena resuelve de una vez el acarreo entre ambas partes (`9,97` → `10,0`).
 */
function redondear(valor: Decimal, decimales: number): Decimal {
  const conservados = valor.fraccion.slice(0, decimales).padEnd(decimales, "0");
  const siguiente = valor.fraccion.charAt(decimales);

  let digitos = valor.entero + conservados;
  if (siguiente !== "" && siguiente >= "5") digitos = incrementar(digitos);

  if (decimales === 0) {
    return { negativo: valor.negativo, entero: digitos === "" ? "0" : digitos, fraccion: "" };
  }

  const corte = digitos.length - decimales;
  const entero = digitos.slice(0, corte);
  return {
    negativo: valor.negativo,
    entero: entero === "" ? "0" : entero,
    fraccion: digitos.slice(corte),
  };
}

/** Desplaza la coma `posiciones` lugares a la derecha: multiplicar por 10^n. */
function desplazar(valor: Decimal, posiciones: number): Decimal {
  const fraccion = valor.fraccion.padEnd(posiciones, "0");
  return {
    negativo: valor.negativo,
    entero: valor.entero + fraccion.slice(0, posiciones),
    fraccion: fraccion.slice(posiciones),
  };
}

/** `5396105548` → `5.396.105.548`. */
function agruparMiles(entero: string): string {
  const limpio = entero.replace(/^0+(?=\d)/, "");
  return limpio.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
}

function esCero(valor: Decimal): boolean {
  return /^0*$/.test(valor.entero) && /^0*$/.test(valor.fraccion);
}

/** Arma el texto final. El signo se omite en el cero para no mostrar «-0». */
function componer(valor: Decimal): string {
  const signo = valor.negativo && !esCero(valor) ? "-" : "";
  const decimales = valor.fraccion === "" ? "" : `,${valor.fraccion}`;
  return `${signo}${agruparMiles(valor.entero)}${decimales}`;
}

function formatear(
  valor: string | number | null | undefined,
  decimales: number,
  posicionesDesplazadas = 0,
): string | null {
  const partes = descomponer(valor);
  if (!partes) return null;
  const desplazado = posicionesDesplazadas === 0 ? partes : desplazar(partes, posicionesDesplazadas);
  return componer(redondear(desplazado, decimales));
}

// ── Importes y cantidades ────────────────────────────────────────────────────

/** Pesos colombianos. Sin decimales por defecto: en tablas solo estorban. */
export function dinero(valor: string | null | undefined, decimales = 0): string {
  const texto = formatear(valor, decimales);
  return texto === null ? SIN_DATO : `$${ESPACIO_FIJO}${texto}`;
}

/** Kilos. El negocio los lee sin decimales salvo que se pidan explícitamente. */
export function kilos(valor: string | null | undefined, decimales = 0): string {
  const texto = formatear(valor, decimales);
  return texto === null ? SIN_DATO : `${texto}${ESPACIO_FIJO}kg`;
}

/** Número simple, sin unidad. */
export function numero(valor: string | number | null | undefined, decimales = 0): string {
  return formatear(valor, decimales) ?? SIN_DATO;
}

/**
 * Formatea según la medida activa de la pantalla.
 *
 * El mismo campo de la API es dinero o kilos según el parámetro `medida` de la
 * consulta; centralizarlo evita que una tabla muestre kilos con el signo peso.
 */
export function porMedida(
  valor: string | null | undefined,
  medida: "valor" | "kilos",
  decimales = 0,
): string {
  return medida === "kilos" ? kilos(valor, decimales) : dinero(valor, decimales);
}

/** Importe abreviado para tarjetas: `$ 5.396 M`. Conserva el orden de magnitud. */
export function dineroCorto(valor: string | null | undefined): string {
  const partes = descomponer(valor);
  if (!partes) return SIN_DATO;

  const digitos = partes.entero.replace(/^0+(?=\d)/, "");
  const escalas: [number, string][] = [
    [10, "MM"], // billones (millones de millones)
    [7, "M"], // millones
    [4, "K"], // miles
  ];

  for (const escala of escalas) {
    const [minimo, sufijo] = escala;
    if (digitos.length >= minimo) {
      const posiciones = sufijo === "MM" ? 12 : sufijo === "M" ? 6 : 3;
      const recorte = digitos.length - posiciones;
      const entero = recorte > 0 ? digitos.slice(0, recorte) : "0";
      const resto = recorte > 0 ? digitos.slice(recorte) : digitos.padStart(posiciones, "0");
      const reducido = redondear(
        { negativo: partes.negativo, entero, fraccion: resto },
        digitos.length - posiciones >= 4 ? 0 : 1,
      );
      return `$${ESPACIO_FIJO}${componer(reducido)}${ESPACIO_FIJO}${sufijo}`;
    }
  }

  return dinero(valor);
}

// ── Porcentajes ──────────────────────────────────────────────────────────────

/**
 * La API envía fracciones (`"0.2885"`); la gerencia lee porcentajes (`28,9 %`).
 * La conversión es un desplazamiento de la coma, no una multiplicación.
 */
export function porcentaje(valor: string | null | undefined, decimales = 1): string {
  const texto = formatear(valor, decimales, 2);
  return texto === null ? SIN_DATO : `${texto}${ESPACIO_FIJO}%`;
}

/**
 * Diferencia entre dos porcentajes, en puntos porcentuales.
 *
 * La brecha de §4.1 es `cumplimiento − ideal`: llamarla «%» induce a leerla como
 * una variación relativa, que es otra cosa. Lleva signo explícito porque su
 * lectura entera es «cuánto voy por encima o por debajo de lo que tocaba».
 */
export function puntos(valor: string | null | undefined, decimales = 1): string {
  const partes = descomponer(valor);
  if (!partes) return SIN_DATO;

  const texto = componer(redondear(desplazar(partes, 2), decimales));
  const signo = partes.negativo || texto.startsWith("-") ? "" : "+";
  return `${signo}${texto}${ESPACIO_FIJO}pp`;
}

/** Días hábiles y trabajados: siempre con un decimal, porque existen medias jornadas. */
export function dias(valor: string | null | undefined): string {
  return formatear(valor, 1) ?? SIN_DATO;
}

// ── Fechas ───────────────────────────────────────────────────────────────────

/**
 * Convierte `YYYY-MM-DD` a fecha local.
 *
 * `new Date("2026-08-09")` se interpreta como medianoche UTC y en Colombia
 * (UTC−5) se muestra como el 8 de agosto. Un reporte con la fecha de corte
 * corrida un día es un reporte que alguien va a malinterpretar, así que la
 * fecha se construye componente a componente.
 */
function aFechaLocal(iso: string): Date | null {
  const partes = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!partes) {
    const suelta = new Date(iso);
    return Number.isNaN(suelta.getTime()) ? null : suelta;
  }
  const anio = Number(partes[1]);
  const mes = Number(partes[2]);
  const dia = Number(partes[3]);
  const fecha = new Date(anio, mes - 1, dia);
  return Number.isNaN(fecha.getTime()) ? null : fecha;
}

const FECHA_CORTA = new Intl.DateTimeFormat("es-CO", {
  day: "2-digit",
  month: "short",
  year: "numeric",
});

const FECHA_LARGA = new Intl.DateTimeFormat("es-CO", {
  weekday: "long",
  day: "numeric",
  month: "long",
  year: "numeric",
});

const FECHA_HORA = new Intl.DateTimeFormat("es-CO", {
  day: "2-digit",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

const DIA_SEMANA = new Intl.DateTimeFormat("es-CO", { weekday: "short" });
const MES_LARGO = new Intl.DateTimeFormat("es-CO", { month: "long", year: "numeric" });

export function fecha(iso: string | null | undefined): string {
  if (!iso) return SIN_DATO;
  const valor = aFechaLocal(iso);
  return valor ? FECHA_CORTA.format(valor) : SIN_DATO;
}

export function fechaLarga(iso: string | null | undefined): string {
  if (!iso) return SIN_DATO;
  const valor = aFechaLocal(iso);
  return valor ? FECHA_LARGA.format(valor) : SIN_DATO;
}

export function fechaHora(iso: string | null | undefined): string {
  if (!iso) return SIN_DATO;
  const valor = new Date(iso);
  return Number.isNaN(valor.getTime()) ? SIN_DATO : FECHA_HORA.format(valor);
}

/** Encabezado de columna de la matriz diaria: `mar 12`. */
export function diaDelMes(iso: string | null | undefined): string {
  if (!iso) return SIN_DATO;
  const valor = aFechaLocal(iso);
  if (!valor) return SIN_DATO;
  return `${DIA_SEMANA.format(valor).replace(".", "")} ${valor.getDate()}`;
}

/** `true` si la fecha cae en domingo; la matriz diaria los resalta. */
export function esDomingo(iso: string | null | undefined): boolean {
  if (!iso) return false;
  const valor = aFechaLocal(iso);
  return valor !== null && valor.getDay() === 0;
}

/** `2026-08` → `agosto de 2026`. */
export function periodoLargo(periodo: string | null | undefined): string {
  if (!periodo) return SIN_DATO;
  const partes = /^(\d{4})-(\d{2})$/.exec(periodo);
  if (!partes) return periodo;
  const fechaMes = new Date(Number(partes[1]), Number(partes[2]) - 1, 1);
  return MES_LARGO.format(fechaMes);
}

/** El período del mes en curso, en formato `YYYY-MM`. */
export function periodoActual(): string {
  const hoy = new Date();
  return `${hoy.getFullYear()}-${String(hoy.getMonth() + 1).padStart(2, "0")}`;
}

// ── Geometría de gráficos ────────────────────────────────────────────────────

/**
 * Proporción 0–1 para dibujar. **Solo para geometría.**
 *
 * Es el único punto del frontend donde un importe se convierte a `number`, y el
 * resultado no se muestra jamás: alimenta el ancho de una barra o la coordenada
 * de un trazo, donde un error en el decimoquinto decimal no existe a efectos de
 * píxeles. Ninguna cifra que el usuario lea sale de aquí.
 */
export function proporcionParaGrafico(
  valor: string | number | null | undefined,
  maximo = 1,
): number {
  if (valor === null || valor === undefined || valor === "") return 0;
  const cifra = Number(valor);
  if (!Number.isFinite(cifra) || maximo === 0) return 0;
  return Math.min(1, Math.max(0, cifra / maximo));
}

/** Comparación laxa para decidir un adorno visual (nunca para calcular una cifra). */
export function comparaParaGrafico(
  valor: string | null | undefined,
  referencia: string | null | undefined,
): -1 | 0 | 1 | null {
  if (valor === null || valor === undefined || valor === "") return null;
  if (referencia === null || referencia === undefined || referencia === "") return null;
  const a = Number(valor);
  const b = Number(referencia);
  if (!Number.isFinite(a) || !Number.isFinite(b)) return null;
  if (a > b) return 1;
  if (a < b) return -1;
  return 0;
}

/** Convierte `SIN_PRESUPUESTO` en `Sin presupuesto`. */
export function humanizar(codigo: string): string {
  const texto = codigo.replaceAll("_", " ").toLowerCase();
  return texto.charAt(0).toUpperCase() + texto.slice(1);
}
