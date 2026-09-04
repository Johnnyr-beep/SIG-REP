/**
 * Hooks de datos sobre TanStack Query.
 *
 * Toda llamada a la API pasa por aquí: los componentes no conocen rutas ni
 * verbos HTTP, solo hooks con nombre de negocio. Cambiar un endpoint es tocar
 * este archivo, no ocho pantallas.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { UseMutationResult, UseQueryResult } from "@tanstack/react-query";

import { descargar, enviarArchivo, peticion } from "./cliente";
import type { ValorParametro } from "./cliente";

import type {
  CambioClave,
  CambioPresupuesto,
  CambioUsuario,
  Categoria,
  ClaveRestablecida,
  CorridaIngesta,
  CorteClientes,
  EntradaCalendario,
  EntradaIngesta,
  EntradaHistoriaVenta,
  EntradaPresupuesto,
  EntradaUsuario,
  EventoAuditoria,
  FilaCalendario,
  FilaPresupuesto,
  Grupo,
  HistoriaVenta,
  MapeoCategoria,
  Medida,
  Periodo,
  PuntoVenta,
  RechazoIngesta,
  RespuestaClientes,
  RespuestaCumplimiento,
  RespuestaCostos,
  RespuestaTablero,
  RespuestaVentaDiaria,
  ResultadoCargaMasiva,
  Rol,
  Salud,
  Usuario,
  UsuarioAdministrado,
  UsuarioCreado,
  Zona,
} from "./tipos";

/** Filtros de `GET /usuarios`. Ambos opcionales, como en el contrato. */
export interface FiltrosUsuarios {
  rol?: Rol | "";
  activo?: "true" | "false" | "";
}

/** Filtros comunes a todos los reportes (§ «Reportes» del contrato). */
export interface FiltrosReporte {
  /** Obligatorio. `YYYY-MM`. */
  periodo: string;
  /**
   * Primer día del rango. **Solo lo entiende `venta-diaria`.**
   *
   * No entra en `comoParametros` a propósito: el contrato lo declara únicamente
   * en ese reporte, así que mandarlo a los otros tres sería enviar un parámetro
   * que no está en su firma.
   */
  desde?: string;
  /** Fecha de corte. Ausente = hoy, según el contrato. */
  hasta?: string;
  grupo?: string;
  /**
   * Uno o varios códigos C.O. separados por coma: `"402,405,603"`.
   *
   * **Ausente significa «todos»**, y no es lo mismo que enumerar los dieciséis
   * a mano —aunque el resultado coincida—. Por eso una selección vacía borra el
   * parámetro en lugar de enviarlo en blanco: el contrato dice que
   * `?punto_venta=` equivale a no filtrar, y una barra que se vacía no pide el
   * punto de código «».
   */
  punto_venta?: string;
  /**
   * Centros de operación de agropecuaria, separados por coma: `"301,302"`.
   *
   * **Ningún reporte de carnes lo entiende**, y por eso no entra en
   * `comoParametros`: vive aquí porque el estado de los filtros es uno solo —la
   * barra de direcciones— y las dos unidades comparten esa barra. Lo consume
   * `filtrosAgroDe`, que arma los parámetros de `/agro`.
   */
  centro?: string;
  categoria?: string;
  medida: Medida;
}

function comoParametros(
  filtros: FiltrosReporte,
): Record<string, ValorParametro> {
  return {
    periodo: filtros.periodo,
    hasta: filtros.hasta,
    grupo: filtros.grupo,
    punto_venta: filtros.punto_venta,
    categoria: filtros.categoria,
    medida: filtros.medida,
  };
}

/** Los mismos filtros más `desde`, que es exclusivo del reporte diario. */
function comoParametrosDiarios(
  filtros: FiltrosReporte,
): Record<string, ValorParametro> {
  return { ...comoParametros(filtros), desde: filtros.desde };
}

/** Claves de caché centralizadas para poder invalidar con precisión. */
export const claves = {
  perfil: ["perfil"] as const,
  salud: ["salud"] as const,
  grupos: ["catalogo", "grupos"] as const,
  puntosVenta: ["catalogo", "puntos-venta"] as const,
  categorias: ["catalogo", "categorias"] as const,
  zonas: ["catalogo", "zonas"] as const,
  mapeoCategorias: ["catalogo", "mapeo-categorias"] as const,
  calendario: (periodo: string) => ["calendario", periodo] as const,
  presupuesto: (periodo: string, puntoVenta: string) =>
    ["presupuesto", periodo, puntoVenta] as const,
  historialPresupuesto: (periodo: string, puntoVenta: string) =>
    ["presupuesto-historial", periodo, puntoVenta] as const,
  historiaVenta: (periodo: string) => ["historia-venta", periodo] as const,
  periodos: ["periodos"] as const,
  tablero: (filtros: FiltrosReporte) =>
    ["reporte", "tablero", filtros] as const,
  cumplimiento: (filtros: FiltrosReporte) =>
    ["reporte", "cumplimiento", filtros] as const,
  costos: (filtros: FiltrosReporte) => ["reporte", "costos", filtros] as const,
  ventaDiaria: (filtros: FiltrosReporte) =>
    ["reporte", "venta-diaria", filtros] as const,
  clientes: (filtros: FiltrosReporte, por: CorteClientes) =>
    ["reporte", "clientes", por, filtros] as const,

  corridas: ["ingesta", "corridas"] as const,
  rechazos: (id: number) => ["ingesta", "rechazos", id] as const,
  usuarios: (filtros: FiltrosUsuarios) => ["usuarios", filtros] as const,
  auditoriaUsuarios: (usuarioId: number | null, limite: number) =>
    ["usuarios", "auditoria", usuarioId, limite] as const,
};

// ── Sesión y salud ───────────────────────────────────────────────────────────

export function usePerfil(habilitado: boolean): UseQueryResult<Usuario> {
  return useQuery({
    queryKey: claves.perfil,
    queryFn: () => peticion<Usuario>("/auth/yo"),
    enabled: habilitado,
    staleTime: 5 * 60_000,
    retry: false,
  });
}

/**
 * Cambio de clave, obligatorio o voluntario.
 *
 * Al terminar solo se invalida el perfil: el token sigue sirviendo y el usuario
 * continúa donde estaba, sin repetir el inicio de sesión. La respuesta trae el
 * perfil ya sin la marca, así que además se refresca de inmediato la copia en
 * caché para que el bloqueo desaparezca sin esperar al viaje de vuelta.
 */
export function useCambiarClave(): UseMutationResult<void, Error, CambioClave> {
  const cliente = useQueryClient();
  return useMutation({
    mutationFn: (datos) =>
      peticion<void>("/auth/cambiar-clave", { metodo: "POST", cuerpo: datos }),
    onSuccess: () => {
      cliente.setQueryData<Usuario>(claves.perfil, (anterior) =>
        anterior ? { ...anterior, debe_cambiar_password: false } : anterior,
      );
      void cliente.invalidateQueries({ queryKey: claves.perfil });
    },
  });
}

export function useSalud(): UseQueryResult<Salud> {
  return useQuery({
    queryKey: claves.salud,
    queryFn: () => peticion<Salud>("/salud"),
    staleTime: 60_000,
    retry: false,
  });
}

// ── Catálogos ────────────────────────────────────────────────────────────────

/** Los catálogos cambian de mes en mes, no de minuto en minuto. */
const CACHE_CATALOGO = 30 * 60_000;

export function useGrupos(): UseQueryResult<Grupo[]> {
  return useQuery({
    queryKey: claves.grupos,
    queryFn: () => peticion<Grupo[]>("/catalogos/grupos"),
    staleTime: CACHE_CATALOGO,
  });
}

export function usePuntosVenta(): UseQueryResult<PuntoVenta[]> {
  return useQuery({
    queryKey: claves.puntosVenta,
    queryFn: () => peticion<PuntoVenta[]>("/catalogos/puntos-venta"),
    staleTime: CACHE_CATALOGO,
  });
}

export function useCategorias(): UseQueryResult<Categoria[]> {
  return useQuery({
    queryKey: claves.categorias,
    queryFn: () => peticion<Categoria[]>("/catalogos/categorias"),
    staleTime: CACHE_CATALOGO,
  });
}

export function useZonas(): UseQueryResult<Zona[]> {
  return useQuery({
    queryKey: claves.zonas,
    queryFn: () => peticion<Zona[]>("/catalogos/zonas"),
    staleTime: CACHE_CATALOGO,
  });
}

export function useMapeoCategorias(
  habilitado = true,
): UseQueryResult<MapeoCategoria[]> {
  return useQuery({
    queryKey: claves.mapeoCategorias,
    queryFn: () => peticion<MapeoCategoria[]>("/catalogos/mapeo-categorias"),
    enabled: habilitado,
    staleTime: CACHE_CATALOGO,
  });
}

// ── Reportes ─────────────────────────────────────────────────────────────────

export function useTablero(
  filtros: FiltrosReporte,
): UseQueryResult<RespuestaTablero> {
  return useQuery({
    queryKey: claves.tablero(filtros),
    queryFn: () =>
      peticion<RespuestaTablero>("/reportes/tablero", {
        parametros: comoParametros(filtros),
      }),
    staleTime: 60_000,
  });
}

export function useCumplimiento(
  filtros: FiltrosReporte,
): UseQueryResult<RespuestaCumplimiento> {
  return useQuery({
    queryKey: claves.cumplimiento(filtros),
    queryFn: () =>
      peticion<RespuestaCumplimiento>("/reportes/cumplimiento", {
        parametros: comoParametros(filtros),
      }),
    staleTime: 60_000,
  });
}

export function useCostos(
  filtros: FiltrosReporte,
): UseQueryResult<RespuestaCostos> {
  return useQuery({
    queryKey: claves.costos(filtros),
    queryFn: () =>
      peticion<RespuestaCostos>("/reportes/costos", {
        parametros: comoParametros(filtros),
      }),
    staleTime: 60_000,
  });
}

/**
 * Matriz diaria, con el rango `desde`/`hasta` del contrato.
 *
 * `habilitado` existe para que la pantalla pueda **no lanzar** la consulta
 * cuando ya sabe que el rango es inválido —invertido o por encima del tope de
 * 92 días—. Un 422 que el usuario no puede provocar es mejor que uno bien
 * explicado; y hasta que corrija el rango, la petición no sale.
 */
export function useVentaDiaria(
  filtros: FiltrosReporte,
  habilitado = true,
): UseQueryResult<RespuestaVentaDiaria> {
  return useQuery({
    queryKey: claves.ventaDiaria(filtros),
    queryFn: () =>
      peticion<RespuestaVentaDiaria>("/reportes/venta-diaria", {
        parametros: comoParametrosDiarios(filtros),
      }),
    enabled: habilitado,
    staleTime: 60_000,
  });
}

export function useVentaDiariaAsadero(
  filtros: FiltrosReporte,
  habilitado = true,
): UseQueryResult<RespuestaVentaDiaria> {
  return useQuery({
    queryKey: ["reporte", "venta-diaria-asadero", filtros],
    queryFn: () =>
      peticion<RespuestaVentaDiaria>("/reportes/venta-diaria-asadero", {
        parametros: comoParametrosDiarios(filtros),
      }),
    enabled: habilitado,
    staleTime: 60_000,
  });
}


export function useClientes(
  filtros: FiltrosReporte,
  por: CorteClientes,
): UseQueryResult<RespuestaClientes> {
  return useQuery({
    queryKey: claves.clientes(filtros, por),
    queryFn: () =>
      peticion<RespuestaClientes>("/reportes/clientes", {
        parametros: { ...comoParametros(filtros), por },
      }),
    staleTime: 60_000,
  });
}

/**
 * Exporta el reporte visible a `.xlsx` con los mismos filtros de la pantalla.
 *
 * No es una consulta: es un efecto que descarga un archivo, así que se modela
 * como mutación para tener estados de envío y error sin ensuciar la caché.
 */
export function useExportar(): UseMutationResult<
  void,
  Error,
  {
    reporte: string;
    filtros: FiltrosReporte;
    extra?: Record<string, ValorParametro>;
  }
> {
  return useMutation({
    mutationFn: ({ reporte, filtros, extra }) =>
      descargar(
        `/reportes/${reporte}/exportar`,
        // `desde` solo viaja en el reporte que lo declara; en los demás, `filtros.desde`
        // ni siquiera se puede fijar desde la barra.
        {
          ...(reporte === "venta-diaria"
            ? comoParametrosDiarios(filtros)
            : comoParametros(filtros)),
          ...extra,
        },
        `sigrep-${reporte}-${filtros.periodo}.xlsx`,
      ),
  });
}

// ── Calendario ───────────────────────────────────────────────────────────────

export function useCalendario(
  periodo: string,
): UseQueryResult<FilaCalendario[]> {
  return useQuery({
    queryKey: claves.calendario(periodo),
    queryFn: () =>
      peticion<FilaCalendario[]>("/calendario", { parametros: { periodo } }),
    staleTime: 5 * 60_000,
  });
}

export function useGuardarCalendario(
  periodo: string,
): UseMutationResult<
  void,
  Error,
  { zonaId: number; datos: EntradaCalendario }
> {
  const cliente = useQueryClient();
  return useMutation({
    mutationFn: ({ zonaId, datos }) =>
      peticion<void>(`/calendario/${zonaId}`, {
        metodo: "PUT",
        parametros: { periodo },
        cuerpo: datos,
      }),
    onSuccess: () => {
      void cliente.invalidateQueries({ queryKey: claves.calendario(periodo) });
      // Los días hábiles son el denominador del ideal: cambiarlos mueve todos
      // los indicadores de todas las pantallas.
      void cliente.invalidateQueries({ queryKey: ["reporte"] });
    },
  });
}

// ── Presupuesto ──────────────────────────────────────────────────────────────

export function usePresupuesto(
  periodo: string,
  puntoVenta: string,
): UseQueryResult<FilaPresupuesto[]> {
  return useQuery({
    queryKey: claves.presupuesto(periodo, puntoVenta),
    queryFn: () =>
      peticion<FilaPresupuesto[]>("/presupuesto", {
        parametros: { periodo, punto_venta: puntoVenta },
      }),
    enabled: puntoVenta !== "",
    staleTime: 60_000,
  });
}

export function useHistorialPresupuesto(
  periodo: string,
  puntoVenta: string,
): UseQueryResult<CambioPresupuesto[]> {
  return useQuery({
    queryKey: claves.historialPresupuesto(periodo, puntoVenta),
    queryFn: () =>
      peticion<CambioPresupuesto[]>("/presupuesto/historial", {
        parametros: { periodo, punto_venta: puntoVenta },
      }),
    enabled: puntoVenta !== "",
    staleTime: 30_000,
  });
}

/** Invalida todo lo que un cambio de presupuesto puede haber movido. */
function useInvalidarPresupuesto(periodo: string, puntoVenta: string) {
  const cliente = useQueryClient();
  return () => {
    void cliente.invalidateQueries({
      queryKey: claves.presupuesto(periodo, puntoVenta),
    });
    void cliente.invalidateQueries({
      queryKey: claves.historialPresupuesto(periodo, puntoVenta),
    });
    void cliente.invalidateQueries({ queryKey: ["presupuesto"] });
    void cliente.invalidateQueries({ queryKey: ["reporte"] });
  };
}

export function useGuardarPresupuesto(
  periodo: string,
  puntoVenta: string,
): UseMutationResult<void, Error, EntradaPresupuesto> {
  const invalidar = useInvalidarPresupuesto(periodo, puntoVenta);
  return useMutation({
    mutationFn: (datos) =>
      peticion<void>("/presupuesto", { metodo: "PUT", cuerpo: datos }),
    onSuccess: invalidar,
  });
}

export function useCargaMasivaPresupuesto(
  periodo: string,
  puntoVenta: string,
): UseMutationResult<ResultadoCargaMasiva, Error, File> {
  const invalidar = useInvalidarPresupuesto(periodo, puntoVenta);
  return useMutation({
    mutationFn: (archivo) =>
      enviarArchivo<ResultadoCargaMasiva>(
        "/presupuesto/carga-masiva",
        archivo,
        { periodo },
      ),
    onSuccess: invalidar,
  });
}

export function usePeriodos(): UseQueryResult<Periodo[]> {
  return useQuery({
    queryKey: claves.periodos,
    queryFn: () => peticion<Periodo[]>("/periodos"),
    staleTime: 5 * 60_000,
  });
}

export function useCerrarPeriodo(): UseMutationResult<Periodo, Error, string> {
  const cliente = useQueryClient();
  return useMutation({
    mutationFn: (periodo) =>
      peticion<Periodo>(`/periodos/${periodo}/cerrar`, { metodo: "POST" }),
    onSuccess: () => {
      void cliente.invalidateQueries({ queryKey: claves.periodos });
      void cliente.invalidateQueries({ queryKey: ["presupuesto"] });
    },
  });
}

// ── Historia de venta ────────────────────────────────────────────────────────

export function useHistoriaVenta(
  periodo: string,
): UseQueryResult<HistoriaVenta[]> {
  return useQuery({
    queryKey: claves.historiaVenta(periodo),
    queryFn: () =>
      peticion<HistoriaVenta[]>("/historia-venta", {
        parametros: { periodo },
      }),
    enabled: periodo.length === 7,
  });
}

export function useGuardarHistoriaVenta(
  periodo: string,
): UseMutationResult<HistoriaVenta, Error, EntradaHistoriaVenta> {
  const cliente = useQueryClient();
  return useMutation({
    mutationFn: (datos) =>
      peticion<HistoriaVenta>("/historia-venta", {
        metodo: "PUT",
        cuerpo: datos,
      }),
    onSuccess: () => {
      void cliente.invalidateQueries({ queryKey: claves.historiaVenta(periodo) });
      void cliente.invalidateQueries({ queryKey: ["reporte"] });
    },
  });
}

// ── Ingesta ──────────────────────────────────────────────────────────────────

export function useCorridasIngesta(): UseQueryResult<CorridaIngesta[]> {
  return useQuery({
    queryKey: claves.corridas,
    queryFn: () => peticion<CorridaIngesta[]>("/ingesta/corridas"),
    staleTime: 30_000,
  });
}

export function useRechazosIngesta(
  id: number | null,
): UseQueryResult<RechazoIngesta[]> {
  return useQuery({
    queryKey: claves.rechazos(id ?? 0),
    queryFn: () =>
      peticion<RechazoIngesta[]>(`/ingesta/corridas/${id}/rechazos`),
    enabled: id !== null,
  });
}

function useInvalidarIngesta() {
  const cliente = useQueryClient();
  return () => {
    void cliente.invalidateQueries({ queryKey: claves.corridas });
    void cliente.invalidateQueries({ queryKey: claves.salud });
    // Una ingesta cambia la venta: los reportes que estén en pantalla ya no valen.
    void cliente.invalidateQueries({ queryKey: ["reporte"] });
  };
}

export function useEjecutarIngesta(): UseMutationResult<
  unknown,
  Error,
  EntradaIngesta
> {
  const invalidar = useInvalidarIngesta();
  return useMutation({
    mutationFn: (datos) =>
      peticion("/ingesta/ejecutar", { metodo: "POST", cuerpo: datos }),
    onSuccess: invalidar,
  });
}

export function useIngestaArchivo(): UseMutationResult<unknown, Error, File> {
  const invalidar = useInvalidarIngesta();
  return useMutation({
    mutationFn: (archivo) => enviarArchivo("/ingesta/archivo", archivo),
    onSuccess: invalidar,
  });
}

// ── Usuarios · administración de cuentas ─────────────────────────────────────

/**
 * Listado de cuentas. Solo el rol `ADMIN` recibe algo distinto de un 403.
 *
 * `habilitado` evita disparar la consulta —y con ella un 403 en la consola— en
 * las sesiones de los otros cuatro roles, que ni siquiera ven la entrada.
 */
export function useUsuarios(
  filtros: FiltrosUsuarios,
  habilitado: boolean,
): UseQueryResult<UsuarioAdministrado[]> {
  return useQuery({
    queryKey: claves.usuarios(filtros),
    queryFn: () =>
      peticion<UsuarioAdministrado[]>("/usuarios", {
        parametros: { rol: filtros.rol, activo: filtros.activo },
      }),
    enabled: habilitado,
    staleTime: 30_000,
  });
}

export function useAuditoriaUsuarios(
  usuarioId: number | null,
  limite: number,
  habilitado: boolean,
): UseQueryResult<EventoAuditoria[]> {
  return useQuery({
    queryKey: claves.auditoriaUsuarios(usuarioId, limite),
    queryFn: () =>
      peticion<EventoAuditoria[]>("/usuarios/auditoria", {
        parametros: { usuario_id: usuarioId, limite },
      }),
    enabled: habilitado,
    staleTime: 30_000,
  });
}

/** Invalida el listado y la auditoría: toda operación deja rastro en ambos. */
function useInvalidarUsuarios() {
  const cliente = useQueryClient();
  return () => {
    void cliente.invalidateQueries({ queryKey: ["usuarios"] });
  };
}

/**
 * Alta de cuenta.
 *
 * **La respuesta contiene la clave provisional en claro.** Quien llame a este
 * hook debe copiarla al estado del componente que la muestra y llamar acto
 * seguido a `reset()`; por eso la mutación se declara con `gcTime: 0`, para que
 * el secreto no sobreviva en la caché de mutaciones ni un segundo de más.
 */
export function useCrearUsuario(): UseMutationResult<
  UsuarioCreado,
  Error,
  EntradaUsuario
> {
  const invalidar = useInvalidarUsuarios();
  return useMutation({
    mutationFn: (datos) =>
      peticion<UsuarioCreado>("/usuarios", { metodo: "POST", cuerpo: datos }),
    gcTime: 0,
    onSuccess: invalidar,
  });
}

export function useActualizarUsuario(): UseMutationResult<
  UsuarioAdministrado,
  Error,
  { id: number; datos: CambioUsuario }
> {
  const invalidar = useInvalidarUsuarios();
  return useMutation({
    mutationFn: ({ id, datos }) =>
      peticion<UsuarioAdministrado>(`/usuarios/${id}`, {
        metodo: "PATCH",
        cuerpo: datos,
      }),
    onSuccess: invalidar,
  });
}

/**
 * Fija el alcance por punto de venta.
 *
 * `PUT` **reemplaza** la lista completa: lo que se envía es lo que queda. La
 * pantalla manda siempre el conjunto entero resultante, nunca un delta; enviar
 * solo lo añadido borraría todo lo demás.
 */
export function useFijarPuntosVenta(): UseMutationResult<
  UsuarioAdministrado,
  Error,
  { id: number; puntos_venta: string[] }
> {
  const invalidar = useInvalidarUsuarios();
  return useMutation({
    mutationFn: ({ id, puntos_venta }) =>
      peticion<UsuarioAdministrado>(`/usuarios/${id}/puntos-venta`, {
        metodo: "PUT",
        cuerpo: { puntos_venta },
      }),
    onSuccess: invalidar,
  });
}

/** Activar o desactivar. No hay borrado: la baja es la desactivación (regla 3). */
export function useCambiarEstadoUsuario(): UseMutationResult<
  UsuarioAdministrado,
  Error,
  { id: number; activar: boolean }
> {
  const invalidar = useInvalidarUsuarios();
  return useMutation({
    mutationFn: ({ id, activar }) =>
      peticion<UsuarioAdministrado>(
        `/usuarios/${id}/${activar ? "activar" : "desactivar"}`,
        {
          metodo: "POST",
        },
      ),
    onSuccess: invalidar,
  });
}

export function useCambiarPermisoUsuario(): UseMutationResult<
  UsuarioAdministrado,
  Error,
  { id: number; codigo: string; asignar: boolean }
> {
  const invalidar = useInvalidarUsuarios();
  return useMutation({
    mutationFn: ({ id, codigo, asignar }) =>
      peticion<UsuarioAdministrado>(
        `/usuarios/${id}/permisos${asignar ? "" : `/${codigo}`}`,
        {
          metodo: asignar ? "POST" : "DELETE",
          ...(asignar ? { cuerpo: { codigo } } : {}),
        },
      ),
    onSuccess: invalidar,
  });
}

/**
 * Restablece la clave y devuelve otra provisional.
 *
 * Mismas precauciones que el alta: `gcTime: 0` y `reset()` inmediato en cuanto
 * el componente se queda con el valor.
 */
export function useRestablecerClave(): UseMutationResult<
  ClaveRestablecida,
  Error,
  number
> {
  const invalidar = useInvalidarUsuarios();
  return useMutation({
    mutationFn: (id) =>
      peticion<ClaveRestablecida>(`/usuarios/${id}/restablecer-clave`, {
        metodo: "POST",
      }),
    gcTime: 0,
    onSuccess: invalidar,
  });
}
