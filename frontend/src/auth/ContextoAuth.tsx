/** Sesión del usuario: estado, rol y ciclo de vida del token. */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import type { ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";

import {
  ErrorApi,
  almacenTokens,
  iniciarSesion,
  registrarExpiracionSesion,
} from "@/api/cliente";
import { usePerfil } from "@/api/consultas";
import type { Rol, Usuario } from "@/api/tipos";

interface ValorAuth {
  usuario: Usuario | null;
  cargando: boolean;
  autenticado: boolean;
  falloValidacionSesion: unknown | null;
  reintentarValidacionSesion: () => void;
  entrar: (usuario: string, clave: string) => Promise<void>;
  salir: () => void;

  /** `true` si el rol del usuario es alguno de los indicados. */
  tieneRol: (...roles: Rol[]) => boolean;
  /** Atajo: quien puede parametrizar presupuesto y calendario (§8.4). */
  puedeParametrizar: boolean;
  /**
   * La cuenta arrastra una clave provisional y no puede hacer nada más.
   *
   * Lo consume `App` para plantar la pantalla de cambio de clave en lugar del
   * enrutador entero: mientras valga `true` no hay ruta que renderizar, así que
   * escribir la URL a mano tampoco lleva a ninguna parte.
   */
  debeCambiarClave: boolean;
  /** Único rol que administra cuentas. Los otros cuatro reciben 403. */
  esAdmin: boolean;
  tienePermiso: (codigo: string) => boolean;
}

const ContextoAuth = createContext<ValorAuth | null>(null);

export function ProveedorAuth({ children }: { children: ReactNode }) {
  const [hayToken, setHayToken] = useState(
    () => almacenTokens.acceso() !== null,
  );
  const clienteConsultas = useQueryClient();

  const {
    data: usuario,
    isLoading,
    isError,
    error,
    refetch: refetchPerfil,
  } = usePerfil(hayToken);

  const salir = useCallback(() => {
    almacenTokens.limpiar();
    setHayToken(false);
    // Vaciar la caché al cerrar sesión evita que el siguiente usuario del mismo
    // equipo vea, aunque sea un instante, las cifras del anterior.
    clienteConsultas.clear();
  }, [clienteConsultas]);

  // El cliente HTTP avisa cuando una renovación falla definitivamente.
  useEffect(() => {
    registrarExpiracionSesion(salir);
  }, [salir]);

  // Solo un 401 confirma que la sesión expiró. Fallos de red/servidor conservan
  // el token para que el usuario pueda reintentar sin autenticarse de nuevo.
  useEffect(() => {
    if (isError && hayToken && error instanceof ErrorApi && error.esSesionExpirada) {
      salir();
    }
  }, [isError, hayToken, error, salir]);

  const reintentarValidacionSesion = useCallback(() => {
    void refetchPerfil();
  }, [refetchPerfil]);

  const entrar = useCallback(
    async (nombreUsuario: string, clave: string) => {
      await iniciarSesion(nombreUsuario, clave);
      setHayToken(true);
      void clienteConsultas.invalidateQueries({ refetchType: "active" });
    },
    [clienteConsultas],
  );

  const tieneRol = useCallback(
    (...roles: Rol[]) => (usuario ? roles.includes(usuario.rol) : false),
    [usuario],
  );

  const valor = useMemo<ValorAuth>(
    () => ({
      usuario: usuario ?? null,
      cargando: hayToken && isLoading,
      autenticado: hayToken && usuario !== undefined,
      falloValidacionSesion: isError ? error : null,
      reintentarValidacionSesion,
      entrar,
      salir,

      tieneRol,
      // `ADMIN` es además superusuario del negocio: el contrato lo hace entrar
      // en reportes, presupuesto, calendario e ingesta como `GERENTE`, para que
      // Sistemas pueda diagnosticar sin pedir prestada una cuenta de gerencia.
      puedeParametrizar: usuario
        ? usuario.rol === "ADMIN" ||
          usuario.rol === "GERENTE" ||
          usuario.rol === "ANALISTA"
        : false,
      debeCambiarClave: usuario?.debe_cambiar_password === true,
      esAdmin: usuario?.rol === "ADMIN",
      tienePermiso: (codigo) =>
        usuario?.rol === "ADMIN" || usuario?.permisos.includes(codigo) === true,
    }),
    [
      usuario,
      hayToken,
      isLoading,
      isError,
      error,
      reintentarValidacionSesion,
      entrar,
      salir,
      tieneRol,
    ],
  );

  return (
    <ContextoAuth.Provider value={valor}>{children}</ContextoAuth.Provider>
  );
}

export function useAuth(): ValorAuth {
  const contexto = useContext(ContextoAuth);
  if (!contexto) {
    throw new Error("useAuth debe usarse dentro de <ProveedorAuth>.");
  }
  return contexto;
}
