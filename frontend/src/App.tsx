/** Composición de la aplicación: rutas y guardias de acceso. */

import { Navigate, Route, Routes } from "react-router-dom";
import type { ReactNode } from "react";

import type { Rol } from "@/api/tipos";
import { useAuth } from "@/auth/ContextoAuth";
import { Cargando, Vacio } from "@/componentes/comunes";
import { Disposicion } from "@/componentes/Disposicion";

import { Acceso } from "@/paginas/Acceso";
import { Calendario } from "@/paginas/Calendario";
import { CambioClaveObligatorio } from "@/paginas/CambioClave";
import { Clientes } from "@/paginas/Clientes";
import { Cumplimiento } from "@/paginas/Cumplimiento";
import { Ingesta } from "@/paginas/Ingesta";
import { Presupuesto } from "@/paginas/Presupuesto";
import { Tablero } from "@/paginas/Tablero";
import { Usuarios } from "@/paginas/Usuarios";
import { VentaDiaria } from "@/paginas/VentaDiaria";

/**
 * Guardia por rol.
 *
 * No sustituye a la autorización del backend —esa es la que cuenta— pero evita
 * que un usuario llegue por enlace directo a una pantalla que solo le va a
 * devolver 403 sin explicación.
 */
function Restringido({ roles, children }: { roles: Rol[]; children: ReactNode }) {
  const { tieneRol } = useAuth();

  if (!tieneRol(...roles)) {
    return (
      <Vacio
        titulo="No tiene permiso para esta pantalla"
        detalle={`Requiere uno de estos roles: ${roles.join(", ")}.`}
      />
    );
  }

  return <>{children}</>;
}


export function App() {
  const { autenticado, cargando, debeCambiarClave } = useAuth();

  // Mientras se resuelve el perfil no se decide nada: renderizar el acceso por
  // un instante y sacarlo después produce un parpadeo desconcertante.
  if (cargando) return <Cargando texto="Verificando sesión…" />;

  if (!autenticado) return <Acceso />;

  // La clave provisional bloquea la aplicación entera, y el corte va **antes**
  // del enrutador: no hay `<Routes>` montado, así que escribir «/presupuesto» en
  // la barra de direcciones tampoco lleva a ninguna parte. Un guardia por ruta
  // habría dejado abierta cualquier ruta que alguien añada mañana sin acordarse
  // de envolverla.
  if (debeCambiarClave) return <CambioClaveObligatorio />;

  return (
    <Routes>
      <Route element={<Disposicion />}>
        <Route index element={<Tablero />} />
        <Route path="cumplimiento" element={<Cumplimiento />} />
        <Route path="venta-diaria" element={<VentaDiaria />} />
        <Route path="clientes" element={<Clientes />} />

        <Route
          path="presupuesto"
          element={
            <Restringido roles={["ADMIN", "GERENTE", "ANALISTA"]}>
              <Presupuesto />
            </Restringido>
          }
        />
        <Route path="calendario" element={<Calendario />} />
        <Route path="ingesta" element={<Ingesta />} />
        {/* Administración de cuentas: `ADMIN` y nadie más. El guardia no
            sustituye al 403 del backend —esa es la autorización que cuenta—,
            pero evita que un `JEFE_PDV` que teclea la URL vea una pantalla rota
            en lugar de una explicación. */}
        <Route
          path="usuarios"
          element={
            <Restringido roles={["ADMIN"]}>
              <Usuarios />
            </Restringido>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
