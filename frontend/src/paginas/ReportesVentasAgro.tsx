import { useMemo } from "react";

import { useResumenAgro, useVentasComercialesAgro } from "@/api/consultasAgro";
import type { FilaVentaComercialAgro } from "@/api/tiposAgro";
import { AvisoError, Cargando, Tarjeta, Vacio } from "@/componentes/comunes";
import { BarraFiltrosAgro, filtrosAgroDe, useFiltros } from "@/componentes/filtros";
import { dinero, kilos } from "@/utilidades/formato";

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
          <section className="inteligencia__encabezado">
            <div>
              <p className="inteligencia__eyebrow">Reportes comerciales</p>
              <h2>Lecturas específicas de la venta</h2>
              <p className="suave">
                Corte al {comerciales.data.fecha_corte}. Los valores excluyen impuestos.
              </p>
            </div>
          </section>
          <div className="inteligencia__dos-columnas">
            <Tarjeta titulo="Ventas por bienes y servicios" sinRelleno>
              <TablaResumen filas={tipoItem.data.filas.map((fila) => ({
                nombre: fila.nombre,
                valor: fila.venta_valor,
                peso: fila.kilos,
              }))} />
            </Tarjeta>
            <Tarjeta titulo="Ventas por especie" sinRelleno>
              <TablaResumen filas={especie.data.filas.map((fila) => ({
                nombre: fila.nombre,
                valor: fila.venta_valor,
                peso: fila.kilos,
              }))} />
            </Tarjeta>
          </div>
          <Tarjeta titulo="Ventas TAT" descripcion="Tipo comercial TAT, separado por especie." sinRelleno>
            <TablaCategoria filas={filtrar(comerciales.data.filas, "TAT")} />
          </Tarjeta>
          {CATEGORIAS.map(([patron, titulo]) => (
            <Tarjeta key={patron} titulo={`${titulo} de res y cerdo`} sinRelleno>
              <TablaCategoria filas={filtrar(comerciales.data.filas, patron)} />
            </Tarjeta>
          ))}
        </>
      ) : null}
    </div>
  );
}

function filtrar(filas: FilaVentaComercialAgro[], patron: string) {
  return filas.filter((fila) => normalizar(fila.tipo_comercial).includes(patron));
}

function normalizar(valor: string) {
  return valor.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toUpperCase();
}

function TablaResumen({ filas }: { filas: { nombre: string; valor: string; peso: string }[] }) {
  return <Tabla filas={filas.map((fila) => ({ especie: fila.nombre, ...fila }))} />;
}

function TablaCategoria({ filas }: { filas: FilaVentaComercialAgro[] }) {
  return <Tabla filas={filas.map((fila) => ({ especie: fila.especie, nombre: fila.tipo_comercial, valor: fila.venta_valor, peso: fila.kilos }))} />;
}

function Tabla({ filas }: { filas: { especie: string; nombre: string; valor: string; peso: string }[] }) {
  if (!filas.length) return <Vacio titulo="Sin ventas para este corte" />;
  return (
    <div className="tabla-envoltorio">
      <table className="tabla">
        <thead><tr><th>Especie</th><th>Tipo comercial</th><th className="numero">Venta</th><th className="numero">Kilos</th></tr></thead>
        <tbody>{filas.map((fila) => <tr key={`${fila.especie}-${fila.nombre}`}><th scope="row">{fila.especie}</th><td>{fila.nombre}</td><td className="numero">{dinero(fila.valor)}</td><td className="numero">{kilos(fila.peso)}</td></tr>)}</tbody>
      </table>
    </div>
  );
}
