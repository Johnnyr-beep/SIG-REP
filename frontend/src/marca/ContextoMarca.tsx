/**
 * Unidad de negocio elegida: estado, persistencia y adopción del tema.
 *
 * Toda la aplicación pregunta aquí de qué marca es. La adopción visual se hace
 * en un solo sitio —`data-marca` en `<html>`— y desde ahí `estilos.css`
 * reasigna la rampa `--marca-*`, de la que cuelgan `--acento`, `--acento-suave`
 * y el resto. Ningún componente conoce un color: conoce su marca.
 *
 * La elección se recuerda porque cada instancia sirve a una sola unidad: quien
 * ya eligió no debería volver a hacerlo cada mañana. Va en `localStorage`, no
 * en `sessionStorage`, precisamente por eso —los tokens son lo contrario y por
 * la razón contraria: caducan al cerrar el navegador a propósito—.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import type { ReactNode } from "react";

import type { ClaveMarca, Marca } from "@/marca/marcas";
import { almacenTokens } from "@/api/cliente";
import { obtenerMarca } from "@/marca/marcas";

const CLAVE_ALMACEN = "sigrep_marca";

interface ValorMarca {
  /** `null` mientras no se haya elegido: `App` planta el selector. */
  marca: Marca | null;
  elegir: (clave: ClaveMarca) => void;
  /** Vuelve al selector. Lo usa el enlace del acceso. */
  olvidar: () => void;
}

const ContextoMarca = createContext<ValorMarca | null>(null);

/**
 * Lectura defensiva: un `localStorage` bloqueado por política del navegador
 * lanza al leerlo, y quedarse sin selector de marca por eso sería absurdo.
 * Un valor que ya no corresponde a ninguna marca —una clave retirada— se
 * descarta y se vuelve a preguntar.
 */
function leerGuardada(): Marca | null {
  try {
    return obtenerMarca(localStorage.getItem(CLAVE_ALMACEN));
  } catch {
    return null;
  }
}

export function ProveedorMarca({ children }: { children: ReactNode }) {
  const [marca, setMarca] = useState<Marca | null>(leerGuardada);

  // El atributo y el almacén se sincronizan juntos: son la misma decisión vista
  // desde el navegador y desde la hoja de estilos.
  useEffect(() => {
    const raiz = document.documentElement;
    try {
      if (marca) {
        raiz.setAttribute("data-marca", marca.clave);
        localStorage.setItem(CLAVE_ALMACEN, marca.clave);
      } else {
        // Sin marca elegida, `:root` se queda con la rampa por defecto que
        // declara `estilos.css`, que es la de la instancia desplegada.
        raiz.removeAttribute("data-marca");
        localStorage.removeItem(CLAVE_ALMACEN);
      }
    } catch {
      // Si el almacén no está disponible la elección sigue valiendo para esta
      // sesión; solo se pierde el recuerdo.
    }
  }, [marca]);

  /**
   * Elegir unidad **cierra la sesión abierta**, si la hay y es de otra.
   *
   * Desde que cada compañía tiene su base, un token pertenece a una unidad y a
   * una sola: la lleva firmada dentro, y el servidor la respeta por encima de
   * cualquier cabecera. Cambiar de marca conservando el token dejaría al usuario
   * en las pantallas de agropecuaria consultando la base de carnes —o al revés—,
   * viendo tablas vacías sin ninguna explicación a la vista.
   *
   * Así que se limpia y se vuelve a pedir acceso, que además es lo correcto:
   * son dos empresas distintas y las credenciales de una no valen en la otra.
   */
  const elegir = useCallback(
    (clave: ClaveMarca) => {
      if (marca && marca.clave !== clave) almacenTokens.limpiar();
      setMarca(obtenerMarca(clave));
    },
    [marca],
  );

  const olvidar = useCallback(() => {
    almacenTokens.limpiar();
    setMarca(null);
  }, []);

  const valor = useMemo<ValorMarca>(
    () => ({ marca, elegir, olvidar }),
    [marca, elegir, olvidar],
  );

  return (
    <ContextoMarca.Provider value={valor}>{children}</ContextoMarca.Provider>
  );
}

export function useMarca(): ValorMarca {
  const contexto = useContext(ContextoMarca);
  if (!contexto) {
    throw new Error("useMarca debe usarse dentro de <ProveedorMarca>.");
  }
  return contexto;
}

/**
 * La marca ya elegida, para los componentes que se renderizan por debajo del
 * selector y no tienen por qué contemplar el caso `null`: para cuando la barra
 * lateral existe, elegir marca es cosa hecha.
 */
export function useMarcaElegida(): Marca {
  const { marca } = useMarca();
  if (!marca) {
    throw new Error(
      "No hay unidad de negocio elegida: esta pantalla va después del selector.",
    );
  }
  return marca;
}
