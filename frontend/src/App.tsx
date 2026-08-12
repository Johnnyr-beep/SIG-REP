/** Composición de la aplicación: rutas y guardias de acceso. */

import { Navigate, Route, Routes } from "react-router-dom";
import type { ReactNode } from "react";

import type { Rol } from "@/api/tipos";
import { useAuth } from "@/auth/ContextoAuth";
import { Cargando, Vacio } from "@/componentes/comunes";
import { Disposicion } from "@/componentes/Disposicion";
import { Acceso } from "@/paginas/Acceso";
import { Calendario } from "@/paginas/Calendario";
import { Clientes } from "@/paginas/Clientes";
import { Cumplimiento } from "@/paginas/Cumplimiento";
import { Ingesta } from "@/paginas/Ingesta";
import { Presupuesto } from "@/paginas/Presupuesto";
import { Tablero } from "@/paginas/Tablero";
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
  const { autenticado, cargando } = useAuth();

  // Mientras se resuelve el perfil no se decide nada: renderizar el acceso por
  // un instante y sacarlo después produce un parpadeo desconcertante.
  if (cargando) return <Cargando texto="Verificando sesión…" />;

  if (!autenticado) return <Acceso />;

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
            <Restringido roles={["GERENTE", "ANALISTA"]}>
              <Presupuesto />
            </Restringido>
          }
        />
        <Route path="calendario" element={<Calendario />} />
        <Route path="ingesta" element={<Ingesta />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
