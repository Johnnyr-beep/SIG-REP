/**
 * Resumen financiero consolidado — instancia Grupo Santacruz.
 *
 * Balance general, estado de resultados e indicadores del libro mayor que
 * carga `python -m app.infrastructure.cargar_libro_mayor`. Una sola pantalla,
 * a propósito: es el primer corte del módulo y responde la pregunta que pide
 * el negocio —¿cómo va la compañía este mes, según el libro mayor?— antes de
 * abrir el detalle por cuenta o por tercero.
 */

import { useState } from "react";

import {
  useBalanceGeneral,
  useEstadoResultados,
  useIndicadoresFinancieros,
} from "@/api/consultasFinanciero";
import { AvisoError, Cargando, Tarjeta } from "@/componentes/comunes";
import { Indicador } from "@/componentes/indicadores";
import { dinero, numero, porcentaje } from "@/utilidades/formato";

/** `"2026-07"` del `<input type="month">` a `"202607"` que pide la API. */
function aPeriodoApi(mes: string): string {
  return mes.replace("-", "");
}

function periodoActual(): string {
  const hoy = new Date();
  return `${hoy.getFullYear()}-${String(hoy.getMonth() + 1).padStart(2, "0")}`;
}

export function ResumenFinanciero() {
  const [mes, setMes] = useState(periodoActual());
  const periodo = aPeriodoApi(mes);
  const filtros = { periodo };

  const balance = useBalanceGeneral(filtros);
  const resultados = useEstadoResultados(filtros);
  const indicadores = useIndicadoresFinancieros(filtros);

  const cargando = balance.isLoading || resultados.isLoading || indicadores.isLoading;
  const error = balance.error ?? resultados.error ?? indicadores.error;

  return (
    <div className="pila">
      <Tarjeta
        titulo="Resumen financiero"
        descripcion="Balance general y estado de resultados del libro mayor, por período contable."
        acciones={
          <form
            className="formulario formulario--linea"
            onSubmit={(evento) => evento.preventDefault()}
          >
            <label className="campo">
              <span>Período</span>
              <input
                className="campo__control"
                type="month"
                value={mes}
                onChange={(evento) => setMes(evento.target.value)}
                required
              />
            </label>
          </form>
        }
      >
        <AvisoError error={error} />
        {cargando ? <Cargando texto="Cargando el resumen financiero…" /> : null}

        {!cargando && balance.data ? (
          <>
            <h3>Balance general</h3>
            <div className="rejilla rejilla--indicadores">
              <Indicador etiqueta="Activo" valor={dinero(balance.data.activo)} />
              <Indicador etiqueta="Pasivo" valor={dinero(balance.data.pasivo)} />
              <Indicador etiqueta="Patrimonio" valor={dinero(balance.data.patrimonio)} />
              <Indicador
                etiqueta="Descuadre"
                valor={dinero(balance.data.descuadre)}
                nota="Activo − pasivo − patrimonio. Debe ser cero; si no lo es, el descuadre viene del origen."
                tono={balance.data.descuadre === "0.00" ? undefined : "aviso"}
              />
            </div>
          </>
        ) : null}

        {!cargando && resultados.data ? (
          <>
            <h3>Estado de resultados</h3>
            <div className="rejilla rejilla--indicadores">
              <Indicador etiqueta="Ingresos" valor={dinero(resultados.data.ingresos)} />
              <Indicador etiqueta="Costos" valor={dinero(resultados.data.costos)} />
              <Indicador etiqueta="Gastos" valor={dinero(resultados.data.gastos)} />
              <Indicador
                etiqueta="Utilidad neta"
                valor={dinero(resultados.data.utilidad_neta)}
                tono={resultados.data.utilidad_neta.trim().startsWith("-") ? "peligro" : "exito"}
              />
            </div>
          </>
        ) : null}

        {!cargando && indicadores.data ? (
          <>
            <h3>Indicadores</h3>
            <div className="rejilla rejilla--indicadores">
              <Indicador
                etiqueta="Liquidez corriente"
                valor={numero(indicadores.data.liquidez_corriente, 2)}
                nota="Activo corriente / pasivo corriente"
              />
              <Indicador
                etiqueta="Endeudamiento"
                valor={porcentaje(indicadores.data.endeudamiento)}
                nota="Pasivo / activo"
              />
              <Indicador
                etiqueta="Margen neto"
                valor={porcentaje(indicadores.data.margen_neto)}
                nota="Utilidad neta / ingresos"
              />
            </div>
          </>
        ) : null}
      </Tarjeta>
    </div>
  );
}
