/**
 * ╔══════════════════════════════════════════════════════════════════════════╗
 * ║  DATOS DE EJEMPLO — NO SON CIFRAS REALES DEL NEGOCIO                      ║
 * ╚══════════════════════════════════════════════════════════════════════════╝
 *
 * Este módulo existe solo para poder ver y revisar las pantallas mientras el
 * backend se termina. Se activa con `VITE_SIGREP_EJEMPLOS=1` y `cliente.ts` lo
 * importa de forma dinámica, así que con la variable apagada —el caso de
 * producción— este fragmento ni se descarga.
 *
 * Reglas que se respetan aquí para que el ensayo sea válido:
 *
 * 1. La estructura y los nombres de campo son exactamente los de `docs/API.md`.
 *    Si algo no se puede armar contra el contrato, es un problema del contrato,
 *    no de la pantalla.
 * 2. Todo importe sale como `string`, igual que la API real.
 * 3. La jerarquía, los códigos de C.O., las zonas y las categorías son los
 *    reales de §3 de la especificación: los nombres son verdaderos, las cifras
 *    no.
 *
 * ── Sobre la aritmética de este archivo ─────────────────────────────────────
 * Las cifras se derivan con aritmética de `number` porque aquí se está
 * *simulando* lo que el backend calcula con `Decimal`. Es el único archivo del
 * frontend que hace cuentas, y sus resultados nunca tocan un dato persistido.
 * El código de producción no calcula: formatea lo que la API ya calculó.
 */

import type { Opciones } from "./cliente";
import { ErrorApi } from "./cliente";
import type {
  CambioPresupuesto,
  Categoria,
  CorridaIngesta,
  FilaCalendario,
  FilaClientes,
  FilaGrupo,
  FilaIndicadores,
  FilaPresupuesto,
  FilaPuntoVentaReporte,
  FilaVentaDiaria,
  Grupo,
  MapeoCategoria,
  Medida,
  ParametrosCalculo,
  Periodo,
  PuntoVenta,
  RechazoIngesta,
  RespuestaClientes,
  RespuestaCumplimiento,
  RespuestaTablero,
  RespuestaVentaDiaria,
  Salud,
  Semaforo,
  TokensAcceso,
  Usuario,
  Zona,
} from "./tipos";

const PERIODO = "2026-08";
const FECHA_CORTE = "2026-08-09";

/** Umbral del semáforo de §4.1 (supuesto de §8.3, pendiente de confirmar). */
const UMBRAL_AMARILLO = 0.9;

// ── Catálogos reales de §3 ───────────────────────────────────────────────────

const GRUPOS: Grupo[] = [
  { id: 1, codigo: "001", nombre: "GRUPO 1" },
  { id: 2, codigo: "002", nombre: "GRUPO 2" },
  { id: 3, codigo: "003", nombre: "GRUPO 3" },
  { id: 4, codigo: "004", nombre: "GRUPO 4" },
];

const CATEGORIAS: Categoria[] = [
  { id: 1, codigo: "RES", nombre: "RES", orden: 1 },
  { id: 2, codigo: "CERDO", nombre: "CERDO", orden: 2 },
  { id: 3, codigo: "POLLO", nombre: "POLLO", orden: 3 },
  { id: 4, codigo: "PESCADO", nombre: "PESCADO", orden: 4 },
  { id: 5, codigo: "EMBUTIDOS", nombre: "EMBUTIDOS", orden: 5 },
  { id: 6, codigo: "VISCERAS", nombre: "VISCERAS", orden: 6 },
  { id: 7, codigo: "ASADERO", nombre: "ASADERO", orden: 7 },
  { id: 8, codigo: "OTROS", nombre: "OTROS", orden: 8 },
];

interface DefinicionPdv {
  id: number;
  codigo_co: string;
  nombre: string;
  grupo: string;
  zona: string;
  /** Presupuesto mensual en pesos. `0` = no presupuestado. */
  presupuesto: number;
  /** Cumplimiento simulado en pesos al corte. */
  factor: number;
  /** Categorías que el punto no maneja (§3.1). */
  sinCategorias?: string[];
}

const ZONA_BGA = "BUCARAMANGA Y CENTRO";
const ZONA_CTG = "CARTAGENA";
const ZONA_PEI = "PEREIRA";
const ZONA_L70 = "LA 70 / LA 43 / SIMON / LA GRANJA";
const ZONA_RESTO = "RESTO (POR CONFIRMAR)";

const PDVS: DefinicionPdv[] = [
  { id: 1, codigo_co: "402", nombre: "MALAMBO", grupo: "001", zona: ZONA_RESTO, presupuesto: 1_600_000_000, factor: 0.291 },
  { id: 2, codigo_co: "603", nombre: "CONCORDE", grupo: "001", zona: ZONA_RESTO, presupuesto: 1_100_000_000, factor: 0.244 },
  { id: 3, codigo_co: "403", nombre: "LAGRANJA", grupo: "001", zona: ZONA_L70, presupuesto: 1_350_000_000, factor: 0.302 },
  { id: 4, codigo_co: "406", nombre: "SIMON", grupo: "001", zona: ZONA_L70, presupuesto: 1_250_000_000, factor: 0.268 },
  { id: 5, codigo_co: "412", nombre: "BUCARAMANGA", grupo: "002", zona: ZONA_BGA, presupuesto: 1_500_000_000, factor: 0.281 },
  { id: 6, codigo_co: "409", nombre: "PEREIRA", grupo: "002", zona: ZONA_PEI, presupuesto: 1_200_000_000, factor: 0.252 },
  { id: 7, codigo_co: "415", nombre: "CARTAGENA", grupo: "002", zona: ZONA_CTG, presupuesto: 900_000_000, factor: 0.238 },
  { id: 8, codigo_co: "414", nombre: "CENTRO", grupo: "003", zona: ZONA_BGA, presupuesto: 1_450_000_000, factor: 0.297 },
  { id: 9, codigo_co: "701", nombre: "SANFELIPE", grupo: "003", zona: ZONA_RESTO, presupuesto: 1_300_000_000, factor: 0.259 },
  { id: 10, codigo_co: "702", nombre: "OLAYA", grupo: "003", zona: ZONA_RESTO, presupuesto: 1_150_000_000, factor: 0.226 },
  { id: 11, codigo_co: "405", nombre: "LA43", grupo: "003", zona: ZONA_L70, presupuesto: 1_400_000_000, factor: 0.288, sinCategorias: ["ASADERO"] },
  { id: 12, codigo_co: "407", nombre: "LA70", grupo: "004", zona: ZONA_L70, presupuesto: 1_750_000_000, factor: 0.31 },
  { id: 13, codigo_co: "413", nombre: "LA93", grupo: "004", zona: ZONA_RESTO, presupuesto: 1_600_000_000, factor: 0.264 },
  { id: 14, codigo_co: "605", nombre: "ALAMEDA", grupo: "004", zona: ZONA_RESTO, presupuesto: 1_250_000_000, factor: 0.271, sinCategorias: ["ASADERO"] },
  { id: 15, codigo_co: "606", nombre: "ALAMEDA2", grupo: "004", zona: ZONA_RESTO, presupuesto: 1_200_000_000, factor: 0.243 },
  // Vende y no está presupuestado. El sistema lo muestra aparte y no descuadra.
  { id: 16, codigo_co: "432", nombre: "EVENTOS BUCARAMANGA", grupo: "002", zona: ZONA_BGA, presupuesto: 0, factor: 0 },
];

interface DefinicionZona {
  id: number;
  nombre: string;
  dias_habiles: number;
  dias_trabajados: number;
}

/** Días hábiles de agosto de 2026 según el Excel vigente (§3.2). */
const ZONAS: DefinicionZona[] = [
  { id: 1, nombre: ZONA_BGA, dias_habiles: 27.5, dias_trabajados: 7.5 },
  { id: 2, nombre: ZONA_CTG, dias_habiles: 24, dias_trabajados: 7 },
  { id: 3, nombre: ZONA_PEI, dias_habiles: 27.5, dias_trabajados: 7.5 },
  { id: 4, nombre: ZONA_L70, dias_habiles: 28.5, dias_trabajados: 8 },
  // Supuesto de §8.1: 28 días hábiles a la espera de que el usuario los confirme.
  { id: 5, nombre: ZONA_RESTO, dias_habiles: 28, dias_trabajados: 7.5 },
];

/** Precio medio por kilo, para derivar el presupuesto en kilos. */
const PRECIO_KILO = 22_000;

function zonaDe(pdv: DefinicionPdv): DefinicionZona {
  return ZONAS.find((zona) => zona.nombre === pdv.zona) ?? ZONAS[0]!;
}

// ── Derivación de indicadores ────────────────────────────────────────────────

function cadena(valor: number, decimales = 2): string {
  return valor.toFixed(decimales);
}

function semaforoDe(cumplimiento: number | null, ideal: number | null, presupuesto: number): Semaforo {
  if (presupuesto <= 0) return "SIN_PRESUPUESTO";
  if (cumplimiento === null || ideal === null) return "SIN_PRESUPUESTO";
  if (cumplimiento >= ideal) return "VERDE";
  if (cumplimiento >= ideal * UMBRAL_AMARILLO) return "AMARILLO";
  return "ROJO";
}

interface EntradaIndicadores {
  presupuesto: number;
  venta: number;
  habiles: number;
  trabajados: number;
  medida: Medida;
  semilla: number;
}

function armarIndicadores(entrada: EntradaIndicadores): FilaIndicadores {
  const { presupuesto, venta, habiles, trabajados, medida, semilla } = entrada;

  const cumplimiento = presupuesto > 0 ? venta / presupuesto : null;
  const ideal = habiles > 0 ? trabajados / habiles : null;
  const brecha = cumplimiento !== null && ideal !== null ? cumplimiento - ideal : null;
  const proyeccion = trabajados > 0 ? (venta / trabajados) * habiles : null;
  const proyectado = proyeccion !== null && presupuesto > 0 ? proyeccion / presupuesto : null;
  const diariaPromedio = trabajados > 0 ? venta / trabajados : null;

  // §4.2: sin días restantes el requerido es indefinido y se pinta «—».
  let diariaRequerida: number | null = null;
  if (presupuesto > 0) {
    if (venta >= presupuesto) diariaRequerida = 0;
    else if (habiles > trabajados) diariaRequerida = (presupuesto - venta) / (habiles - trabajados);
  }

  const crecimiento = 0.14 + (semilla % 23) / 100;
  const anterior = venta > 0 ? venta / (1 + crecimiento) : null;

  // El margen es un concepto monetario: en la vista de kilos no aplica y viaja
  // como `null`, que la pantalla pinta «—» en lugar de un cero engañoso.
  const margenPorcentaje = medida === "kilos" ? null : 0.3 + (semilla % 11) / 100;
  const margenValor = margenPorcentaje === null ? null : venta * margenPorcentaje;

  const decimales = medida === "kilos" ? 2 : 2;

  return {
    presupuesto: presupuesto > 0 ? cadena(presupuesto, decimales) : null,
    venta: cadena(venta, decimales),
    cumplimiento: cumplimiento === null ? null : cadena(cumplimiento, 4),
    ideal: ideal === null ? null : cadena(ideal, 4),
    brecha: brecha === null ? null : cadena(brecha, 4),
    semaforo: semaforoDe(cumplimiento, ideal, presupuesto),
    proyeccion: proyeccion === null ? null : cadena(proyeccion, decimales),
    cumplimiento_proyectado: proyectado === null ? null : cadena(proyectado, 4),
    venta_diaria_promedio: diariaPromedio === null ? null : cadena(diariaPromedio, decimales),
    venta_diaria_requerida: diariaRequerida === null ? null : cadena(diariaRequerida, decimales),
    // Sin 2025 cargado el crecimiento estaría vacío; aquí se simula con historia
    // salvo para dos puntos, para poder ver el «—» en pantalla.
    venta_anio_anterior: anterior === null || semilla % 7 === 3 ? null : cadena(anterior, decimales),
    crecimiento: anterior === null || semilla % 7 === 3 ? null : cadena(crecimiento, 4),
    margen_valor: margenValor === null ? null : cadena(margenValor, decimales),
    margen_porcentaje: margenPorcentaje === null ? null : cadena(margenPorcentaje, 4),
    dias_habiles: cadena(habiles, 1),
    dias_trabajados: cadena(trabajados, 1),
  };
}

/** Escala del presupuesto según la medida activa. */
function presupuestoDe(pdv: DefinicionPdv, medida: Medida): number {
  return medida === "kilos" ? pdv.presupuesto / PRECIO_KILO : pdv.presupuesto;
}

/** En kilos se cumple algo menos que en pesos: el precio tapa el volumen (§4.5). */
function factorDe(pdv: DefinicionPdv, medida: Medida): number {
  return medida === "kilos" ? Math.max(0, pdv.factor - 0.018) : pdv.factor;
}

const PESOS_CATEGORIA: Record<string, number> = {
  RES: 0.32,
  CERDO: 0.17,
  POLLO: 0.16,
  PESCADO: 0.08,
  EMBUTIDOS: 0.09,
  VISCERAS: 0.05,
  ASADERO: 0.07,
  OTROS: 0.06,
};

function categoriasDe(pdv: DefinicionPdv, medida: Medida) {
  const excluidas = pdv.sinCategorias ?? [];
  const activas = CATEGORIAS.filter((categoria) => !excluidas.includes(categoria.codigo));
  const totalPeso = activas.reduce(
    (suma, categoria) => suma + (PESOS_CATEGORIA[categoria.codigo] ?? 0),
    0,
  );
  const zona = zonaDe(pdv);
  const presupuestoPdv = presupuestoDe(pdv, medida);
  const factor = factorDe(pdv, medida);

  return activas.map((categoria, indice) => {
    const peso = (PESOS_CATEGORIA[categoria.codigo] ?? 0) / (totalPeso || 1);
    const presupuesto = presupuestoPdv * peso;
    // Cada categoría se desvía del promedio del punto, que es lo que hace útil
    // el desglose: el punto puede ir bien y la res ir mal.
    const desvio = ((((pdv.id * 7 + indice * 13) % 11) - 5) / 100) * 1.6;
    const venta = presupuesto * Math.max(0.05, factor + desvio);

    return {
      categoria,
      fila: armarIndicadores({
        presupuesto,
        venta,
        habiles: zona.dias_habiles,
        trabajados: zona.dias_trabajados,
        medida,
        semilla: pdv.id * 31 + indice,
      }),
    };
  });
}

function parametrosDe(medida: Medida): ParametrosCalculo {
  const zona = ZONAS[0]!;
  return {
    dias_habiles: cadena(zona.dias_habiles, 1),
    dias_trabajados: cadena(zona.dias_trabajados, 1),
    fecha_corte: FECHA_CORTE,
    umbrales: {
      verde: "cumplimiento ≥ ideal",
      amarillo: `cumplimiento ≥ ideal × ${UMBRAL_AMARILLO}`,
      rojo: `cumplimiento < ideal × ${UMBRAL_AMARILLO}`,
      medida,
    },
  };
}

// ── Construcción de las respuestas ───────────────────────────────────────────

function medidaDe(opciones: Opciones): Medida {
  return opciones.parametros?.medida === "kilos" ? "kilos" : "valor";
}

function pdvsPresupuestados(grupo?: string): DefinicionPdv[] {
  return PDVS.filter(
    (pdv) => pdv.presupuesto > 0 && (grupo === undefined || pdv.grupo === grupo),
  );
}

function agregar(pdvs: DefinicionPdv[], medida: Medida, semilla: number): FilaIndicadores {
  let presupuesto = 0;
  let venta = 0;
  let habilesPonderados = 0;
  let trabajadosPonderados = 0;

  for (const pdv of pdvs) {
    const zona = zonaDe(pdv);
    const presupuestoPdv = presupuestoDe(pdv, medida);
    presupuesto += presupuestoPdv;
    venta += presupuestoPdv * factorDe(pdv, medida);
    // Los días de una agrupación se ponderan por presupuesto: promediarlos a
    // secas mezclaría una zona de 24 días con una de 28.5 como si pesaran igual.
    habilesPonderados += zona.dias_habiles * presupuestoPdv;
    trabajadosPonderados += zona.dias_trabajados * presupuestoPdv;
  }

  const habiles = presupuesto > 0 ? habilesPonderados / presupuesto : 0;
  const trabajados = presupuesto > 0 ? trabajadosPonderados / presupuesto : 0;

  return armarIndicadores({ presupuesto, venta, habiles, trabajados, medida, semilla });
}

function tablero(opciones: Opciones): RespuestaTablero {
  const medida = medidaDe(opciones);
  const grupoFiltrado = opciones.parametros?.grupo;

  const grupos: FilaGrupo[] = GRUPOS.map((grupo, indice) => ({
    codigo: grupo.codigo,
    nombre: grupo.nombre,
    ...agregar(pdvsPresupuestados(grupo.codigo), medida, indice * 5 + 2),
  }));

  const eventos = PDVS.find((pdv) => pdv.codigo_co === "432");
  const ventaEventos = medida === "kilos" ? 3_180_000 / PRECIO_KILO : 68_400_000;

  return {
    periodo: typeof grupoFiltrado === "string" ? PERIODO : PERIODO,
    fecha_corte: FECHA_CORTE,
    medida,
    consolidado: agregar(pdvsPresupuestados(), medida, 1),
    grupos,
    sin_presupuesto: eventos
      ? [
          {
            codigo_co: eventos.codigo_co,
            nombre: eventos.nombre,
            venta: cadena(ventaEventos, 2),
          },
        ]
      : [],
    parametros_calculo: parametrosDe(medida),
  };
}

function cumplimiento(opciones: Opciones): RespuestaCumplimiento {
  const medida = medidaDe(opciones);
  const grupo = opciones.parametros?.grupo;
  const filtroGrupo = typeof grupo === "string" && grupo !== "" ? grupo : undefined;
  const pdvFiltro = opciones.parametros?.punto_venta;

  const seleccion = PDVS.filter((pdv) => {
    if (filtroGrupo !== undefined && pdv.grupo !== filtroGrupo) return false;
    if (typeof pdvFiltro === "string" && pdvFiltro !== "" && pdv.codigo_co !== pdvFiltro) {
      return false;
    }
    return true;
  });

  const filas: FilaPuntoVentaReporte[] = seleccion.map((pdv) => {
    const zona = zonaDe(pdv);
    const presupuesto = presupuestoDe(pdv, medida);
    const venta =
      pdv.presupuesto > 0
        ? presupuesto * factorDe(pdv, medida)
        : medida === "kilos"
          ? 3_180_000 / PRECIO_KILO
          : 68_400_000;

    return {
      punto_venta: pdv.codigo_co,
      nombre: pdv.nombre,
      ...armarIndicadores({
        presupuesto,
        venta,
        habiles: zona.dias_habiles,
        trabajados: zona.dias_trabajados,
        medida,
        semilla: pdv.id,
      }),
      categorias:
        pdv.presupuesto > 0
          ? categoriasDe(pdv, medida).map((entrada) => ({
              categoria: entrada.categoria.nombre,
              ...entrada.fila,
            }))
          : [],
    };
  });

  return {
    periodo: PERIODO,
    fecha_corte: FECHA_CORTE,
    medida,
    filas,
    parametros_calculo: parametrosDe(medida),
  };
}

/**
 * Reparto de la venta del mes entre los días transcurridos.
 *
 * El peso por día de semana replica el patrón de una carnicería: el sábado
 * concentra, el domingo va medio y el lunes cae.
 */
const PESO_DIA_SEMANA = [0.9, 0.75, 0.85, 0.95, 1.05, 1.6, 1.3];

function ventaDiaria(opciones: Opciones): RespuestaVentaDiaria {
  const medida = medidaDe(opciones);
  const fechas: string[] = [];
  for (let dia = 1; dia <= 9; dia += 1) {
    fechas.push(`2026-08-${String(dia).padStart(2, "0")}`);
  }

  const presupuestoDiario: Record<string, string | null> = {};
  const filas: FilaVentaDiaria[] = PDVS.map((pdv) => {
    const zona = zonaDe(pdv);
    const presupuesto = presupuestoDe(pdv, medida);
    const ventaMes =
      pdv.presupuesto > 0
        ? presupuesto * factorDe(pdv, medida)
        : medida === "kilos"
          ? 3_180_000 / PRECIO_KILO
          : 68_400_000;

    presupuestoDiario[pdv.codigo_co] =
      presupuesto > 0 ? cadena(presupuesto / zona.dias_habiles, 2) : null;

    const pesos = fechas.map((iso, indice) => {
      const partes = iso.split("-");
      const fecha = new Date(Number(partes[0]), Number(partes[1]) - 1, Number(partes[2]));
      const base = PESO_DIA_SEMANA[fecha.getDay()] ?? 1;
      return base * (1 + ((((pdv.id * 3 + indice * 5) % 9) - 4) / 100));
    });
    const sumaPesos = pesos.reduce((suma, peso) => suma + peso, 0);

    return {
      punto_venta: pdv.codigo_co,
      nombre: pdv.nombre,
      valores: pesos.map((peso) => cadena((ventaMes * peso) / sumaPesos, 2)),
      total: cadena(ventaMes, 2),
    };
  });

  return {
    fechas,
    presupuesto_diario_por_pdv: presupuestoDiario,
    filas,
    fecha_corte: FECHA_CORTE,
    medida,
    parametros_calculo: parametrosDe(medida),
  };
}

const CLIENTES_EJEMPLO: Record<string, [string, string, number][]> = {
  cliente: [
    ["900123456", "CONSUMIDOR FINAL PDV", 0.412],
    ["901556789", "RESTAURANTE LA BRASA S.A.S.", 0.121],
    ["800334455", "HOTEL ESTELAR CARIBE", 0.094],
    ["901009988", "CASINO SERVICIOS DE ALIMENTACION", 0.078],
    ["830112233", "SUPERMERCADOS OLIMPICA S.A.", 0.066],
    ["901778899", "ASADERO EL BUEN SABOR", 0.051],
    ["900445566", "COMEDORES INDUSTRIALES DEL NORTE", 0.043],
    ["901223344", "PANADERIA Y CAFETERIA LA 70", 0.031],
  ],
  vendedor: [
    ["V-001", "JOHANA MUÑOZ", 0.238],
    ["V-002", "CARLOS RESTREPO", 0.201],
    ["V-003", "LUZ MARINA GOMEZ", 0.176],
    ["V-004", "ANDRES FELIPE OSPINA", 0.152],
    ["V-005", "SANDRA MILENA RUIZ", 0.128],
    ["SIN", "SIN VENDEDOR ASIGNADO", 0.105],
  ],
  canal: [
    ["POS", "CONSUMIDOR FINAL PDV", 0.612],
    ["HORECA", "HORECA", 0.244],
    ["NAL", "CLIENTES NACIONALES", 0.099],
    ["EMP", "EMPLEADOS", 0.021],
    ["SC", "SIN CLASIFICAR", 0.024],
  ],
  condicion_pago: [
    ["CON", "CONTADO", 0.97],
    ["30D", "30 DÍAS", 0.012],
    ["15D", "15 DÍAS", 0.009],
    ["08D", "8 DÍAS", 0.005],
    ["60D", "60 DÍAS", 0.004],
  ],
};

function clientes(opciones: Opciones): RespuestaClientes {
  const medida = medidaDe(opciones);
  const por = typeof opciones.parametros?.por === "string" ? opciones.parametros.por : "cliente";
  const definicion = CLIENTES_EJEMPLO[por] ?? CLIENTES_EJEMPLO.cliente ?? [];
  const ventaTotal = PDVS.reduce(
    (suma, pdv) => suma + presupuestoDe(pdv, medida) * factorDe(pdv, medida),
    0,
  );

  const filas: FilaClientes[] = definicion.map(([clave, nombre, participacion], indice) => {
    const venta = ventaTotal * participacion;
    return {
      clave,
      nombre,
      venta: cadena(venta, 2),
      kilos: cadena(venta / PRECIO_KILO, 2),
      // Una fila sin margen calculable: la pantalla debe pintar «—».
      margen_porcentaje: indice === 4 ? null : cadena(0.28 + (indice % 8) / 100, 4),
      participacion: cadena(participacion, 4),
    };
  });

  return { filas, fecha_corte: FECHA_CORTE, medida, parametros_calculo: parametrosDe(medida) };
}

function calendario(): FilaCalendario[] {
  return ZONAS.map((zona) => ({
    zona: { id: zona.id, nombre: zona.nombre },
    dias_habiles: cadena(zona.dias_habiles, 1),
    dias_trabajados: cadena(zona.dias_trabajados, 1),
    ideal: cadena(zona.dias_trabajados / zona.dias_habiles, 4),
    fecha_corte: FECHA_CORTE,
  }));
}

function presupuesto(opciones: Opciones): FilaPresupuesto[] {
  const codigo = opciones.parametros?.punto_venta;
  const pdv =
    (typeof codigo === "string" ? PDVS.find((item) => item.codigo_co === codigo) : undefined) ??
    PDVS[0]!;

  const excluidas = pdv.sinCategorias ?? [];
  return CATEGORIAS.filter((categoria) => !excluidas.includes(categoria.codigo)).map(
    (categoria, indice) => {
      const peso = PESOS_CATEGORIA[categoria.codigo] ?? 0;
      const monto = pdv.presupuesto * peso;
      return {
        punto_venta: pdv.codigo_co,
      nombre: pdv.nombre,
        categoria: { id: categoria.id, codigo: categoria.codigo, nombre: categoria.nombre },
        monto: cadena(monto, 2),
        kilos: cadena(monto / PRECIO_KILO, 2),
        actualizado_en: indice % 3 === 0 ? "2026-07-28T14:32:00-05:00" : "2026-07-25T09:11:00-05:00",
        actualizado_por: indice % 3 === 0 ? "jmunoz" : "cgomez",
      };
    },
  );
}

const HISTORIAL: CambioPresupuesto[] = [
  {
    cuando: "2026-07-28T14:32:00-05:00",
    quien: "jmunoz",
    campo: "monto · RES",
    valor_anterior: "480000000.00",
    valor_nuevo: "512000000.00",
    motivo: "Ajuste por apertura de nevera adicional en la vitrina principal.",
  },
  {
    cuando: "2026-07-26T10:05:00-05:00",
    quien: "cgomez",
    campo: "kilos · POLLO",
    valor_anterior: "11000.00",
    valor_nuevo: "11636.36",
    motivo: "Corrección de conversión: se había cargado el kilaje de julio.",
  },
  {
    cuando: "2026-07-25T09:11:00-05:00",
    quien: "cgomez",
    campo: "monto · CERDO",
    valor_anterior: null,
    valor_nuevo: "272000000.00",
    motivo: "Carga inicial del período.",
  },
];

const PERIODOS: Periodo[] = [
  { periodo: "2026-08", cerrado: false, cerrado_por: null, cerrado_en: null },
  { periodo: "2026-07", cerrado: true, cerrado_por: "arestrepo", cerrado_en: "2026-08-03T17:40:00-05:00" },
  { periodo: "2026-06", cerrado: true, cerrado_por: "arestrepo", cerrado_en: "2026-07-04T11:20:00-05:00" },
];

const CORRIDAS: CorridaIngesta[] = [
  {
    id: 314,
    cuando: "2026-08-09T23:10:00-05:00",
    quien: "sistema",
    fuente: "excel",
    desde: "2026-08-01",
    hasta: "2026-08-09",
    estado: "COMPLETADA_CON_RECHAZOS",
    filas_leidas: 131_819,
    aceptadas: 131_791,
    rechazadas: 28,
    duracion_ms: 47_320,
  },
  {
    id: 313,
    cuando: "2026-08-08T23:10:00-05:00",
    quien: "sistema",
    fuente: "excel",
    desde: "2026-08-01",
    hasta: "2026-08-08",
    estado: "COMPLETADA",
    filas_leidas: 117_204,
    aceptadas: 117_204,
    rechazadas: 0,
    duracion_ms: 41_880,
  },
  {
    id: 312,
    cuando: "2026-08-07T23:10:00-05:00",
    quien: "jmunoz",
    fuente: "excel",
    desde: "2026-08-07",
    hasta: "2026-08-07",
    estado: "ERROR",
    filas_leidas: 0,
    aceptadas: 0,
    rechazadas: 0,
    duracion_ms: 1_204,
  },
];

/** Rechazos con los motivos reales del aviso de calidad de dato de §3.4. */
const RECHAZOS: RechazoIngesta[] = [
  { fila: 1_042, campo: "Domicilio", valor: "", motivo: "Campo obligatorio vacío; se esperaba «Si» o «No»." },
  { fila: 1_043, campo: "Domicilio", valor: "", motivo: "Campo obligatorio vacío; se esperaba «Si» o «No»." },
  { fila: 8_871, campo: "CLASES DE CLIENTES", valor: "johana.muñoz", motivo: "El valor no pertenece al catálogo de clases de cliente." },
  { fila: 12_004, campo: "CLASES DE CLIENTES", valor: "2026-08-03 16:29:02", motivo: "El valor no pertenece al catálogo de clases de cliente." },
  { fila: 30_115, campo: "CATEGORIA", valor: "0021 - MARISCOS", motivo: "Categoría de SIESA sin mapeo registrado; se clasificó como OTROS." },
  { fila: 44_902, campo: "C.O.", valor: "0", motivo: "Centro de operación desconocido; la fila no se pudo asignar a un punto de venta." },
  { fila: 51_330, campo: "Cantidad inv.", valor: "-12.5", motivo: "Cantidad negativa sin nota crédito asociada." },
  { fila: 77_650, campo: "Valor subtotal", valor: "", motivo: "Venta vacía: la línea no aporta valor y se descarta." },
];

const USUARIO: Usuario = {
  id: 1,
  usuario: "gerencia",
  nombre: "Gerencia General (datos de ejemplo)",
  rol: "GERENTE",
  puntos_venta: [],
};

const SALUD: Salud = {
  estado: "datos_de_ejemplo",
  version: "0.0.0-ejemplos",
  base_datos: "sin conexión — la interfaz corre con datos ficticios",
  ultima_ingesta: "2026-08-09T23:10:00-05:00",
};

// ── Enrutado ─────────────────────────────────────────────────────────────────

/** Retardo corto para que los estados de carga se puedan ver y revisar. */
function esperar<T>(valor: T): Promise<T> {
  return new Promise((resolver) => {
    setTimeout(() => resolver(valor), 140);
  });
}

export async function acceder(usuario: string, clave: string): Promise<TokensAcceso> {
  if (!usuario || !clave) {
    throw new ErrorApi(401, "credenciales_invalidas", "Indique usuario y contraseña.");
  }
  return esperar({
    token_acceso: "ejemplo.token.acceso",
    token_refresco: "ejemplo.token.refresco",
    tipo: "bearer",
  });
}

export async function responderArchivo<T>(ruta: string, archivo: File): Promise<T> {
  if (ruta.startsWith("/presupuesto/carga-masiva")) {
    return esperar({
      aceptadas: 118,
      rechazadas: 3,
      errores: [
        { fila: 14, motivo: `Punto de venta «PDV LA 44» no existe en el catálogo (${archivo.name}).` },
        { fila: 51, motivo: "El monto «1.250.000,oo» no es un número válido." },
        { fila: 92, motivo: "El período 2026-07 está cerrado y no admite cambios de presupuesto." },
      ],
    } as T);
  }

  if (ruta.startsWith("/ingesta/archivo")) {
    return esperar({ ...CORRIDAS[0]!, id: 315, quien: "gerencia", cuando: new Date().toISOString() } as T);
  }

  throw new ErrorApi(404, "ruta_desconocida", `Sin datos de ejemplo para «${ruta}».`);
}

/**
 * Traduce una ruta del contrato al bloque de datos de ejemplo correspondiente.
 *
 * Las escrituras no persisten nada: devuelven una respuesta plausible para que
 * el ciclo de la interfaz (enviar, invalidar, recargar) se pueda revisar de
 * extremo a extremo.
 */
export async function responder<T>(ruta: string, opciones: Opciones): Promise<T> {
  const metodo = opciones.metodo ?? "GET";

  if (metodo !== "GET") {
    if (ruta.startsWith("/periodos/") && ruta.endsWith("/cerrar")) {
      return esperar({ periodo: PERIODO, cerrado: true, cerrado_por: "gerencia", cerrado_en: new Date().toISOString() } as T);
    }
    // PUT de presupuesto, PUT de calendario, POST de ingesta y de mapeo.
    return esperar(undefined as T);
  }

  const rutas: Record<string, () => unknown> = {
    "/auth/yo": () => USUARIO,
    "/salud": () => SALUD,
    "/catalogos/grupos": () => GRUPOS,
    "/catalogos/categorias": () => CATEGORIAS,
    "/catalogos/puntos-venta": () =>
      PDVS.map(
        (pdv): PuntoVenta => ({
          id: pdv.id,
          codigo_co: pdv.codigo_co,
          nombre: pdv.nombre,
          grupo: GRUPOS.find((grupo) => grupo.codigo === pdv.grupo)?.nombre ?? pdv.grupo,
          zona: pdv.zona,
          activo: true,
          presupuestado: pdv.presupuesto > 0,
        }),
      ),
    "/catalogos/zonas": () =>
      ZONAS.map(
        (zona): Zona => ({
          id: zona.id,
          nombre: zona.nombre,
          puntos_venta: PDVS.filter((pdv) => pdv.zona === zona.nombre).map((pdv) => pdv.nombre),
        }),
      ),
    "/catalogos/mapeo-categorias": () =>
      [
        ["0001 - RES", "RES"],
        ["0002 - CERDO", "CERDO"],
        ["0003 - POLLO", "POLLO"],
        ["0004 - PESCADO", "PESCADO"],
        ["0005 - EMBUTIDOS", "EMBUTIDOS"],
        ["0009 - VISCERAS", "VISCERAS"],
        ["0010 - RESTAURANTE", "ASADERO"],
        ["0006 - QUESO Y LACTEOS", "OTROS"],
        ["0006 - QUESOS Y LACTEOS", "OTROS"],
        ["0007 - HUEVOS", "OTROS"],
        ["0008 - VIVERES", "OTROS"],
        ["0014 - DOMICILIOS", "OTROS"],
      ].map(([texto, categoria]): MapeoCategoria => ({ texto_siesa: texto ?? "", categoria: categoria ?? "" })),
    "/calendario": calendario,
    "/presupuesto": () => presupuesto(opciones),
    "/presupuesto/historial": () => HISTORIAL,
    "/periodos": () => PERIODOS,
    "/reportes/tablero": () => tablero(opciones),
    "/reportes/cumplimiento": () => cumplimiento(opciones),
    "/reportes/venta-diaria": () => ventaDiaria(opciones),
    "/reportes/clientes": () => clientes(opciones),
    "/ingesta/corridas": () => CORRIDAS,
  };

  const constructor = rutas[ruta];
  if (constructor) return esperar(constructor() as T);

  if (/^\/ingesta\/corridas\/\d+\/rechazos$/.test(ruta)) {
    return esperar(RECHAZOS as T);
  }

  throw new ErrorApi(
    404,
    "ruta_sin_ejemplo",
    `La ruta «${ruta}» no tiene datos de ejemplo. Apague VITE_SIGREP_EJEMPLOS para consultar el backend.`,
  );
}
