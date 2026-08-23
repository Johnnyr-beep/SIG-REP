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
function descomponer(
  valor: string | number | null | undefined,
): Decimal | null {
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
    return {
      negativo: valor.negativo,
      entero: digitos === "" ? "0" : digitos,
      fraccion: "",
    };
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

// ── Aritmética decimal sobre cadenas ─────────────────────────────────────────
//
// Existe por un caso concreto: la línea acumulada de la tendencia, que suma
// cifras **ya publicadas** para poder dibujarlas. Todo lo demás lo calcula el
// backend con `Decimal` y aquí se pinta tal cual.
//
// Se hace con dígitos sueltos —el mayor producto parcial es 9×9 más acarreos,
// un entero de dos cifras— y nunca con el valor entero. Un «3278067652.00»
// jamás entra en un `double`, que es el paso exacto por el que se corrompen los
// importes de esta compañía. El acumulado del último día tiene que dar lo mismo
// que el total de la tabla, y con `Number` no lo daba.

/** Quita ceros a la izquierda dejando al menos un dígito. */
function sinCeros(digitos: string): string {
  const limpio = digitos.replace(/^0+(?=\d)/, "");
  return limpio === "" ? "0" : limpio;
}

/** Compara dos cadenas de dígitos por magnitud, sin convertirlas a número. */
function compararDigitos(a: string, b: string): -1 | 0 | 1 {
  const x = sinCeros(a);
  const y = sinCeros(b);
  if (x.length !== y.length) return x.length < y.length ? -1 : 1;
  if (x === y) return 0;
  return x < y ? -1 : 1;
}

function sumarDigitos(a: string, b: string): string {
  const largo = Math.max(a.length, b.length);
  const x = a.padStart(largo, "0");
  const y = b.padStart(largo, "0");
  const salida: string[] = [];
  let acarreo = 0;

  for (let posicion = largo - 1; posicion >= 0; posicion -= 1) {
    const suma =
      DIGITOS.indexOf(x.charAt(posicion)) +
      DIGITOS.indexOf(y.charAt(posicion)) +
      acarreo;
    salida.unshift(DIGITOS.charAt(suma % 10));
    acarreo = suma >= 10 ? 1 : 0;
  }

  if (acarreo === 1) salida.unshift("1");
  return salida.join("");
}

/** Resta suponiendo que `mayor` no es menor que `menor`; lo garantiza el llamador. */
function restarDigitos(mayor: string, menor: string): string {
  const largo = Math.max(mayor.length, menor.length);
  const x = mayor.padStart(largo, "0");
  const y = menor.padStart(largo, "0");
  const salida: string[] = [];
  let prestamo = 0;

  for (let posicion = largo - 1; posicion >= 0; posicion -= 1) {
    let resta =
      DIGITOS.indexOf(x.charAt(posicion)) -
      DIGITOS.indexOf(y.charAt(posicion)) -
      prestamo;
    if (resta < 0) {
      resta += 10;
      prestamo = 1;
    } else {
      prestamo = 0;
    }
    salida.unshift(DIGITOS.charAt(resta));
  }

  return salida.join("");
}

function multiplicarDigitos(a: string, b: string): string {
  const x = sinCeros(a);
  const y = sinCeros(b);
  const salida = new Array<number>(x.length + y.length).fill(0);

  for (let i = x.length - 1; i >= 0; i -= 1) {
    const digitoA = DIGITOS.indexOf(x.charAt(i));
    let acarreo = 0;

    for (let j = y.length - 1; j >= 0; j -= 1) {
      const posicion = i + j + 1;
      const suma =
        (salida[posicion] ?? 0) +
        digitoA * DIGITOS.indexOf(y.charAt(j)) +
        acarreo;
      salida[posicion] = suma % 10;
      acarreo = (suma - (suma % 10)) / 10;
    }

    // La posición `i` no la tocó ninguna vuelta anterior —cada una escribe de
    // `i+1` hacia la derecha—, así que el acarreo cabe ahí sin normalizar nada.
    salida[i] = (salida[i] ?? 0) + acarreo;
  }

  return sinCeros(salida.join(""));
}

/** Recompone un `Decimal` a partir de sus dígitos y de dónde cae la coma. */
function partir(digitos: string, decimales: number, negativo: boolean): Decimal {
  const relleno = digitos.padStart(decimales + 1, "0");
  const corte = relleno.length - decimales;
  return {
    negativo,
    entero: sinCeros(relleno.slice(0, corte)),
    fraccion: decimales === 0 ? "" : relleno.slice(corte),
  };
}

function sumarPartes(a: Decimal, b: Decimal): Decimal {
  const decimales = Math.max(a.fraccion.length, b.fraccion.length);
  const x = a.entero + a.fraccion.padEnd(decimales, "0");
  const y = b.entero + b.fraccion.padEnd(decimales, "0");

  if (a.negativo === b.negativo)
    return partir(sumarDigitos(x, y), decimales, a.negativo);

  // Signos distintos: manda el de mayor magnitud. La igualdad se resuelve
  // aparte para no publicar un «-0» donde el resultado es cero.
  const orden = compararDigitos(x, y);
  if (orden === 0) return partir("0", decimales, false);
  return orden > 0
    ? partir(restarDigitos(x, y), decimales, a.negativo)
    : partir(restarDigitos(y, x), decimales, b.negativo);
}

function multiplicarPartes(a: Decimal, b: Decimal): Decimal {
  return partir(
    multiplicarDigitos(a.entero + a.fraccion, b.entero + b.fraccion),
    a.fraccion.length + b.fraccion.length,
    a.negativo !== b.negativo,
  );
}

/**
 * División entre un entero pequeño, por el algoritmo de la escuela.
 *
 * El divisor siempre es un contador de la propia pantalla —cuántos días se
 * dibujan—, así que «resto por diez más un dígito» ni se acerca al límite de los
 * enteros exactos de JavaScript.
 */
function dividirPartes(
  valor: Decimal,
  divisor: number,
  decimales: number,
): Decimal | null {
  if (!Number.isInteger(divisor) || divisor <= 0) return null;

  // Un decimal más de los pedidos: es el que mira `redondear` para decidir.
  const escala = Math.max(valor.fraccion.length, decimales + 1);
  const dividendo = valor.entero + valor.fraccion.padEnd(escala, "0");

  const cociente: string[] = [];
  let resto = 0;
  for (const caracter of dividendo) {
    const actual = resto * 10 + DIGITOS.indexOf(caracter);
    cociente.push(DIGITOS.charAt((actual - (actual % divisor)) / divisor));
    resto = actual % divisor;
  }

  return redondear(partir(cociente.join(""), escala, valor.negativo), decimales);
}

/**
 * Vuelve al formato de la API (`-1234.50`), no al de pantalla.
 *
 * El resultado de una suma tiene que poder volver a entrar en `dinero`, `kilos`
 * o `porMedida`, y esas esperan lo que envía el backend: punto decimal y sin
 * separador de miles.
 */
function componerCrudo(valor: Decimal): string {
  const signo = valor.negativo && !esCero(valor) ? "-" : "";
  const decimales = valor.fraccion === "" ? "" : `.${valor.fraccion}`;
  return `${signo}${valor.entero}${decimales}`;
}

/**
 * Suma dos importes tal como llegan de la API, sin pasar por `number`.
 *
 * `null` significa «no aporta», no «cero»: sumar un día sin venta registrada
 * devuelve el acumulado intacto, que es lo que mantiene plana la línea de la
 * tendencia en lugar de dibujar una caída que no ocurrió.
 */
export function sumar(
  a: string | null | undefined,
  b: string | null | undefined,
): string | null {
  const izquierda = descomponer(a);
  const derecha = descomponer(b);
  if (!izquierda) return derecha ? componerCrudo(derecha) : null;
  if (!derecha) return componerCrudo(izquierda);
  return componerCrudo(sumarPartes(izquierda, derecha));
}

/** Producto de dos decimales de la API. `null` si falta cualquiera de los dos. */
export function multiplicar(
  a: string | null | undefined,
  b: string | null | undefined,
): string | null {
  const izquierda = descomponer(a);
  const derecha = descomponer(b);
  if (!izquierda || !derecha) return null;
  return componerCrudo(multiplicarPartes(izquierda, derecha));
}

/**
 * `valor × veces ÷ partes`, para repartir una cifra publicada entre N tramos.
 *
 * Con `veces === partes` devuelve el valor de vuelta —la división deshace la
 * multiplicación—, y de ahí sale la propiedad que importa: el último punto de
 * una serie repartida coincide con la cifra que la originó, en vez de quedar a
 * unos pesos por acumulación de redondeos.
 */
export function repartir(
  valor: string | null | undefined,
  veces: number,
  partes: number,
  decimales = 2,
): string | null {
  const partido = descomponer(valor);
  if (!partido) return null;
  if (!Number.isInteger(veces) || veces < 0) return null;

  const escalado = multiplicarPartes(partido, {
    negativo: false,
    entero: String(veces),
    fraccion: "",
  });
  const dividido = dividirPartes(escalado, partes, decimales);
  return dividido === null ? null : componerCrudo(dividido);
}

function formatear(
  valor: string | number | null | undefined,
  decimales: number,
  posicionesDesplazadas = 0,
): string | null {
  const partes = descomponer(valor);
  if (!partes) return null;
  const desplazado =
    posicionesDesplazadas === 0
      ? partes
      : desplazar(partes, posicionesDesplazadas);
  return componer(redondear(desplazado, decimales));
}

// ── Importes y cantidades ────────────────────────────────────────────────────

/** Pesos colombianos. Sin decimales por defecto: en tablas solo estorban. */
export function dinero(
  valor: string | null | undefined,
  decimales = 0,
): string {
  const texto = formatear(valor, decimales);
  return texto === null ? SIN_DATO : `$${ESPACIO_FIJO}${texto}`;
}

/** Kilos. El negocio los lee sin decimales salvo que se pidan explícitamente. */
export function kilos(valor: string | null | undefined, decimales = 0): string {
  const texto = formatear(valor, decimales);
  return texto === null ? SIN_DATO : `${texto}${ESPACIO_FIJO}kg`;
}

/** Número simple, sin unidad. */
export function numero(
  valor: string | number | null | undefined,
  decimales = 0,
): string {
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
  return medida === "kilos"
    ? kilos(valor, decimales)
    : dinero(valor, decimales);
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
      const resto =
        recorte > 0
          ? digitos.slice(recorte)
          : digitos.padStart(posiciones, "0");
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
export function porcentaje(
  valor: string | null | undefined,
  decimales = 1,
): string {
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
export function puntos(
  valor: string | null | undefined,
  decimales = 1,
): string {
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
const MES_LARGO = new Intl.DateTimeFormat("es-CO", {
  month: "long",
  year: "numeric",
});

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

const MES_CORTO = new Intl.DateTimeFormat("es-CO", { month: "short" });

/** `2026-08` → `ago`. Para notas donde el año se sobreentiende por el contexto. */
export function mesCorto(periodo: string | null | undefined): string {
  if (!periodo) return SIN_DATO;
  const partes = /^(\d{4})-(\d{2})/.exec(periodo);
  if (!partes) return periodo;
  const fechaMes = new Date(Number(partes[1]), Number(partes[2]) - 1, 1);
  return MES_CORTO.format(fechaMes).replace(".", "");
}

// ── Aritmética de fechas ─────────────────────────────────────────────────────
//
// El rango `desde`/`hasta` del reporte diario obliga a contar días y a desplazar
// fechas en el propio selector, para que un rango inválido no llegue siquiera a
// enviarse. Es aritmética de calendario, no de importes: aquí `number` es la
// herramienta correcta y la regla de «nunca un float» de este módulo no aplica.

/** El día de hoy en `YYYY-MM-DD`, en hora local (no UTC: eso corre la fecha). */
export function fechaHoy(): string {
  const hoy = new Date();
  return `${hoy.getFullYear()}-${String(hoy.getMonth() + 1).padStart(2, "0")}-${String(
    hoy.getDate(),
  ).padStart(2, "0")}`;
}

/**
 * El período al que pertenece una fecha: su prefijo `YYYY-MM`.
 *
 * Es la regla que el contrato fija para cruzar cada día con la línea de
 * referencia de **su** mes cuando el rango cruza de mes. Deliberadamente no
 * construye un `Date`: el prefijo de la cadena ya es la respuesta y así no hay
 * huso horario que la corra un día.
 */
export function periodoDeFecha(iso: string | null | undefined): string | null {
  if (!iso) return null;
  return /^\d{4}-\d{2}/.test(iso) ? iso.slice(0, 7) : null;
}

/** Descompone `YYYY-MM-DD` en sus tres números, o `null` si no lo es. */
function partesDeFecha(
  iso: string | null | undefined,
): [number, number, number] | null {
  if (!iso) return null;
  const partes = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!partes) return null;
  return [Number(partes[1]), Number(partes[2]), Number(partes[3])];
}

/**
 * Desplaza una fecha un número de días, hacia adelante o hacia atrás.
 *
 * Se apoya en `Date.UTC` y no en el constructor local: mediodía UTC en un huso
 * fijo como el colombiano da siempre el mismo día, y el desbordamiento de mes y
 * de año lo resuelve el propio calendario.
 */
export function sumarDias(iso: string, dias: number): string {
  const partes = partesDeFecha(iso);
  if (!partes) return iso;
  const [anio, mes, dia] = partes;
  const desplazada = new Date(Date.UTC(anio, mes - 1, dia + dias));
  return desplazada.toISOString().slice(0, 10);
}

/** El último día de un período `YYYY-MM`. `2026-02` → `2026-02-28`. */
export function finDeMes(periodo: string | null | undefined): string | null {
  if (!periodo) return null;
  const partes = /^(\d{4})-(\d{2})$/.exec(periodo);
  if (!partes) return null;
  // El día 0 del mes siguiente es el último del pedido, y el calendario resuelve
  // solo los febreros bisiestos.
  return new Date(Date.UTC(Number(partes[1]), Number(partes[2]), 0))
    .toISOString()
    .slice(0, 10);
}

/**
 * Días que abarca un rango, **contando los dos extremos**.
 *
 * `2026-08-01` a `2026-08-01` es un día, no cero: es la cuenta que usa el tope
 * de 92 del contrato («92 entran, 93 no»). Devuelve un número negativo si el
 * rango está invertido, que es justo lo que el selector necesita detectar.
 */
export function diasDelRango(desde: string, hasta: string): number | null {
  const inicio = partesDeFecha(desde);
  const fin = partesDeFecha(hasta);
  if (!inicio || !fin) return null;
  const a = Date.UTC(inicio[0], inicio[1] - 1, inicio[2]);
  const b = Date.UTC(fin[0], fin[1] - 1, fin[2]);
  return Math.round((b - a) / 86_400_000) + 1;
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
  if (referencia === null || referencia === undefined || referencia === "")
    return null;
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
