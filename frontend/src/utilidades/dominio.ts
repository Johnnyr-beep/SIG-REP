/**
 * Vocabulario del negocio en la interfaz.
 *
 * Traduce los códigos del contrato a lo que la gerencia lee, y resuelve las
 * referencias de catálogo que el contrato deja abiertas (texto suelto u objeto).
 */

import type { CorteClientes, Medida, ReferenciaSimple, Semaforo } from "@/api/tipos";

// ── Referencias de catálogo ──────────────────────────────────────────────────

/** Nombre presentable de una referencia, venga como texto o como objeto. */
export function etiquetaDe(referencia: ReferenciaSimple | null | undefined): string {
  if (referencia === null || referencia === undefined) return "—";
  if (typeof referencia === "string") return referencia;
  return referencia.nombre ?? referencia.codigo_co ?? referencia.codigo ?? "—";
}

/** Código de la referencia, si viaja. `null` cuando solo llegó el nombre. */
export function codigoDe(referencia: ReferenciaSimple | null | undefined): string | null {
  if (referencia === null || referencia === undefined) return null;
  if (typeof referencia === "string") return null;
  return referencia.codigo_co ?? referencia.codigo ?? null;
}

/** Identificador estable para usar como `key` de React. */
export function claveDe(referencia: ReferenciaSimple | null | undefined, respaldo: string): string {
  return codigoDe(referencia) ?? etiquetaDe(referencia) ?? respaldo;
}

// ── Semáforo ─────────────────────────────────────────────────────────────────

/**
 * Presentación del semáforo **sin depender del color**.
 *
 * Uno de cada doce hombres tiene alguna deficiencia en la visión del color, y
 * esta pantalla la mira la gerencia en un proyector y en un teléfono. Cada
 * estado lleva por tanto un símbolo de forma distinta —no solo un tono— y un
 * texto que lo nombra; el color es el tercer refuerzo, nunca el único.
 */
export interface AspectoSemaforo {
  simbolo: string;
  etiqueta: string;
  /** Lectura completa para el lector de pantalla. */
  descripcion: string;
  tono: "exito" | "aviso" | "peligro" | "neutro";
}

const ASPECTOS: Record<Semaforo, AspectoSemaforo> = {
  VERDE: {
    simbolo: "✓",
    etiqueta: "En meta",
    descripcion: "Verde: el cumplimiento alcanza o supera el ideal del período.",
    tono: "exito",
  },
  AMARILLO: {
    simbolo: "!",
    etiqueta: "En riesgo",
    descripcion: "Amarillo: el cumplimiento va por debajo del ideal pero dentro del margen tolerado.",
    tono: "aviso",
  },
  ROJO: {
    simbolo: "▼",
    etiqueta: "Atrasado",
    descripcion: "Rojo: el cumplimiento va por debajo del margen tolerado frente al ideal.",
    tono: "peligro",
  },
  SIN_PRESUPUESTO: {
    simbolo: "○",
    etiqueta: "Sin presupuesto",
    descripcion:
      "Sin presupuesto: el punto de venta registra venta pero no tiene presupuesto parametrizado, así que no hay cumplimiento que medir.",
    tono: "neutro",
  },
};

const ASPECTO_DESCONOCIDO: AspectoSemaforo = {
  simbolo: "?",
  etiqueta: "Sin clasificar",
  descripcion: "El backend devolvió un estado de semáforo que esta versión no conoce.",
  tono: "neutro",
};

export function aspectoSemaforo(estado: Semaforo | null | undefined): AspectoSemaforo {
  if (!estado) return ASPECTO_DESCONOCIDO;
  return ASPECTOS[estado] ?? ASPECTO_DESCONOCIDO;
}

// ── Medida ───────────────────────────────────────────────────────────────────

export const MEDIDAS: { valor: Medida; etiqueta: string; ayuda: string }[] = [
  { valor: "valor", etiqueta: "Pesos", ayuda: "Venta y presupuesto en pesos colombianos." },
  { valor: "kilos", etiqueta: "Kilos", ayuda: "Venta y presupuesto en kilos (cantidad inventario)." },
];

export function esMedida(valor: string | null): valor is Medida {
  return valor === "valor" || valor === "kilos";
}

/** Unidad que corresponde a la medida activa, para encabezados de columna. */
export function unidadDe(medida: Medida): string {
  return medida === "kilos" ? "kg" : "$";
}

// ── Cortes del reporte de clientes ───────────────────────────────────────────

export const CORTES_CLIENTES: { valor: CorteClientes; etiqueta: string }[] = [
  { valor: "cliente", etiqueta: "Cliente" },
  { valor: "vendedor", etiqueta: "Vendedor" },
  { valor: "canal", etiqueta: "Canal" },
  { valor: "condicion_pago", etiqueta: "Condición de pago" },
];

export function esCorteClientes(valor: string | null): valor is CorteClientes {
  return (
    valor === "cliente" || valor === "vendedor" || valor === "canal" || valor === "condicion_pago"
  );
}

// ── Fórmulas ─────────────────────────────────────────────────────────────────

/**
 * Las fórmulas de §4, tal como se muestran junto a cada indicador.
 *
 * Están escritas, no escondidas en una celda: es el punto entero del sistema
 * frente al Excel que reemplaza.
 */
export const FORMULAS: Record<string, string> = {
  cumplimiento: "cumplimiento = venta ÷ presupuesto",
  // En una fila de un solo punto de venta el ideal es «días trabajados ÷ días
  // hábiles» y se rehace a mano con los días que muestra el pie. En un grupo o
  // en el consolidado, que abarcan zonas con calendarios distintos, se pondera
  // el ideal de cada zona por su presupuesto: promediar los días y dividir
  // después daría otro número. El backend envía la fórmula vigente en
  // `parametros_calculo.formulas`, que es la que manda sobre este texto.
  ideal:
    "ideal = días trabajados ÷ días hábiles · en un agregado, ponderado por presupuesto de cada zona",
  brecha: "brecha = cumplimiento − ideal",
  proyeccion: "proyección = (venta ÷ días trabajados) × días hábiles",
  cumplimiento_proyectado: "cumplimiento proyectado = proyección ÷ presupuesto",
  venta_diaria_promedio: "venta diaria promedio = venta ÷ días trabajados",
  venta_diaria_requerida:
    "venta diaria requerida = (presupuesto − venta) ÷ (días hábiles − días trabajados)",
  crecimiento:
    "crecimiento = venta ÷ venta del año anterior − 1 · solo sobre los puntos con historia del año anterior",
  margen_valor: "margen = Σ valor subtotal − Σ costo promedio",
  margen_porcentaje: "margen % = margen ÷ venta",
  presupuesto_diario: "presupuesto diario = presupuesto mensual ÷ días hábiles",
};

/** Estados de una corrida de ingesta, con el tono con que se pintan. */
export function tonoEstadoIngesta(estado: string): "exito" | "aviso" | "peligro" | "info" {
  const normalizado = estado.toUpperCase();
  if (normalizado.includes("ERROR") || normalizado.includes("FALL")) return "peligro";
  if (normalizado.includes("PARCIAL") || normalizado.includes("ADVERT")) return "aviso";
  if (normalizado.includes("CURSO") || normalizado.includes("EJECU")) return "info";
  return "exito";
}
