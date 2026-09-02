/** Costos y margen de Carnes Santacruz, calculados sobre la venta cargada. */

import { useCostos } from "@/api/consultas";
import type { FilaCostos } from "@/api/tipos";
import { AvisoError, Cargando, Tarjeta, Vacio } from "@/componentes/comunes";
import { BarraFiltros, useFiltros } from "@/componentes/filtros";
import { Indicador, PieCalculo } from "@/componentes/indicadores";
import { dinero, numero, porcentaje } from "@/utilidades/formato";

export function Costos() {
  const control = useFiltros();
  const { filtros } = control;
  const { data, isLoading, error } = useCostos(filtros);

  return (
    <div className="pila">
      <BarraFiltros control={control} mostrar={{ categoria: true, medida: false }} />
      <AvisoError error={error} />
      {isLoading ? <Cargando texto="Calculando costos y margen…" /> : null}
      {data ? (
        <>
          <Tarjeta
            titulo="Costos y margen"
            descripcion={`Venta y costo acumulados al ${data.fecha_corte}. El margen solo se publica con costo completo.`}
            pie={<PieCalculo parametros={data.parametros_calculo} medida="valor" />}
          >
            <div className="rejilla rejilla--indicadores">
              <Indicador etiqueta="Venta acumulada" valor={dinero(data.consolidado.venta)} />
              <Indicador etiqueta="Costo acumulado" valor={dinero(data.consolidado.costo)} />
              <Indicador etiqueta="Margen" valor={porcentaje(data.consolidado.margen_porcentaje)} nota={dinero(data.consolidado.margen_valor)} />
              <Indicador etiqueta="Cobertura de costo" valor={porcentaje(data.consolidado.cobertura_costo)} nota={`${numero(data.consolidado.lineas_con_costo)} de ${numero(data.consolidado.lineas)} líneas con costo`} />
            </div>
          </Tarjeta>
          <TablaCostos titulo="Costo por grupo" etiqueta="Grupo" filas={data.grupos} />
          <TablaCostos titulo="Costo por punto de venta" etiqueta="Punto de venta" filas={data.puntos_venta} />
          <TablaCostos titulo="Costo por categoría" etiqueta="Categoría" filas={data.categorias} />
        </>
      ) : null}
    </div>
  );
}

function TablaCostos({ titulo, etiqueta, filas }: { titulo: string; etiqueta: string; filas: (FilaCostos & { nombre: string })[] }) {
  return (
    <Tarjeta titulo={titulo} sinRelleno>
      {filas.length === 0 ? <Vacio titulo="Sin costo en el corte" detalle="Ninguna línea coincide con los filtros seleccionados." /> : (
        <div className="tabla-envoltorio"><table className="tabla"><thead><tr><th scope="col">{etiqueta}</th><th scope="col" className="numero">Venta</th><th scope="col" className="numero">Costo</th><th scope="col" className="numero">Margen</th><th scope="col" className="numero">Margen %</th><th scope="col" className="numero">Cobertura</th><th scope="col" className="numero">Líneas</th></tr></thead><tbody>{filas.map((fila) => <tr key={fila.nombre}><th scope="row">{fila.nombre}</th><td className="numero">{dinero(fila.venta)}</td><td className="numero">{dinero(fila.costo)}</td><td className="numero">{dinero(fila.margen_valor)}</td><td className="numero">{porcentaje(fila.margen_porcentaje)}</td><td className="numero">{porcentaje(fila.cobertura_costo)}</td><td className="numero">{numero(fila.lineas_con_costo)} / {numero(fila.lineas)}</td></tr>)}</tbody></table></div>
      )}
    </Tarjeta>
  );
}