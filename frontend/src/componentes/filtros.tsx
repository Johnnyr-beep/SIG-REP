/**
 * Filtros comunes a todas las pantallas: período, corte, agrupación y medida.
 *
 * El estado vive en la barra de direcciones, no en un `useState`. Así el gerente
 * puede pegar el enlace de «cumplimiento del grupo 3 en kilos al 9 de agosto» en
 * un correo y quien lo abra ve exactamente lo mismo; recargar la página tampoco
 * pierde la selección.
 */

import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router-dom";

import type { FiltrosReporte } from "@/api/consultas";
import { useCategorias, useGrupos, usePuntosVenta } from "@/api/consultas";
import type { Medida } from "@/api/tipos";
import { MEDIDAS, esMedida } from "@/utilidades/dominio";
import { periodoActual } from "@/utilidades/formato";

export interface ControlFiltros {
  filtros: FiltrosReporte;
  fijar: (clave: keyof FiltrosReporte, valor: string) => void;
}

export function useFiltros(): ControlFiltros {
  const [parametros, setParametros] = useSearchParams();

  const filtros = useMemo<FiltrosReporte>(() => {
    const medida = parametros.get("medida");
    return {
      periodo: parametros.get("periodo") ?? periodoActual(),
      hasta: parametros.get("hasta") ?? undefined,
      grupo: parametros.get("grupo") ?? undefined,
      punto_venta: parametros.get("punto_venta") ?? undefined,
      categoria: parametros.get("categoria") ?? undefined,
      medida: esMedida(medida) ? medida : "valor",
    };
  }, [parametros]);

  const fijar = useCallback(
    (clave: keyof FiltrosReporte, valor: string) => {
      setParametros(
        (anteriores) => {
          const siguientes = new URLSearchParams(anteriores);
          if (valor === "") siguientes.delete(clave);
          else siguientes.set(clave, valor);
          // Filtrar por un punto de venta concreto y a la vez por su grupo es
          // redundante y produce lecturas confusas si no coinciden.
          if (clave === "punto_venta" && valor !== "") siguientes.delete("grupo");
          if (clave === "grupo" && valor !== "") siguientes.delete("punto_venta");
          return siguientes;
        },
        { replace: true },
      );
    },
    [setParametros],
  );

  return { filtros, fijar };
}

// ── Conmutador de medida ─────────────────────────────────────────────────────

/**
 * Pesos o kilos.
 *
 * Es un grupo de radios de verdad, no dos botones: el lector de pantalla anuncia
 * «1 de 2» y las flechas del teclado recorren las opciones. §4.5 explica por qué
 * el conmutador es prominente: un mes puede cumplir en pesos por precio y fallar
 * en kilos por volumen, y esa diferencia es justo lo que la gerencia busca.
 */
export function ConmutadorMedida({
  medida,
  onCambiar,
}: {
  medida: Medida;
  onCambiar: (medida: Medida) => void;
}) {
  return (
    <fieldset className="segmentado">
      <legend className="solo-lectores">Medida del reporte</legend>
      {MEDIDAS.map((opcion) => (
        <label
          key={opcion.valor}
          className={`segmentado__opcion${medida === opcion.valor ? " segmentado__opcion--activa" : ""}`}
          title={opcion.ayuda}
        >
          <input
            type="radio"
            name="medida"
            value={opcion.valor}
            checked={medida === opcion.valor}
            onChange={() => onCambiar(opcion.valor)}
          />
          {opcion.etiqueta}
        </label>
      ))}
    </fieldset>
  );
}

// ── Barra de filtros ─────────────────────────────────────────────────────────

export function BarraFiltros({
  control,
  mostrar,
  acciones,
}: {
  control: ControlFiltros;
  /** Qué controles tienen sentido en esta pantalla. */
  mostrar?: {
    corte?: boolean;
    grupo?: boolean;
    puntoVenta?: boolean;
    categoria?: boolean;
    medida?: boolean;
  };
  acciones?: React.ReactNode;
}) {
  const { filtros, fijar } = control;
  const visible = {
    corte: true,
    grupo: true,
    puntoVenta: true,
    categoria: false,
    medida: true,
    ...mostrar,
  };

  const { data: grupos } = useGrupos();
  const { data: puntos } = usePuntosVenta();
  const { data: categorias } = useCategorias();

  return (
    <section className="filtros" aria-label="Filtros del reporte">
      <label className="filtros__campo">
        <span>Período</span>
        <input
          className="campo__control"
          type="month"
          value={filtros.periodo}
          onChange={(evento) => fijar("periodo", evento.target.value)}
          required
        />
      </label>

      {visible.corte ? (
        <label className="filtros__campo">
          <span>Corte</span>
          <input
            className="campo__control"
            type="date"
            value={filtros.hasta ?? ""}
            onChange={(evento) => fijar("hasta", evento.target.value)}
            // Sin valor, el contrato toma «hoy»; el marcador lo dice explícito.
            title="Fecha hasta la que se acumula la venta. Vacío = hoy."
          />
        </label>
      ) : null}

      {visible.grupo ? (
        <label className="filtros__campo">
          <span>Grupo</span>
          <select
            className="campo__control"
            value={filtros.grupo ?? ""}
            onChange={(evento) => fijar("grupo", evento.target.value)}
          >
            <option value="">Todos</option>
            {(grupos ?? []).map((grupo) => (
              <option key={grupo.codigo} value={grupo.codigo}>
                {grupo.nombre}
              </option>
            ))}
          </select>
        </label>
      ) : null}

      {visible.puntoVenta ? (
        <label className="filtros__campo">
          <span>Punto de venta</span>
          <select
            className="campo__control"
            value={filtros.punto_venta ?? ""}
            onChange={(evento) => fijar("punto_venta", evento.target.value)}
          >
            <option value="">Todos</option>
            {(puntos ?? []).map((punto) => (
              <option key={punto.codigo_co} value={punto.codigo_co}>
                {punto.codigo_co} · {punto.nombre}
                {punto.presupuestado ? "" : " (sin presupuesto)"}
              </option>
            ))}
          </select>
        </label>
      ) : null}

      {visible.categoria ? (
        <label className="filtros__campo">
          <span>Categoría</span>
          <select
            className="campo__control"
            value={filtros.categoria ?? ""}
            onChange={(evento) => fijar("categoria", evento.target.value)}
          >
            <option value="">Todas</option>
            {(categorias ?? []).map((categoria) => (
              <option key={categoria.codigo} value={categoria.codigo}>
                {categoria.nombre}
              </option>
            ))}
          </select>
        </label>
      ) : null}

      {visible.medida ? (
        <div className="filtros__campo">
          <span>Medida</span>
          <ConmutadorMedida
            medida={filtros.medida}
            onCambiar={(medida) => fijar("medida", medida)}
          />
        </div>
      ) : null}

      {acciones ? <div className="filtros__acciones">{acciones}</div> : null}
    </section>
  );
}
