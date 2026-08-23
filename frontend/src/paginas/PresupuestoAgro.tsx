/**
 * Parametrización del presupuesto de agropecuaria.
 *
 * Esta pantalla existe alrededor de una sola regla, y toda su forma sale de
 * ella: **el presupuesto no tiene un total global**. El negocio fija la meta en
 * cuatro descomposiciones —vendedor, centro de operación, especie y tipo
 * comercial— que son cuatro repartos del *mismo* dinero. Sumarlas daría cuatro
 * veces la meta.
 *
 * Por eso la pantalla trabaja **una dimensión a la vez** y no ofrece en ningún
 * sitio una cifra que las agregue. La comprobación que sí tiene sentido es la
 * contraria: si los cuatro repartos describen el mismo dinero, sus totales deben
 * coincidir, y cuando no coinciden hay un error de captura. Eso es lo que
 * publica el cuadre, arriba del todo y sin poderse pasar por alto.
 *
 * El sistema **no reparte la diferencia**. Hacerlo sería inventarse la meta de
 * alguien; quien la capturó es quien la arregla.
 */

import { useState } from "react";
import { useSearchParams } from "react-router-dom";

import {
  useCargaMasivaAgro,
  useDimensionesAgro,
  useCuadreAgro,
  useGuardarPresupuestoAgro,
  useHistorialAgro,
  usePresupuestoAgro,
} from "@/api/consultasAgro";
import type { MetaAgro, MiembroDimensionAgro } from "@/api/tiposAgro";
import {
  AvisoError,
  Cargando,
  Campo,
  Tarjeta,
  Vacio,
} from "@/componentes/comunes";
import { AvisoCuadre } from "@/componentes/indicadoresAgro";
import {
  DIMENSIONES_PRESUPUESTO,
  esDimensionPresupuesto,
  etiquetaDimension,
} from "@/utilidades/dominioAgro";
import {
  dinero,
  fechaHora,
  kilos,
  periodoActual,
  periodoLargo,
} from "@/utilidades/formato";

/** La marca de «todavía no hay miembro elegido»: obliga a escoger uno. */
const NUEVA: MetaAgro = {
  dimension: "",
  clave: "",
  nombre: "",
  monto: "0",
  kilos: "0",
};

export function PresupuestoAgro() {
  const [parametros, setParametros] = useSearchParams();
  const periodo = parametros.get("periodo") ?? periodoActual();
  const crudo = parametros.get("dimension");
  const dimension = esDimensionPresupuesto(crudo) ? crudo : "centro_operacion";

  const { data, isLoading, error } = usePresupuestoAgro(periodo, dimension);
  const { data: cuadre } = useCuadreAgro(periodo);
  const { data: historial } = useHistorialAgro(periodo, dimension);
  const guardar = useGuardarPresupuestoAgro();
  const carga = useCargaMasivaAgro(periodo);

  const [edicion, setEdicion] = useState<MetaAgro | null>(null);

  function fijar(clave: string, valor: string) {
    const siguientes = new URLSearchParams(parametros);
    siguientes.set(clave, valor);
    setParametros(siguientes, { replace: true });
  }

  // La respuesta trae una entrada por dimensión; con el filtro puesto, una sola.
  const bloque = data?.[0] ?? null;
  const filas = bloque?.filas ?? [];

  return (
    <div className="pila">
      <section className="filtros" aria-label="Período y dimensión">
        <label className="filtros__campo">
          <span>Período</span>
          <input
            className="campo__control"
            type="month"
            value={periodo}
            onChange={(evento) => fijar("periodo", evento.target.value)}
            required
          />
        </label>
        <label className="filtros__campo">
          <span>Dimensión</span>
          <select
            className="campo__control"
            value={dimension}
            onChange={(evento) => fijar("dimension", evento.target.value)}
          >
            {DIMENSIONES_PRESUPUESTO.map((opcion) => (
              <option key={opcion.valor} value={opcion.valor}>
                {opcion.etiqueta}
              </option>
            ))}
          </select>
        </label>
        <div className="filtros__acciones">
          <button
            type="button"
            className="boton boton--pequeno"
            onClick={() => setEdicion(NUEVA)}
          >
            Fijar una meta
          </button>
          <CargaMasiva carga={carga} />
        </div>
      </section>

      <AvisoError error={error} />
      <AvisoError error={guardar.error} />

      {/* El cuadre va arriba y visible aunque cuadre: es la única señal de que
          las otras tres dimensiones existen y de que esta no vive sola. */}
      <AvisoCuadre cuadre={cuadre} discretoSiCuadra={false} />

      {isLoading ? <Cargando texto="Cargando el presupuesto…" /> : null}

      {bloque ? (
        <Tarjeta
          titulo={`Presupuesto por ${etiquetaDimension(dimension).toLowerCase()}`}
          descripcion={
            <>
              Total de esta descomposición para {periodoLargo(periodo)}:{" "}
              <strong>{dinero(bloque.total_monto)}</strong> ·{" "}
              {kilos(bloque.total_kilos)}.{" "}
              <em>
                Es el presupuesto de la compañía repartido por esta dimensión,
                no el de un trozo: no se suma con el de las otras tres.
              </em>
            </>
          }
          sinRelleno
        >
          {!bloque.definido ? (
            <Vacio
              titulo="Esta dimensión no tiene presupuesto capturado"
              detalle="No es lo mismo que un presupuesto de cero: aquel sería una afirmación del negocio y esto es la ausencia de la parametrización. Mientras siga así, los reportes por esta dimensión no traen cumplimiento."
            />
          ) : (
            <div className="tabla-envoltorio">
              <table className="tabla">
                <thead>
                  <tr>
                    <th scope="col">Clave</th>
                    <th scope="col">Nombre</th>
                    <th scope="col">Meta ($)</th>
                    <th scope="col">Meta (kg)</th>
                    <th scope="col">
                      <span className="solo-lectores">Acciones</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {filas.map((fila) => (
                    <tr key={fila.clave}>
                      <td className="mono">{fila.clave}</td>
                      <td>{fila.nombre}</td>
                      <td className="numero">{dinero(fila.monto)}</td>
                      <td className="numero">{kilos(fila.kilos)}</td>
                      <td>
                        <button
                          type="button"
                          className="boton boton--sutil boton--pequeno"
                          onClick={() => setEdicion(fila)}
                        >
                          Cambiar
                        </button>
                      </td>
                    </tr>
                  ))}
                  <tr className="fila-total">
                    <th scope="row" colSpan={2}>
                      TOTAL · {filas.length} miembro
                      {filas.length === 1 ? "" : "s"}
                    </th>
                    <td className="numero">{dinero(bloque.total_monto)}</td>
                    <td className="numero">{kilos(bloque.total_kilos)}</td>
                    <td />
                  </tr>
                </tbody>
              </table>
            </div>
          )}
        </Tarjeta>
      ) : null}

      {edicion ? (
        <FormularioMeta
          meta={edicion}
          periodo={periodo}
          dimension={dimension}
          guardar={guardar}
          onCerrar={() => setEdicion(null)}
        />
      ) : null}

      {historial && historial.length > 0 ? (
        <Tarjeta
          titulo="Historial de cambios"
          descripcion="Todo cambio de presupuesto queda con autor, fecha y motivo (§7)."
          sinRelleno
        >
          <div className="tabla-envoltorio">
            <table className="tabla tabla--compacta">
              <thead>
                <tr>
                  <th scope="col">Cuándo</th>
                  <th scope="col">Quién</th>
                  <th scope="col">Clave</th>
                  <th scope="col">Campo</th>
                  <th scope="col">Antes</th>
                  <th scope="col">Después</th>
                  <th scope="col">Motivo</th>
                </tr>
              </thead>
              <tbody>
                {historial.map((linea, indice) => (
                  <tr key={`${linea.cuando}-${indice}`}>
                    <td>{fechaHora(linea.cuando)}</td>
                    <td>{linea.quien ?? "—"}</td>
                    <td className="mono">{linea.clave}</td>
                    <td>{linea.campo}</td>
                    <td className="numero tenue">
                      {dinero(linea.valor_anterior)}
                    </td>
                    <td className="numero">{dinero(linea.valor_nuevo)}</td>
                    <td>{linea.motivo}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Tarjeta>
      ) : null}
    </div>
  );
}

function FormularioMeta({
  meta,
  periodo,
  dimension,
  guardar,
  onCerrar,
}: {
  meta: MetaAgro;
  periodo: string;
  dimension: "vendedor" | "centro_operacion" | "especie" | "tipo_comercial";
  guardar: ReturnType<typeof useGuardarPresupuestoAgro>;
  onCerrar: () => void;
}) {
  const esNueva = meta.clave === "";
  const [clave, setClave] = useState(meta.clave);
  const [monto, setMonto] = useState(meta.monto);
  const [kilosMeta, setKilos] = useState(meta.kilos);
  const [motivo, setMotivo] = useState("");

  // El catálogo de la dimensión, para elegir a quién. La clave es la del origen
  // —la cédula del vendedor, el `CO_Id` del centro—, así que no se teclea: se
  // escoge. Escribirla a mano es como se acaba con una meta colgada de una
  // clave que ninguna venta usa.
  const { data: miembros } = useDimensionesAgro(dimension);

  function enviar(evento: React.FormEvent) {
    evento.preventDefault();
    guardar.mutate(
      { periodo, dimension, clave, monto, kilos: kilosMeta, motivo },
      { onSuccess: onCerrar },
    );
  }

  return (
    <Tarjeta
      titulo={esNueva ? "Fijar una meta" : `Meta de ${meta.nombre}`}
      descripcion={`Período ${periodoLargo(periodo)}.`}
    >
      <form className="formulario" onSubmit={enviar}>
        {esNueva ? (
          <Campo
            etiqueta="¿A quién?"
            ayuda={
              miembros && miembros.length === 0
                ? "Este catálogo está vacío: los miembros aparecen con la primera ingesta."
                : "Sale del catálogo que dejó la ingesta, no se escribe a mano."
            }
          >
            <select
              className="campo__control"
              value={clave}
              onChange={(evento) => setClave(evento.target.value)}
              required
            >
              <option value="">Elija uno…</option>
              {(miembros ?? []).map((m: MiembroDimensionAgro) => (
                <option key={m.clave} value={m.clave}>
                  {m.nombre} · {m.clave}
                </option>
              ))}
            </select>
          </Campo>
        ) : null}
        <Campo etiqueta="Meta en pesos">
          <input
            className="campo__control"
            type="number"
            min="0"
            step="0.01"
            value={monto}
            onChange={(evento) => setMonto(evento.target.value)}
            required
          />
        </Campo>
        <Campo etiqueta="Meta en kilos">
          <input
            className="campo__control"
            type="number"
            min="0"
            step="0.001"
            value={kilosMeta}
            onChange={(evento) => setKilos(evento.target.value)}
            required
          />
        </Campo>
        {/* El motivo lo exige el contrato con cinco caracteres mínimo, y no por
            capricho: «ajuste» no sirve para evaluar a nadie seis meses después. */}
        <Campo
          etiqueta="Motivo del cambio"
          ayuda="Queda en el historial con su autor y su fecha. Escriba por qué cambia, no qué cambia."
        >
          <input
            className="campo__control"
            type="text"
            minLength={5}
            maxLength={400}
            value={motivo}
            onChange={(evento) => setMotivo(evento.target.value)}
            required
          />
        </Campo>
        <div className="formulario__acciones">
          <button
            type="button"
            className="boton boton--sutil"
            onClick={onCerrar}
          >
            Cancelar
          </button>
          <button type="submit" className="boton" disabled={guardar.isPending}>
            {guardar.isPending ? "Guardando…" : "Guardar"}
          </button>
        </div>
      </form>
    </Tarjeta>
  );
}

function CargaMasiva({
  carga,
}: {
  carga: ReturnType<typeof useCargaMasivaAgro>;
}) {
  const resultado = carga.data;

  return (
    <>
      <label className="boton boton--pequeno">
        {carga.isPending ? "Cargando…" : "Cargar archivo"}
        <input
          type="file"
          accept=".xlsx,.xlsm,.csv"
          hidden
          onChange={(evento) => {
            const archivo = evento.target.files?.[0];
            if (archivo) {
              carga.mutate({
                archivo,
                motivo: `Carga masiva de ${archivo.name}`,
              });
              evento.target.value = "";
            }
          }}
        />
      </label>
      {resultado ? (
        <span className="tenue">
          {resultado.aceptadas} aceptada{resultado.aceptadas === 1 ? "" : "s"}
          {resultado.rechazadas > 0
            ? ` · ${resultado.rechazadas} rechazada(s)`
            : ""}
        </span>
      ) : null}
    </>
  );
}
