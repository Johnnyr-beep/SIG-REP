import { useMemo } from "react";

import { useResumenAgro, useVentasComercialesAgro } from "@/api/consultasAgro";
import type { FilaVentaComercialAgro } from "@/api/tiposAgro";
import { AvisoError, Cargando, Tarjeta, Vacio } from "@/componentes/comunes";
import { BarraFiltrosAgro, filtrosAgroDe, useFiltros } from "@/componentes/filtros";
import { Indicador } from "@/componentes/indicadores";
import { dinero, kilos, sumar } from "@/utilidades/formato";

const CATEGORIAS = [
  ["CORT", "Cortes"],
  ["SUBPRODUCT", "Subproductos"],
  ["SACRIFIC", "Sacrificio"],
  ["DESPOST", "Desposte"],
  ["CANAL", "Canales"],
] as const;

export function ReportesVentasAgro() {
  const control = useFiltros();
  const filtros = useMemo(() => filtrosAgroDe(control.filtros), [control.filtros]);
  const comerciales = useVentasComercialesAgro(filtros);
  const tipoItem = useResumenAgro(filtros, "tipo_item");
  const especie = useResumenAgro(filtros, "especie");

  return (
    <div className="pila">
      <BarraFiltrosAgro control={control} />
      <AvisoError error={comerciales.error ?? tipoItem.error ?? especie.error} />
      {comerciales.isLoading || tipoItem.isLoading || especie.isLoading ? (
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
            <Tarjeta
              titulo="Ventas TAT"
              descripcion="Tipo comercial TAT, separado para lectura rápida."
            >
              <DesgloseTAT filas={filtrar(comerciales.data.filas, "TAT")} />
            </Tarjeta>
          </div>
        </>
      ) : null}
    </div>
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

function DesgloseTAT({ filas }: { filas: FilaVentaComercialAgro[] }) {
  if (!filas.length) return <Vacio titulo="Sin ventas TAT en este corte" />;
  return (
    <ul className="reportes-comerciales__lista">
      {filas.map((fila) => (
        <li key={`${fila.especie}-${fila.tipo_comercial}`}>
          <span>
            <strong>{fila.especie}</strong>
            <small>{kilos(fila.kilos)}</small>
          </span>
          <strong>{dinero(fila.venta_valor)}</strong>
        </li>
      ))}
    </ul>
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
