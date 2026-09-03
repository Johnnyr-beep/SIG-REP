import { useMemo } from "react";

import { useResumenAgro, useVentasComercialesAgro } from "@/api/consultasAgro";
import { useVentasTat } from "@/api/consultasTat";
import type { AgroTatVenta } from "@/api/tipos";
import type { FilaVentaComercialAgro } from "@/api/tiposAgro";
import { useMarcaElegida } from "@/marca/ContextoMarca";
import { AvisoError, Cargando, Tarjeta, Vacio } from "@/componentes/comunes";
import { BarraFiltrosAgro, filtrosAgroDe, useFiltros } from "@/componentes/filtros";
import { Indicador } from "@/componentes/indicadores";
import { dinero, finDeMes, kilos, numero, sumar } from "@/utilidades/formato";

const CATEGORIAS = [
  ["CORT", "Cortes"],
  ["SUBPRODUCT", "Subproductos"],
  ["SACRIFIC", "Sacrificio"],
  ["DESPOST", "Desposte"],
  ["CANAL", "Canales"],
] as const;

export function ReportesVentasAgro() {
  const marca = useMarcaElegida();
  const esAgropecuaria = marca.clave === "agropecuaria";
  const control = useFiltros();
  const filtros = useMemo(() => filtrosAgroDe(control.filtros), [control.filtros]);
  const comerciales = useVentasComercialesAgro(filtros);
  const tipoItem = useResumenAgro(filtros, "tipo_item");
  const especie = useResumenAgro(filtros, "especie");
  const tat = useVentasTat({
    fecha_inicio: `${filtros.periodo}-01`,
    fecha_fin: filtros.hasta ?? finDeMes(filtros.periodo) ?? `${filtros.periodo}-01`,
    limit: 100,
    offset: 0,
  }, esAgropecuaria);

  return (
    <div className="pila">
      <BarraFiltrosAgro control={control} mostrar={{ rango: true }} />
      <AvisoError error={comerciales.error ?? tipoItem.error ?? especie.error ?? tat.error} />
      {comerciales.isLoading || tipoItem.isLoading || especie.isLoading || tat.isLoading ? (
        <Cargando texto="Preparando reportes de ventas…" />
      ) : null}
      {comerciales.data && tipoItem.data && especie.data ? (
        <>
          <section className="reportes-comerciales__cabecera">
            <div>
              <p className="inteligencia__eyebrow">Reportes comerciales</p>
              <h2>Venta por línea de negocio</h2>
              <p className="suave">
                Corte al {comerciales.data.fecha_corte}. Valores netos, sin impuestos.
              </p>
            </div>
          </section>

          <section className="rejilla rejilla--indicadores" aria-label="Resumen de ventas">
            <Indicador
              etiqueta="Total comercial"
              valor={dinero(
                totalCuatroComponentes(tipoItem.data.filas, especie.data.filas, "venta_valor"),
              )}
              nota={`${kilos(
                totalCuatroComponentes(tipoItem.data.filas, especie.data.filas, "kilos"),
              )} en Bienes, Servicios, Res y Cerdo`}
            />
            {tipoItem.data.filas.map((fila) => (
              <Indicador
                key={fila.clave}
                etiqueta={fila.nombre}
                valor={dinero(fila.venta_valor)}
                nota={`${kilos(fila.kilos)} vendidos`}
              />
            ))}
            {especie.data.filas
              .filter((fila) => ["RES", "CERDO"].includes(normalizar(fila.nombre)))
              .map((fila) => (
                <Indicador
                  key={fila.clave}
                  etiqueta={`Venta ${fila.nombre}`}
                  valor={dinero(fila.venta_valor)}
                  nota={`${kilos(fila.kilos)} vendidos`}
                />
              ))}
          </section>

          <div className="reportes-comerciales__principal">
            <Tarjeta
              titulo="Categorías por especie"
              descripcion="Comparación directa de res y cerdo por cada línea comercial."
              sinRelleno
            >
              <MatrizCategorias filas={comerciales.data.filas} />
            </Tarjeta>
            {esAgropecuaria && tat.data ? (
              <Tarjeta
                titulo="Ventas TAT"
                descripcion="Facturación TAT separada para lectura rápida."
              >
                <DesgloseTAT
                  filas={tat.data.filas}
                  totalCantidad={tat.data.total_cantidad}
                  totalSubtotal={tat.data.total_subtotal}
                />
              </Tarjeta>
            ) : null}
          </div>
        </>
      ) : null}
    </div>
  );
}

/**
 * Total que pidió gerencia para la cabecera: Bienes + Servicios + venta de Res
 * + venta de Cerdo. Las cuatro cifras se conservan separadas justo después para
 * que su composición permanezca comprobable a simple vista.
 */
function totalCuatroComponentes(
  tiposItem: { nombre: string; venta_valor: string; kilos: string }[],
  especies: { nombre: string; venta_valor: string; kilos: string }[],
  medida: "venta_valor" | "kilos",
) {
  const bienesServicios = tiposItem.filter((fila) =>
    ["BIENES", "SERVICIOS"].includes(normalizar(fila.nombre)),
  );
  const resCerdo = especies.filter((fila) =>
    ["RES", "CERDO"].includes(normalizar(fila.nombre)),
  );
  return [...bienesServicios, ...resCerdo].reduce(
    (total, fila) => sumar(total, fila[medida]) ?? total,
    "0",
  );
}

function MatrizCategorias({ filas }: { filas: FilaVentaComercialAgro[] }) {
  return (
    <div className="tabla-envoltorio">
      <table className="tabla">
        <thead>
          <tr>
            <th>Categoría</th>
            <th className="numero">Res</th>
            <th className="numero">Cerdo</th>
            <th className="numero">Total</th>
          </tr>
        </thead>
        <tbody>
          {CATEGORIAS.map(([patron, etiqueta]) => {
            const categoria = filtrar(filas, patron);
            const res = porEspecie(categoria, "RES");
            const cerdo = porEspecie(categoria, "CERDO");
            return (
              <tr key={patron}>
                <th scope="row">{etiqueta}</th>
                <td className="numero">{res ? dinero(res.venta_valor) : "—"}</td>
                <td className="numero">{cerdo ? dinero(cerdo.venta_valor) : "—"}</td>
                <td className="numero">{dinero(sumaVenta(categoria))}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function DesgloseTAT({
  filas,
  totalCantidad,
  totalSubtotal,
}: {
  filas: AgroTatVenta[];
  totalCantidad: string;
  totalSubtotal: string;
}) {
  if (!filas.length) return <Vacio titulo="Sin ventas TAT en este corte" />;
  return (
    <div className="rejilla rejilla--indicadores">
      <div className="indicador">
        <span className="indicador__etiqueta">Cantidad total</span>
        <strong className="indicador__valor indicador__valor--mediano">
          {numero(totalCantidad, 2)}
        </strong>
        <span className="indicador__nota">Registros visibles: {numero(filas.length)}</span>
      </div>
      <div className="indicador">
        <span className="indicador__etiqueta">Venta subtotal</span>
        <strong className="indicador__valor indicador__valor--mediano">
          {dinero(totalSubtotal)}
        </strong>
        <span className="indicador__nota">Total del rango consultado</span>
      </div>
    </div>
  );
}

function filtrar(filas: FilaVentaComercialAgro[], patron: string) {
  return filas.filter((fila) => normalizar(fila.tipo_comercial).includes(patron));
}

function porEspecie(filas: FilaVentaComercialAgro[], especie: string) {
  return filas.find((fila) => normalizar(fila.especie) === especie);
}

function sumaVenta(filas: FilaVentaComercialAgro[]) {
  return filas.reduce(
    (total, fila) => sumar(total, fila.venta_valor) ?? total,
    "0",
  );
}

function normalizar(valor: string) {
  return valor.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toUpperCase();
}
