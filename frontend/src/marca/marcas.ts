/**
 * Las tres unidades de negocio del grupo.
 *
 * Este archivo es el censo: quién existe, cómo se llama, con qué logo y si está
 * desplegada. Los **colores no están aquí**: viven en `estilos.css`, en un único
 * bloque por marca que alimenta a la vez el tema de la aplicación y la tarjeta
 * del selector (véase «Identidad de la unidad de negocio» en la hoja). Repetir
 * los hexadecimales en TypeScript sería abrir una segunda fuente de verdad que
 * tarde o temprano se desincroniza de la primera.
 *
 * El puente entre las dos capas es la clave: `data-marca="carnes"` en el
 * elemento raíz, y `data-marca-tarjeta="carnes"` en cada tarjeta del selector.
 */

import logoCarnes from "@/recursos/carnes-santacruz.png";
import logoCarnesFrias from "@/recursos/carnes-frias.png";
import logoAgropecuaria from "@/recursos/frigorifico-agropecuaria.png";

export type ClaveMarca = "carnes" | "agropecuaria" | "carnes-frias";

/**
 * `activa` es la instancia desplegada; `proximamente` es una unidad que existe
 * en el grupo pero todavía no tiene datos ni backend detrás. Se muestra —no se
 * esconde—, pero no deja continuar al acceso.
 */
export type EstadoMarca = "activa" | "proximamente";

export interface Marca {
  clave: ClaveMarca;
  /** Nombre que adopta la aplicación en la barra lateral y en el acceso. */
  nombre: string;
  logo: string;
  /**
   * Dimensiones naturales del PNG. Van explícitas en el `<img>` para que el
   * navegador reserve el hueco antes de descargarlo: los tres logos tienen
   * proporciones distintas (172×182, 197×144 y 160×116) y sin esto la tarjeta
   * de acceso salta al terminar la carga.
   */
  logoAncho: number;
  logoAlto: number;
  estado: EstadoMarca;
  /** Una línea que explica qué es la unidad, bajo la tarjeta del selector. */
  descripcion: string;
}

export const MARCAS: readonly Marca[] = [
  {
    clave: "carnes",
    nombre: "Carnes Santacruz",
    logo: logoCarnes,
    logoAncho: 172,
    logoAlto: 182,
    estado: "activa",
    descripcion: "Puntos de venta al detal. Es la instancia en operación.",
  },
  {
    clave: "agropecuaria",
    nombre: "Frigorífico Agropecuaria",
    logo: logoAgropecuaria,
    logoAncho: 197,
    logoAlto: 144,
    estado: "proximamente",
    descripcion: "Planta de beneficio y canales. Pendiente de despliegue.",
  },
  {
    clave: "carnes-frias",
    nombre: "Carnes Frías",
    logo: logoCarnesFrias,
    logoAncho: 160,
    logoAlto: 116,
    estado: "proximamente",
    descripcion: "Línea de derivados cárnicos. Pendiente de despliegue.",
  },
];

/**
 * Marca con la que se pinta la interfaz mientras no hay ninguna elegida —el
 * propio selector— y valor que `estilos.css` deja en `:root` sin atributo.
 * Las dos definiciones tienen que decir lo mismo.
 */
export const MARCA_POR_DEFECTO: ClaveMarca = "carnes";

/** Traduce lo que haya en `localStorage` a una marca real, o a `null`. */
export function obtenerMarca(clave: string | null | undefined): Marca | null {
  if (!clave) return null;
  return MARCAS.find((marca) => marca.clave === clave) ?? null;
}

/**
 * Ancho que le corresponde a un logo dibujado a un alto dado.
 *
 * Los logos se dimensionan por el **alto**, no por el ancho: el de Carnes es
 * vertical (172×182) y los otros dos apaisados (197×144, 160×116), así que
 * fijar el ancho los dejaría de tamaños visuales muy distintos.
 */
export function anchoLogo(marca: Marca, alto: number): number {
  return Math.round((alto * marca.logoAncho) / marca.logoAlto);
}
