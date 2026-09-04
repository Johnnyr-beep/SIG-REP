import { useMemo, useState } from "react";

import {
  type FiltrosUsuarios,
  useCambiarPermisoUsuario,
  useUsuarios,
} from "@/api/consultas";
import type { UsuarioAdministrado } from "@/api/tipos";
import { AvisoError, Cargando, Distintivo, Tarjeta, Vacio } from "@/componentes/comunes";
import { useMarcaElegida } from "@/marca/ContextoMarca";

const PERMISOS = [
  ["PERMISO_CONSULTAR_PDV", "Consultar puntos de venta"],
  ["PERMISO_VENTA_DIARIA_ASADERO", "Consultar venta diaria de Asadero"],
  ["PERMISO_CONSULTAR_TABLERO", "Consultar tablero"],
  ["PERMISO_CONSULTAR_CUMPLIMIENTO", "Consultar cumplimiento"],
  ["PERMISO_CONSULTAR_COSTOS", "Consultar costos y margen"],
  ["PERMISO_COSTO_POR_GRUPO", "Consultar costo por grupo"],
  ["PERMISO_COSTO_POR_PDV", "Consultar costo por punto de venta"],
  ["PERMISO_COSTO_POR_CATEGORIA", "Consultar costo por categoría"],
  ["PERMISO_CONSULTAR_VENTA_DIARIA", "Consultar venta diaria"],
  ["PERMISO_CONSULTAR_CLIENTES", "Consultar clientes y vendedores"],
  ["PERMISO_CONSULTAR_PRESUPUESTO", "Consultar presupuesto"],
  ["PERMISO_CONSULTAR_CALENDARIO", "Consultar calendario"],
  ["PERMISO_CONSULTAR_INGESTA", "Consultar ingesta"],
  ["PERMISO_CONSULTAR_HISTORIA", "Consultar venta del año anterior"],
  ["PERMISO_FILTRAR_PDV", "Filtrar por punto de venta"],
  ["PERMISO_FILTRAR_GRUPO", "Filtrar por grupo"],
  ["PERMISO_FILTRAR_CATEGORIA", "Filtrar por categoría"],
  ["PERMISO_FILTRAR_PERIODO", "Filtrar por período y corte"],
  ["PERMISO_FILTRAR_MEDIDA", "Cambiar entre pesos y kilos"],
  ["PERMISO_DESCARGAR_TABLERO", "Descargar tablero a Excel"],
  ["PERMISO_DESCARGAR_CUMPLIMIENTO", "Descargar cumplimiento a Excel"],
  ["PERMISO_DESCARGAR_VENTA_DIARIA", "Descargar venta diaria a Excel"],
  ["PERMISO_DESCARGAR_VENTA_DIARIA_ASADERO", "Descargar venta diaria de Asadero a Excel"],
  ["PERMISO_DESCARGAR_CLIENTES", "Descargar clientes y vendedores a Excel"],
] as const;

const PERMISOS_AGRO = [
  ["PERMISO_AGRO_CONSULTAR_RESUMEN", "Consulta: resumen de ventas"],
  ["PERMISO_AGRO_CONSULTAR_REPORTES_VENTAS", "Consulta: reportes de ventas"],
  ["PERMISO_AGRO_CONSULTAR_CUBO_COMERCIAL", "Consulta: cubo comercial"],
  ["PERMISO_AGRO_CONSULTAR_CRUCE_COMERCIAL", "Consulta: cruce comercial"],
  ["PERMISO_AGRO_CONSULTAR_VENTA_DIARIA", "Consulta: venta diaria"],
  ["PERMISO_AGRO_CONSULTAR_INTELIGENCIA_COMERCIAL", "Consulta: inteligencia comercial"],
  ["PERMISO_AGRO_CONSULTAR_TAT", "Consulta: ventas TAT"],
  ["PERMISO_AGRO_CONSULTAR_PRESUPUESTO", "Consulta: presupuesto"],
  ["PERMISO_AGRO_CONSULTAR_CALENDARIO", "Consulta: calendario"],
  ["PERMISO_AGRO_CONSULTAR_INGESTA", "Consulta: ingesta"],
  ["PERMISO_AGRO_FILTRAR_PERIODO", "Filtros y vistas: período y rango"],
  ["PERMISO_AGRO_FILTRAR_CENTRO", "Filtros y vistas: centro"],
  ["PERMISO_AGRO_FILTRAR_MEDIDA", "Filtros y vistas: medida kilos"],
  ["PERMISO_AGRO_CONFIGURAR_EJE_RESUMEN", "Filtros y vistas: eje del resumen"],
  ["PERMISO_AGRO_CONFIGURAR_EJE_CRUCE", "Filtros y vistas: eje del cruce"],
  ["PERMISO_AGRO_CONFIGURAR_DIMENSIONES_CUBO", "Filtros y vistas: dimensiones del cubo"],
  ["PERMISO_AGRO_DESCARGAR_RESUMEN", "Descargas: resumen"],
  ["PERMISO_AGRO_DESCARGAR_CRUCE", "Descargas: cruce"],
  ["PERMISO_AGRO_DESCARGAR_VENTA_DIARIA", "Descargas: venta diaria"],
] as const;

export function Permisos() {
  const marca = useMarcaElegida();
  const [filtros] = useState<FiltrosUsuarios>({ rol: "", activo: "" });
  const { data: usuarios, isLoading, error } = useUsuarios(filtros, true);
  const cambiar = useCambiarPermisoUsuario();
  const filas = useMemo(() => usuarios ?? [], [usuarios]);

  return (
    <div className="pila">
      <Tarjeta
        titulo="Permisos de consulta"
        descripcion="Asigna a cada usuario los módulos que puede consultar. Los permisos no permiten editar información."
      >
        <AvisoError error={error} />
        <AvisoError error={cambiar.error} />
        {isLoading ? <Cargando texto="Cargando usuarios…" /> : null}
        {!isLoading && filas.length === 0 ? (
          <Vacio titulo="Sin usuarios" detalle="No hay cuentas para asignar permisos." />
        ) : (
          <div className="tabla-envoltorio">
            <table className="tabla tabla--anclada">
              <thead>
                <tr>
                  <th scope="col" className="columna-ancla">Usuario</th>
                  <th scope="col">Rol</th>
                  <th scope="col">Estado</th>
                  <th scope="col">Permisos de consulta</th>
                </tr>
              </thead>
              <tbody>
                {filas.map((cuenta) => (
                  <FilaPermisos
                    key={cuenta.id}
                    cuenta={cuenta}
                    cambiando={cambiar.isPending}
                    permisos={marca.clave === "agropecuaria" ? PERMISOS_AGRO : PERMISOS}
                    onCambiar={(codigo, asignar) =>
                      cambiar.mutate({ id: cuenta.id, codigo, asignar })
                    }
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Tarjeta>
    </div>
  );
}

function FilaPermisos({
  cuenta,
  cambiando,
  permisos,
  onCambiar,
}: {
  cuenta: UsuarioAdministrado;
  cambiando: boolean;
  permisos: readonly (readonly [string, string])[];
  onCambiar: (codigo: string, asignar: boolean) => void;
}) {
  return (
    <tr>
      <th scope="row" className="columna-ancla">
        <span className="mono">{cuenta.usuario}</span>
        <span className="columna-ancla__nota">{cuenta.nombre}</span>
      </th>
      <td><Distintivo tono={cuenta.rol === "ADMIN" ? "info" : "neutro"}>{cuenta.rol}</Distintivo></td>
      <td><Distintivo tono={cuenta.activo ? "exito" : "neutro"}>{cuenta.activo ? "Activa" : "Inactiva"}</Distintivo></td>
      <td>
        <div className="permisos-usuario">
          {permisos.map(([codigo, nombre]) => {
            const asignado = cuenta.permisos.includes(codigo);
            return (
              <button
                key={codigo}
                type="button"
                className={`boton boton--pequeno boton--sutil${asignado ? " boton--permiso-activo" : ""}`}
                onClick={() => onCambiar(codigo, !asignado)}
                disabled={!cuenta.activo || cambiando}
                title={asignado ? `Retirar: ${nombre}` : `Asignar: ${nombre}`}
              >
                {asignado ? "✓" : "+"} {nombre}
              </button>
            );
          })}
        </div>
      </td>
    </tr>
  );
}
