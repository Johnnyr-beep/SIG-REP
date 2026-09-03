/** Composición de la aplicación: rutas y guardias de acceso. */

import { Navigate, Route, Routes } from "react-router-dom";
import type { ReactNode } from "react";

import type { Rol } from "@/api/tipos";
import { useAuth } from "@/auth/ContextoAuth";
import { Cargando, Vacio } from "@/componentes/comunes";
import { Disposicion } from "@/componentes/Disposicion";
import { useMarca } from "@/marca/ContextoMarca";

import { Acceso } from "@/paginas/Acceso";
import { Calendario } from "@/paginas/Calendario";
import { CalendarioAgro } from "@/paginas/CalendarioAgro";
import { CruceAgro } from "@/paginas/CruceAgro";
import { CuboComercialAgro } from "@/paginas/CuboComercialAgro";
import { IngestaAgro } from "@/paginas/IngestaAgro";
import { InteligenciaAgro } from "@/paginas/InteligenciaAgro";
import { PresupuestoAgro } from "@/paginas/PresupuestoAgro";
import { ReportesVentasAgro } from "@/paginas/ReportesVentasAgro";
import { ResumenAgro } from "@/paginas/ResumenAgro";
import { VentaDiariaAgro } from "@/paginas/VentaDiariaAgro";
import { CambioClaveObligatorio } from "@/paginas/CambioClave";
import { Clientes } from "@/paginas/Clientes";
import { Cumplimiento } from "@/paginas/Cumplimiento";
import { Costos } from "@/paginas/Costos";
import { Ingesta } from "@/paginas/Ingesta";
import { HistoriaVenta } from "@/paginas/HistoriaVenta";
import { Presupuesto } from "@/paginas/Presupuesto";
import { SelectorMarca } from "@/paginas/SelectorMarca";
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
function Restringido({
  roles,
  children,
}: {
  roles: Rol[];
  children: ReactNode;
}) {
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
  const { marca } = useMarca();
  const { autenticado, cargando, debeCambiarClave } = useAuth();

  // Primer corte, antes que ninguno: sin unidad de negocio elegida no hay logo
  // que enseñar ni paleta que aplicar, y el acceso pediría credenciales sin
  // decir a qué. Va delante del resto de guardias, no dentro del enrutador.
  if (!marca) return <SelectorMarca />;

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

  // Cada unidad monta **solo sus rutas**. No es cosmetica: agropecuaria es otra
  // compania, con su propia API de origen (`id_cia=3`) y sus propias cifras, y
  // las unidades no se mezclan.
  //
  // Antes las rutas de carnes estaban montadas siempre y solo cambiaba el menu,
  // con tres consecuencias que nadie veia hasta teclear una direccion: `/` era
  // el tablero de carnes —justo donde aterriza quien acaba de entrar—, el
  // comodin mandaba alli, y escribir `/cumplimiento` desde agropecuaria abria
  // las cifras de la otra compania. Un menu que no enlaza no es una puerta
  // cerrada.
  const esAgro = marca.clave === "agropecuaria";
  const esCarnesFrias = marca.clave === "carnes-frias";

  return (
    <Routes>
      <Route element={<Disposicion />}>
        {esAgro || esCarnesFrias ? (
          <>
            {/* Las pantallas conservan el prefijo `/agro` en vez de subir a la
                raiz: un enlace pegado en un correo dice a que unidad pertenece,
                y sigue abriendo lo mismo manana. */}
            <Route
              index
              element={<Navigate to={esCarnesFrias ? "/frias" : "/agro"} replace />}
            />
            <Route path={esCarnesFrias ? "frias" : "agro"}>
              <Route index element={<ResumenAgro />} />
              <Route path="cruce" element={<CruceAgro />} />
              <Route path="cubo-comercial" element={<CuboComercialAgro />} />
              <Route path="venta-diaria" element={<VentaDiariaAgro />} />
              <Route path="reportes-ventas" element={<ReportesVentasAgro />} />
              <Route
                path="presupuesto"
                element={
                  <Restringido roles={["ADMIN", "GERENTE", "ANALISTA"]}>
                    <PresupuestoAgro />
                  </Restringido>
                }
              />
              <Route path="calendario" element={<CalendarioAgro />} />
              <Route path="ingesta" element={<IngestaAgro />} />
              <Route path="inteligencia" element={<InteligenciaAgro />} />
            </Route>
          </>
        ) : (
          <>
            <Route index element={<Tablero />} />
            <Route path="cumplimiento" element={<Cumplimiento />} />
            <Route path="costos" element={<Costos />} />
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
            <Route
              path="historia-venta"
              element={
                <Restringido roles={["ADMIN", "GERENTE", "ANALISTA"]}>
                  <HistoriaVenta />
                </Restringido>
              }
            />
          </>
        )}

        {/* Administración de cuentas: `ADMIN` y nadie más, y la única pantalla
            común a las dos unidades porque las cuentas son del sistema, no de
            una compañía. El guardia no sustituye al 403 del backend —esa es la
            autorización que cuenta—, pero evita que un `JEFE_PDV` que teclea la
            URL vea una pantalla rota en lugar de una explicación. */}
        <Route
          path="usuarios"
          element={
            <Restringido roles={["ADMIN"]}>
              <Usuarios />
            </Restringido>
          }
        />

        {/* El comodín devuelve a la portada **de la unidad**. Mandarlo siempre a
            «/» era como se llegaba al tablero de carnes desde agropecuaria sin
            haberlo pedido. */}
        <Route
          path="*"
          element={
            <Navigate
              to={esAgro ? "/agro" : esCarnesFrias ? "/frias" : "/"}
              replace
            />
          }
        />
      </Route>
    </Routes>
  );
}
