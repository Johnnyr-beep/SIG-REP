import { Fragment, useMemo, useState } from "react";

import {
  useDetalleVentasComercialesAgro,
  useResumenAgro,
  useVentasComercialesAgro,
} from "@/api/consultasAgro";
import type { FiltrosAgro } from "@/api/consultasAgro";
import { useVentasTat } from "@/api/consultasTat";
import type { AgroTatVenta } from "@/api/tipos";
import type {
  CategoriaVentaComercialAgro,
  FilaVentaComercialAgro,
} from "@/api/tiposAgro";
import { useMarcaElegida } from "@/marca/ContextoMarca";
import { AvisoError, Cargando, Tarjeta, Vacio } from "@/componentes/comunes";
import { BarraFiltrosAgro, filtrosAgroDe, useFiltros } from "@/componentes/filtros";
import { Indicador } from "@/componentes/indicadores";
import { dinero, finDeMes, kilos, numero, sumar } from "@/utilidades/formato";

const CATEGORIAS = [
  { categoria: "cortes", patron: "CORT", etiqueta: "Cortes" },
  { categoria: "subproductos", patron: "SUBPRODUCT", etiqueta: "Subproductos" },
  { categoria: "sacrificio", patron: "SACRIFIC", etiqueta: "Sacrificio" },
  { categoria: "desposte", patron: "DESPOST", etiqueta: "Desposte" },
  { categoria: "canales", patron: "CANAL", etiqueta: "Canales" },
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
    fecha_inicio: filtros.desde ?? `${filtros.periodo}-01`,
    fecha_fin: filtros.hasta ?? finDeMes(filtros.periodo) ?? `${filtros.periodo}-01`,
    limit: 100,
    offset: 0,
  }, esAgropecuaria);

  return (
    <div className="pila">
      <BarraFiltrosAgro control={control} mostrar={{ rango: true }} />
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
            <Indicador
              etiqueta="Total comercial"
              valor={dinero(tipoItem.data.consolidado.venta_valor)}
              nota={`${kilos(tipoItem.data.consolidado.kilos)} vendidos en el corte`}
              tono="exito"
            />
            {tipoItem.data.filas.map((fila) => (
              <Indicador
                key={fila.clave}
                etiqueta={fila.nombre}
                valor={dinero(fila.venta_valor)}
                nota={`${kilos(fila.kilos)} vendidos`}
                tono="exito"
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
                  tono="exito"
                />
              ))}
          </section>

          <div className="reportes-comerciales__principal">
            <Tarjeta
              titulo="Categorías por especie"
              descripcion="Comparación directa de res y cerdo por cada línea comercial."
              sinRelleno
            >
              <MatrizCategorias filas={comerciales.data.filas} filtros={filtros} />
            </Tarjeta>
            {esAgropecuaria ? (
              <Tarjeta
                titulo="Ventas TAT"
                descripcion="Facturación TAT separada para lectura rápida."
              >
                {tat.isLoading ? <Cargando texto="Consultando ventas TAT…" /> : null}
                {tat.error ? (
                  <p className="aviso aviso--advertencia" role="status">
                    Las ventas TAT no están disponibles en este momento. El resto del reporte sí está actualizado.
                  </p>
                ) : null}
                {tat.data ? (
                  <DesgloseTAT
                    filas={tat.data.filas}
                    totalCantidad={tat.data.total_cantidad}
                    totalSubtotal={tat.data.total_subtotal}
                  />
                ) : null}
              </Tarjeta>
            ) : null}
          </div>
        </>
      ) : null}
    </div>
  );
}

function MatrizCategorias({
  filas,
  filtros,
}: {
  filas: FilaVentaComercialAgro[];
  filtros: FiltrosAgro;
}) {
  const [expandida, setExpandida] = useState<CategoriaVentaComercialAgro | null>(null);
  const categorias = CATEGORIAS.map(({ categoria, patron, etiqueta }, indice) => {
    const grupo = filtrar(filas, patron);
    return {
      categoria,
      etiqueta,
      res: porEspecie(grupo, "RES"),
      cerdo: porEspecie(grupo, "CERDO"),
      total: sumaVenta(grupo),
      indice,
    };
  }).sort((a, b) => Number(b.total) - Number(a.total) || a.indice - b.indice);

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
          {categorias.map(({ categoria, etiqueta, res, cerdo, total }) => {
            const abierta = expandida === categoria;
            const idDetalle = `detalle-categoria-${categoria}`;
            return (
              <Fragment key={categoria}>
                <tr>
                  <th scope="row">
                    <button
                      type="button"
                      className="matriz-categorias__toggle"
                      aria-expanded={abierta}
                      aria-controls={idDetalle}
                      onClick={() => setExpandida(abierta ? null : categoria)}
                    >
                      <span aria-hidden="true">{abierta ? "▾" : "▸"}</span>
                      {etiqueta}
                    </button>
                  </th>
                  <td className="numero">{res ? dinero(res.venta_valor) : "—"}</td>
                  <td className="numero">{cerdo ? dinero(cerdo.venta_valor) : "—"}</td>
                  <td className="numero">{dinero(total)}</td>
                </tr>
                {abierta ? (
                  <tr id={idDetalle} className="matriz-categorias__detalle">
                    <td colSpan={4}>
                      <DetalleCategoria filtros={filtros} categoria={categoria} />
                    </td>
                  </tr>
                ) : null}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function DetalleCategoria({
  filtros,
  categoria,
}: {
  filtros: FiltrosAgro;
  categoria: CategoriaVentaComercialAgro;
}) {
  const detalle = useDetalleVentasComercialesAgro(filtros, categoria);

  if (detalle.isLoading) return <Cargando texto="Cargando productos de la categoría…" />;
  if (detalle.error) return <AvisoError error={detalle.error} />;
  if (!detalle.data?.filas.length) {
    return <Vacio titulo="No hay productos para esta categoría en el período." />;
  }

  return (
    <div className="tabla-envoltorio matriz-categorias__detalle-tabla">
      <table className="tabla tabla--compacta">
        <thead>
          <tr>
            <th>Producto / corte</th>
            <th>Especie</th>
            <th className="numero">Venta subtotal</th>
            <th className="numero">Kilos</th>
          </tr>
        </thead>
        <tbody>
          {detalle.data.filas.map((fila) => (
            <tr key={`${fila.producto}-${fila.especie}`}>
              <th scope="row">{fila.producto}</th>
              <td>{fila.especie}</td>
              <td className="numero">{dinero(fila.venta_valor)}</td>
              <td className="numero">{kilos(fila.kilos)}</td>
            </tr>
          ))}
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
    <div className="rejilla reportes-tat__indicadores">
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
