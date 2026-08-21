/**
 * Vocabulario de la unidad Agropecuaria en la interfaz.
 *
 * Traduce los ejes y las dimensiones del contrato a lo que lee la gerencia, y
 * concentra las dos reglas que la pantalla necesita consultar en más de un
 * sitio: qué ejes tienen meta contra la que medir y cuáles no, y qué eje llega
 * sin identificador propio.
 *
 * Fuente: `backend/app/infrastructure/models/agro_vocabulario.py`.
 */

import type {
  DimensionPresupuestoAgro,
  EjeCruceAgro,
  EjeResumenAgro,
} from "@/api/tiposAgro";

// ── Ejes del resumen ─────────────────────────────────────────────────────────

export interface OpcionEje {
  valor: EjeResumenAgro;
  etiqueta: string;
  /** Cómo se llama una fila de este eje, en singular y en minúscula. */
  singular: string;
  ayuda: string;
}

/**
 * Los siete ejes, en el orden en que el negocio los pidió.
 *
 * Una sola pantalla los sirve a los siete —no siete pantallas—: la tabla es la
 * misma, lo único que cambia es por dónde se agrupa. Siete copias del mismo
 * archivo serían siete sitios donde arreglar la próxima columna.
 */
export const EJES_RESUMEN: readonly OpcionEje[] = [
  {
    valor: "centro_operacion",
    etiqueta: "Centro de operación",
    singular: "centro",
    ayuda: "Planta y Montería. Es la unidad que tiene calendario propio.",
  },
  {
    valor: "especie",
    etiqueta: "Especie",
    singular: "especie",
    ayuda: "RES, CERDO, CARNES FRIAS… El animal, no el corte.",
  },
  {
    valor: "tipo_comercial",
    etiqueta: "Tipo comercial",
    singular: "tipo comercial",
    ayuda: "CORTE, CANAL, SUBPRODUCTO, SACRIFICIO, DESPOSTE, LOGISTICA…",
  },
  {
    valor: "vendedor",
    etiqueta: "Vendedor",
    singular: "vendedor",
    ayuda: "La clave es la cédula o el NIT de quien factura.",
  },
  {
    valor: "tipo_item",
    etiqueta: "Tipo de ítem",
    singular: "tipo de ítem",
    ayuda:
      "BIENES y SERVICIOS. El impuesto se ingiere pero no suma en ningún total.",
  },
  {
    valor: "grupo",
    etiqueta: "Grupo",
    singular: "grupo",
    ayuda:
      "La letra de la línea comercial. Una parte de la venta llega sin grupo.",
  },
  {
    valor: "cliente",
    etiqueta: "Cliente",
    singular: "cliente",
    ayuda:
      "Cientos de miembros. La fuente no entrega NIT ni código de cliente.",
  },
];

export function esEjeResumen(valor: string | null): valor is EjeResumenAgro {
  return EJES_RESUMEN.some((eje) => eje.valor === valor);
}

export function opcionDeEje(eje: EjeResumenAgro): OpcionEje {
  // El `??` no es defensa contra un eje inexistente —`esEjeResumen` ya filtró—
  // sino contra `noUncheckedIndexedAccess`, que tipa todo `find` como opcional.
  return (
    EJES_RESUMEN.find((opcion) => opcion.valor === eje) ?? EJES_RESUMEN[0]!
  );
}

/**
 * La dimensión de presupuesto de un eje, si la tiene.
 *
 * `null` en cliente, grupo y tipo de ítem: son ejes de **lectura** y no de
 * meta. Nadie presupuesta 686 clientes. La pantalla pregunta aquí en lugar de
 * deducirlo mirando si `presupuesto` llegó vacío, porque eso confundiría «este
 * eje no se presupuesta» con «este miembro todavía no tiene meta capturada»,
 * que son dos cosas distintas y se explican distinto.
 */
export function dimensionDeEje(
  eje: EjeResumenAgro,
): DimensionPresupuestoAgro | null {
  switch (eje) {
    case "centro_operacion":
    case "especie":
    case "tipo_comercial":
    case "vendedor":
      return eje;
    default:
      return null;
  }
}

/**
 * ¿Este eje llega sin identificador propio?
 *
 * En el eje cliente `clave` y `nombre` son el mismo texto: la fuente no entrega
 * NIT ni código de cliente, y es la única dimensión en esa situación. La tabla
 * no pinta columna de clave ahí, porque sería la misma cadena repetida al lado.
 * Está pedido al administrador de la API; hasta entonces esto no es un dato que
 * falte cargar, es un dato que la fuente no da.
 */
export function ejeSinClavePropia(eje: EjeResumenAgro): boolean {
  return eje === "cliente";
}

// ── Cruces ───────────────────────────────────────────────────────────────────

export const EJES_CRUCE: readonly {
  valor: EjeCruceAgro;
  etiqueta: string;
  ayuda: string;
}[] = [
  {
    valor: "vendedor-cliente",
    etiqueta: "Vendedor × cliente",
    ayuda: "Qué le vendió cada vendedor a cada cliente.",
  },
  {
    valor: "vendedor-cliente-producto",
    etiqueta: "Vendedor × cliente × producto",
    ayuda: "El mismo cruce abierto por producto. Es el que más se trunca.",
  },
];

export function esEjeCruce(valor: string | null): valor is EjeCruceAgro {
  return valor === "vendedor-cliente" || valor === "vendedor-cliente-producto";
}

// ── Dimensiones de presupuesto ───────────────────────────────────────────────

export const DIMENSIONES_PRESUPUESTO: readonly {
  valor: DimensionPresupuestoAgro;
  etiqueta: string;
}[] = [
  { valor: "centro_operacion", etiqueta: "Centro de operación" },
  { valor: "especie", etiqueta: "Especie" },
  { valor: "tipo_comercial", etiqueta: "Tipo comercial" },
  { valor: "vendedor", etiqueta: "Vendedor" },
];

export function esDimensionPresupuesto(
  valor: string | null,
): valor is DimensionPresupuestoAgro {
  return DIMENSIONES_PRESUPUESTO.some((dimension) => dimension.valor === valor);
}

/** Nombre legible de una dimensión que llega como cadena suelta del backend. */
export function etiquetaDimension(dimension: string): string {
  return (
    DIMENSIONES_PRESUPUESTO.find((opcion) => opcion.valor === dimension)
      ?.etiqueta ?? dimension
  );
}

/** Nombre legible de un eje de cruce que llega como cadena suelta. */
export function etiquetaEjeCrudo(eje: string): string {
  const resumen = EJES_RESUMEN.find((opcion) => opcion.valor === eje);
  if (resumen) return resumen.etiqueta;
  return eje === "item" ? "Producto" : eje;
}

// ── Fórmulas ─────────────────────────────────────────────────────────────────

/**
 * Respaldo de las fórmulas de agro.
 *
 * **La versión que manda es la que envía el backend** en
 * `parametros_calculo.formulas`: son las de la especificación, escritas por
 * quien las implementó, y publicarlas tal cual es todo el punto de §4.2. Este
 * diccionario solo cubre el caso de que una respuesta llegue sin ellas, para
 * que la pista de una columna no quede muda.
 */
export const FORMULAS_AGRO: Record<string, string> = {
  venta: "venta = Σ TotalNeto de las líneas cuyo TipoItem no es IMPUESTO",
  cumplimiento:
    "cumplimiento = venta ÷ presupuesto, dentro de una sola dimensión",
  ideal: "ideal = días trabajados ÷ días hábiles del centro",
  brecha: "brecha = cumplimiento − ideal",
  proyeccion: "proyección = (venta ÷ días trabajados) × días hábiles",
  cumplimiento_proyectado: "cumplimiento proyectado = proyección ÷ presupuesto",
  venta_diaria_promedio: "venta diaria promedio = venta ÷ días trabajados",
  venta_diaria_requerida:
    "venta diaria requerida = (presupuesto − venta) ÷ (días hábiles − días trabajados)",
  margen_valor:
    "margen = Σ TotalNeto − Σ TotalCosto; indefinido si alguna línea no tiene costo",
  margen_porcentaje: "margen % = margen ÷ Σ TotalNeto",
  participacion: "participación = venta de la fila ÷ venta total del corte",
  presupuesto_diario:
    "presupuesto diario = presupuesto mensual del centro ÷ días hábiles",
};

/**
 * La fórmula de un indicador: la del backend si llegó, si no la de respaldo.
 *
 * El orden importa y no es negociable: un número acompañado de la fórmula
 * equivocada es peor que un número sin fórmula.
 */
export function formulaDe(
  formulas: Record<string, string> | null | undefined,
  clave: string,
): string | undefined {
  return formulas?.[clave] ?? FORMULAS_AGRO[clave];
}
