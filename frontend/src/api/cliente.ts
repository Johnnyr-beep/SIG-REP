/**
 * Cliente HTTP de la API de SIGREP.
 *
 * Concentra cuatro responsabilidades que no conviene repartir por los
 * componentes: adjuntar el token, renovar la sesión cuando caduca, traducir el
 * formato de error del backend (`{detalle, codigo}`) a una excepción tipada, y
 * —mientras el backend se termina— desviar todo el tráfico al juego de datos de
 * ejemplo cuando la variable de entorno lo pide.
 *
 * Portado de `gsc-one/frontend/src/api/cliente.ts` y ajustado al contrato de
 * `docs/API.md`, que nombra los campos en español (`token_acceso`,
 * `token_refresco`) y expone el login en `/auth/acceso`.
 */

import type { CuerpoError, TokenRenovado, TokensAcceso } from "./tipos";

const BASE = "/api/v1";

/**
 * Modo de datos de ejemplo.
 *
 * Se lee una sola vez, del entorno de compilación: con la variable ausente o en
 * «0» —el caso de producción— el módulo de ejemplos ni siquiera se descarga,
 * porque la importación es dinámica y Vite lo deja en un fragmento aparte.
 */
export const MODO_EJEMPLOS = import.meta.env.VITE_SIGREP_EJEMPLOS === "1";

/** Error de negocio devuelto por la API, con su código. */
export class ErrorApi extends Error {
  constructor(
    readonly estado: number,
    readonly codigo: string,
    mensaje: string,
  ) {
    super(mensaje);
    this.name = "ErrorApi";
  }

  /** Alias en español de `message`, para uniformidad con el resto del código. */
  get mensaje(): string {
    return this.message;
  }

  /** El usuario perdió la sesión y debe volver a autenticarse. */
  get esSesionExpirada(): boolean {
    return this.estado === 401;
  }

  /** El rol del usuario no alcanza para la operación. */
  get esProhibido(): boolean {
    return this.estado === 403;
  }

  /** La operación es válida pero el estado actual la impide (período cerrado). */
  get esConflicto(): boolean {
    return this.estado === 409;
  }
}

// ── Almacén de tokens ────────────────────────────────────────────────────────

const CLAVE_ACCESO = "sigrep_acceso";
const CLAVE_REFRESCO = "sigrep_refresco";

/**
 * Los tokens viven en `sessionStorage`, no en `localStorage`: al cerrar la
 * pestaña la sesión muere, que es el comportamiento esperado en un equipo
 * compartido de oficina o en el portátil que se pasa en una reunión.
 */
export const almacenTokens = {
  acceso: (): string | null => sessionStorage.getItem(CLAVE_ACCESO),
  refresco: (): string | null => sessionStorage.getItem(CLAVE_REFRESCO),
  guardar(acceso: string, refresco: string): void {
    sessionStorage.setItem(CLAVE_ACCESO, acceso);
    sessionStorage.setItem(CLAVE_REFRESCO, refresco);
  },
  actualizarAcceso(acceso: string): void {
    sessionStorage.setItem(CLAVE_ACCESO, acceso);
  },
  limpiar(): void {
    sessionStorage.removeItem(CLAVE_ACCESO);
    sessionStorage.removeItem(CLAVE_REFRESCO);
  },
};

type ManejadorSesion = () => void;
let alExpirarSesion: ManejadorSesion | null = null;

export function registrarExpiracionSesion(manejador: ManejadorSesion): void {
  alExpirarSesion = manejador;
}

// ── Renovación de token ──────────────────────────────────────────────────────

/**
 * Promesa compartida de renovación.
 *
 * El tablero dispara varias consultas a la vez. Si todas reciben 401 y cada una
 * pide su propia renovación, los refrescos concurrentes se invalidan entre sí y
 * el gerente acaba en la pantalla de acceso sin motivo aparente.
 */
let renovacionEnCurso: Promise<boolean> | null = null;

async function renovarSesion(): Promise<boolean> {
  const refresco = almacenTokens.refresco();
  if (!refresco) return false;

  renovacionEnCurso ??= (async () => {
    try {
      const respuesta = await fetch(`${BASE}/auth/refrescar`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token_refresco: refresco }),
      });
      if (!respuesta.ok) return false;

      // El contrato devuelve solo el token de acceso: el de refresco sigue vivo.
      const datos = (await respuesta.json()) as TokenRenovado;
      almacenTokens.actualizarAcceso(datos.token_acceso);
      return true;
    } catch {
      return false;
    } finally {
      // Se libera en el siguiente tick para que los que esperaban lean el token nuevo.
      queueMicrotask(() => {
        renovacionEnCurso = null;
      });
    }
  })();

  return renovacionEnCurso;
}

// ── Petición ─────────────────────────────────────────────────────────────────

export type ValorParametro = string | number | boolean | string[] | undefined | null;

export interface Opciones {
  metodo?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  cuerpo?: unknown;
  parametros?: Record<string, ValorParametro>;
  /** Uso interno: evita reintentar en bucle tras una renovación fallida. */
  esReintento?: boolean;
}

function construirUrl(ruta: string, parametros?: Opciones["parametros"]): string {
  const url = new URL(`${BASE}${ruta}`, window.location.origin);
  if (parametros) {
    for (const [clave, valor] of Object.entries(parametros)) {
      if (valor === undefined || valor === null || valor === "") continue;
      if (Array.isArray(valor)) {
        valor.forEach((elemento) => url.searchParams.append(clave, elemento));
      } else {
        url.searchParams.set(clave, String(valor));
      }
    }
  }
  return url.pathname + url.search;
}

async function extraerError(respuesta: Response): Promise<ErrorApi> {
  let codigo = "error_desconocido";
  let mensaje = `La solicitud falló con estado ${respuesta.status}.`;

  try {
    const cuerpo = (await respuesta.json()) as CuerpoError;
    if (cuerpo.detalle) mensaje = cuerpo.detalle;
    if (cuerpo.codigo) codigo = cuerpo.codigo;
  } catch {
    // El backend devolvió algo que no es JSON (p. ej. un 502 del proxy).
  }

  return new ErrorApi(respuesta.status, codigo, mensaje);
}

function cabecerasBase(): Record<string, string> {
  const cabeceras: Record<string, string> = { Accept: "application/json" };
  const token = almacenTokens.acceso();
  if (token) cabeceras.Authorization = `Bearer ${token}`;
  return cabeceras;
}

export async function peticion<T>(ruta: string, opciones: Opciones = {}): Promise<T> {
  if (MODO_EJEMPLOS) {
    const { responder } = await import("./ejemplos");
    return responder<T>(ruta, opciones);
  }

  const { metodo = "GET", cuerpo, parametros, esReintento = false } = opciones;

  const cabeceras = cabecerasBase();
  if (cuerpo !== undefined) cabeceras["Content-Type"] = "application/json";

  const respuesta = await fetch(construirUrl(ruta, parametros), {
    method: metodo,
    headers: cabeceras,
    body: cuerpo === undefined ? undefined : JSON.stringify(cuerpo),
  });

  if (respuesta.status === 401 && !esReintento && almacenTokens.refresco()) {
    if (await renovarSesion()) {
      return peticion<T>(ruta, { ...opciones, esReintento: true });
    }
    almacenTokens.limpiar();
    alExpirarSesion?.();
  }

  if (!respuesta.ok) {
    const error = await extraerError(respuesta);
    if (error.esSesionExpirada) {
      almacenTokens.limpiar();
      alExpirarSesion?.();
    }
    throw error;
  }

  if (respuesta.status === 204) return undefined as T;
  return (await respuesta.json()) as T;
}

/** Envío `multipart`: carga masiva de presupuesto e ingesta por archivo. */
export async function enviarArchivo<T>(
  ruta: string,
  archivo: File,
  campos: Record<string, string> = {},
): Promise<T> {
  if (MODO_EJEMPLOS) {
    const { responderArchivo } = await import("./ejemplos");
    return responderArchivo<T>(ruta, archivo);
  }

  const formulario = new FormData();
  formulario.append("archivo", archivo);
  for (const [clave, valor] of Object.entries(campos)) formulario.append(clave, valor);

  // Sin `Content-Type`: el navegador debe fijarlo con la frontera del multipart.
  const respuesta = await fetch(construirUrl(ruta), {
    method: "POST",
    headers: cabecerasBase(),
    body: formulario,
  });

  if (!respuesta.ok) throw await extraerError(respuesta);
  if (respuesta.status === 204) return undefined as T;
  return (await respuesta.json()) as T;
}

/**
 * Descarga un `.xlsx` de los endpoints `/exportar`.
 *
 * No se puede usar un enlace directo porque la exportación exige la cabecera
 * `Authorization`: se pide con `fetch`, se materializa el blob y se dispara la
 * descarga con un enlace efímero.
 */
export async function descargar(
  ruta: string,
  parametros: Record<string, ValorParametro>,
  nombreSugerido: string,
): Promise<void> {
  if (MODO_EJEMPLOS) {
    throw new ErrorApi(
      501,
      "exportacion_no_disponible",
      "La exportación a Excel la genera el backend; no está disponible en el modo de datos de ejemplo.",
    );
  }

  const respuesta = await fetch(construirUrl(ruta, parametros), {
    method: "GET",
    headers: cabecerasBase(),
  });

  if (!respuesta.ok) throw await extraerError(respuesta);

  const blob = await respuesta.blob();
  const cabecera = respuesta.headers.get("Content-Disposition") ?? "";
  const nombreEnCabecera = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(cabecera)?.[1];

  const url = URL.createObjectURL(blob);
  const enlace = document.createElement("a");
  enlace.href = url;
  enlace.download = nombreEnCabecera ? decodeURIComponent(nombreEnCabecera) : nombreSugerido;
  document.body.appendChild(enlace);
  enlace.click();
  enlace.remove();
  URL.revokeObjectURL(url);
}

// ── Acceso ───────────────────────────────────────────────────────────────────

/** Login: no lleva token y guarda el par emitido. */
export async function iniciarSesion(usuario: string, clave: string): Promise<void> {
  if (MODO_EJEMPLOS) {
    const { acceder } = await import("./ejemplos");
    const datos = await acceder(usuario, clave);
    almacenTokens.guardar(datos.token_acceso, datos.token_refresco);
    return;
  }

  const respuesta = await fetch(`${BASE}/auth/acceso`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ usuario, clave }),
  });

  if (!respuesta.ok) throw await extraerError(respuesta);

  const datos = (await respuesta.json()) as TokensAcceso;
  almacenTokens.guardar(datos.token_acceso, datos.token_refresco);
}
