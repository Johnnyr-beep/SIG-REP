/**
 * Parametrización del presupuesto de agropecuaria.
 *
 * Esta pantalla tiene dos vistas, cada una alrededor de una regla distinta:
 *
 * **Metas por dimensión** — el presupuesto no tiene un total global. El negocio
 * fija la meta en cuatro descomposiciones —vendedor, centro de operación,
 * especie y tipo comercial— que son cuatro repartos del *mismo* dinero.
 * Sumarlas daría cuatro veces la meta. La pantalla trabaja una dimensión a la
 * vez y no ofrece ninguna cifra que las agregue. El cuadre publica si los
 * cuatro repartos coinciden; el sistema no reparte la diferencia.
 *
 * **Presupuesto mensual** — cuatro bloques independientes —comercial, agro
 * distribución, servicio y nacional— que **sí se suman** para dar el total
 * mensual. Cada bloque es una meta distinta. Es lo opuesto al presupuesto por
 * dimensiones, y por eso vive en rutas y tablas aparte
 * (`/agro/presupuesto-mensual`).
 */

import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import {
  useCanalesMapeosMensual,
  useCargaMasivaAgro,
  useDimensionesAgro,
  useEliminarPresupuestoAgro,
  useCuadreAgro,
  useGuardarCanalMapeoMensual,
  useGuardarDetalleMensual,
  useGuardarMapeoMensual,
  useGuardarPresupuestoAgro,
  useGuardarServicioMensual,
  useHistorialAgro,
  useImportarComercial,
  useMapeosMensual,
  usePresupuestoAgro,
  usePresupuestoMensual,
  useServicioMensual,
} from "@/api/consultasAgro";
import type {
  BloqueDetalleMensual,
  BloqueMensual,
  CanalMapeoMensual,
  DetalleMensual,
  EntradaCanalMapeoMensual,
  EntradaDetalleMensual,
  EntradaMapeoMensual,
  EntradaServicioMensual,
  MapeoMensual,
  MetaAgro,
  MiembroDimensionAgro,
  ResultadoImportacionComercial,
} from "@/api/tiposAgro";
import {
  AvisoError,
  Cargando,
  Campo,
  Confirmacion,
  Dialogo,
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

// ── Presupuesto mensual: vocabulario de bloques ──────────────────────────────

/**
 * Los cuatro bloques en el orden en que los lee el negocio.
 *
 * Las etiquetas coinciden con las del backend (`_ETIQUETAS_BLOQUE` en
 * `agro_presupuesto_mensual_service.py`), que es la fuente de verdad.
 */
const BLOQUES_MENSUAL: readonly {
  valor: BloqueMensual;
  etiqueta: string;
  /** Si el bloque se captura como filas de detalle o como un solo valor. */
  esDetalle: boolean;
  /** El vendedor fijo del bloque, si lo tiene; `null` si es libre. */
  vendedorFijo: string | null;
}[] = [
  { valor: "commercial", etiqueta: "Comercial", esDetalle: true, vendedorFijo: null },
  { valor: "agro_distribucion", etiqueta: "Agropecuaria Distribución", esDetalle: true, vendedorFijo: "AGROPECUARIA" },
  { valor: "servicio", etiqueta: "Servicio", esDetalle: false, vendedorFijo: null },
  { valor: "nacional", etiqueta: "Nacional", esDetalle: true, vendedorFijo: "JUAN SIERRA" },
];

const CATEGORIAS_MENSUAL: readonly string[] = ["A", "B", "C", "D", "E", "F"];

function etiquetaBloque(bloque: string): string {
  return BLOQUES_MENSUAL.find((b) => b.valor === bloque)?.etiqueta ?? bloque;
}

// ── Componente principal: pestañas ───────────────────────────────────────────

export function PresupuestoAgro() {
  const [parametros, setParametros] = useSearchParams();
  const vista = parametros.get("vista") === "mensual" ? "mensual" : "dimensiones";

  function fijar(clave: string, valor: string) {
    const siguientes = new URLSearchParams(parametros);
    siguientes.set(clave, valor);
    setParametros(siguientes, { replace: true });
  }

  return (
    <div className="pila">
      <nav className="pestanas" aria-label="Vistas del presupuesto">
        <button
          type="button"
          className={`pestana${vista === "dimensiones" ? " pestana--activa" : ""}`}
          onClick={() => fijar("vista", "dimensiones")}
        >
          Metas por dimensión
        </button>
        <button
          type="button"
          className={`pestana${vista === "mensual" ? " pestana--activa" : ""}`}
          onClick={() => fijar("vista", "mensual")}
        >
          Presupuesto mensual
        </button>
      </nav>

      {vista === "dimensiones" ? <VistaDimensiones /> : <VistaMensual />}
    </div>
  );
}

// ── Vista: Metas por dimensión ───────────────────────────────────────────────

function VistaDimensiones() {
  const [parametros, setParametros] = useSearchParams();
  const periodo = parametros.get("periodo") ?? periodoActual();
  const crudo = parametros.get("dimension");
  const dimension = esDimensionPresupuesto(crudo) ? crudo : "centro_operacion";

  const { data, isLoading, error } = usePresupuestoAgro(periodo, dimension);
  const { data: cuadre } = useCuadreAgro(periodo);
  const { data: historial } = useHistorialAgro(periodo, dimension);
  const guardar = useGuardarPresupuestoAgro();
  const eliminar = useEliminarPresupuestoAgro();
  const carga = useCargaMasivaAgro(periodo);

  const [edicion, setEdicion] = useState<MetaAgro | null>(null);
  const [eliminacion, setEliminacion] = useState<MetaAgro | null>(null);

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
      <AvisoError error={eliminar.error} />

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
                        <button
                          type="button"
                          className="boton boton--sutil boton--pequeno"
                          onClick={() => setEliminacion(fila)}
                        >
                          Eliminar
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
      <Confirmacion
        abierto={eliminacion !== null}
        titulo="Eliminar meta presupuestal"
        mensaje={
          eliminacion
            ? `Se eliminará la meta de ${eliminacion.nombre}. El historial se conserva.`
            : ""
        }
        textoConfirmar="Eliminar meta"
        peligrosa
        trabajando={eliminar.isPending}
        error={eliminar.error}
        onCancelar={() => setEliminacion(null)}
        onConfirmar={() => {
          if (!eliminacion) return;
          eliminar.mutate(
            { periodo, dimension, clave: eliminacion.clave },
            { onSuccess: () => setEliminacion(null) },
          );
        }}
      />

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

// ── Vista: Presupuesto mensual ────────────────────────────────────────────────
//
// Cuatro bloques independientes —comercial, agro distribución, servicio y
// nacional— que **sí se suman** para dar el total mensual. Es lo opuesto al
// presupuesto por dimensiones de arriba, donde las cuatro descomposiciones
// describen el mismo dinero y no se suman.

function VistaMensual() {
  const [parametros, setParametros] = useSearchParams();
  const periodo = parametros.get("periodo") ?? periodoActual();

  const { data, isLoading, error } = usePresupuestoMensual(periodo);

  function fijar(clave: string, valor: string) {
    const siguientes = new URLSearchParams(parametros);
    siguientes.set(clave, valor);
    setParametros(siguientes, { replace: true });
  }

  return (
    <div className="pila">
      <section className="filtros" aria-label="Período">
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
      </section>

      <AvisoError error={error} />

      {isLoading ? <Cargando texto="Cargando el presupuesto mensual…" /> : null}

      {data ? (
        <>
          {/* El total mensual es la suma de los cuatro bloques. Es lo que
              distingue esta vista de la de dimensiones: aquí sumar tiene
              sentido, porque cada bloque es una meta distinta. */}
          <Tarjeta
            titulo={`Total mensual · ${periodoLargo(periodo)}`}
            descripcion={
              <>
                La suma de los cuatro bloques:{" "}
                <strong>{dinero(data.total_monto)}</strong> ·{" "}
                {kilos(data.total_kilos)}. Cada bloque es una meta independiente;
                por eso aquí sí se suman, a diferencia del presupuesto por
                dimensiones.
              </>
            }
          >
            <div className="fila fila--envolvente">
              {data.bloques.map((bloque) => (
                <div
                  key={bloque.bloque}
                  className="tarjeta tarjeta--simple"
                  style={{ flex: "1 1 200px" }}
                >
                  <p className="tenue" style={{ fontWeight: 600 }}>
                    {etiquetaBloque(bloque.bloque)}
                  </p>
                  <p style={{ fontSize: "1.25rem", fontWeight: 700 }}>
                    {dinero(bloque.total_monto)}
                  </p>
                  <p className="tenue">{kilos(bloque.total_kilos)}</p>
                </div>
              ))}
            </div>
          </Tarjeta>

          {/* Cada bloque se captura y se muestra de forma distinta. */}
          {data.bloques.map((bloque) => {
            const definicion = BLOQUES_MENSUAL.find(
              (b) => b.valor === bloque.bloque,
            );
            if (!definicion) return null;

            return definicion.esDetalle ? (
              <BloqueDetalle
                key={bloque.bloque}
                bloque={bloque.bloque as BloqueDetalleMensual}
                etiqueta={definicion.etiqueta}
                vendedorFijo={definicion.vendedorFijo}
                filas={bloque.filas}
                totalMonto={bloque.total_monto}
                totalKilos={bloque.total_kilos}
                periodo={periodo}
              />
            ) : (
              <BloqueServicio
                key={bloque.bloque}
                periodo={periodo}
                etiqueta={definicion.etiqueta}
              />
            );
          })}

          {/* Configuración de asignaciones: qué vendedor atiende a qué
              cliente, en qué bloque y con qué categoría. Es lo que hace que la
              captura sea configurable en lugar de codificada. */}
          <ConfiguracionMapeos />

          {/* ConfiguraciÃ³n de canales del Excel: a quÃ© vendedor, cliente y
              categorÃ­a pertenece cada canal del libro anual. Es lo que usa la
              importaciÃ³n del Excel comercial para volcar cada canal en el
              bloque comercial. */}
          <ConfiguracionCanales />
        </>
      ) : null}
    </div>
  );
}

// ── Bloque de detalle (Comercial, Agro Distribución, Nacional) ───────────────

function BloqueDetalle({
  bloque,
  etiqueta,
  vendedorFijo,
  filas,
  totalMonto,
  totalKilos,
  periodo,
}: {
  bloque: BloqueDetalleMensual;
  etiqueta: string;
  vendedorFijo: string | null;
  filas: DetalleMensual[];
  totalMonto: string;
  totalKilos: string;
  periodo: string;
}) {
  const guardar = useGuardarDetalleMensual(periodo);
  const [edicion, setEdicion] = useState<DetalleMensual | null>(null);
  const [abrirFormulario, setAbrirFormulario] = useState(false);

  // El bloque comercial usa vendedor libre y categoría A–F; los otros dos
  // tienen vendedor fijo y no usan categoría.
  const esComercial = bloque === "commercial";

  return (
    <Tarjeta
      titulo={etiqueta}
      descripcion={
        <>
          Total del bloque para {periodoLargo(periodo)}:{" "}
          <strong>{dinero(totalMonto)}</strong> · {kilos(totalKilos)}.
          {vendedorFijo ? (
            <>
              {" "}
              <em>
                El vendedor es fijo ({vendedorFijo}); las filas se capturan por
                cliente.
              </em>
            </>
          ) : null}
        </>
      }
      acciones={
        <>
          {esComercial ? <ImportarExcelComercial periodo={periodo} /> : null}
          <button
            type="button"
            className="boton boton--pequeno"
            onClick={() => {
              setEdicion(null);
              setAbrirFormulario(true);
            }}
          >
            Agregar fila
          </button>
        </>
      }
      sinRelleno
    >
      <AvisoError error={guardar.error} />

      {filas.length === 0 ? (
        <Vacio
          titulo="Este bloque no tiene filas capturadas"
          detalle="Cada fila es una meta del bloque para el período, descompuesta por cliente y vendedor. Sin filas, el bloque aporta cero al total mensual."
        />
      ) : (
        <div className="tabla-envoltorio">
          <table className="tabla">
            <thead>
              <tr>
                {esComercial ? <th scope="col">Vendedor</th> : null}
                <th scope="col">Cliente</th>
                {esComercial ? <th scope="col">Categoría</th> : null}
                <th scope="col">Ppto Kilos</th>
                <th scope="col">Presupuesto ($)</th>
                <th scope="col">
                  <span className="solo-lectores">Acciones</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {filas.map((fila, indice) => (
                <tr key={fila.id ?? indice}>
                  {esComercial ? (
                    <td>
                      {fila.vendedor_etiqueta ?? fila.vendedor_clave ?? "—"}
                    </td>
                  ) : null}
                  <td>
                    {fila.cliente_etiqueta ?? fila.cliente_clave ?? "—"}
                    {fila.cliente_clave ? (
                      <span className="tenue mono" style={{ marginLeft: 6 }}>
                        {fila.cliente_clave}
                      </span>
                    ) : null}
                  </td>
                  {esComercial ? (
                    <td className="mono">{fila.categoria ?? "—"}</td>
                  ) : null}
                  <td className="numero">{kilos(fila.kilos)}</td>
                  <td className="numero">{dinero(fila.monto)}</td>
                  <td>
                    <button
                      type="button"
                      className="boton boton--sutil boton--pequeno"
                      onClick={() => {
                        setEdicion(fila);
                        setAbrirFormulario(true);
                      }}
                    >
                      Cambiar
                    </button>
                  </td>
                </tr>
              ))}
              <tr className="fila-total">
                <th scope="row" colSpan={esComercial ? 3 : 1}>
                  TOTAL · {filas.length} fila{filas.length === 1 ? "" : "s"}
                </th>
                <td className="numero">{kilos(totalKilos)}</td>
                <td className="numero">{dinero(totalMonto)}</td>
                <td />
              </tr>
            </tbody>
          </table>
        </div>
      )}

      {abrirFormulario ? (
        <FormularioDetalleMensual
          bloque={bloque}
          etiqueta={etiqueta}
          vendedorFijo={vendedorFijo}
          filaExistente={edicion}
          guardar={guardar}
          onCerrar={() => setAbrirFormulario(false)}
        />
      ) : null}
    </Tarjeta>
  );
}

function FormularioDetalleMensual({
  bloque,
  etiqueta,
  vendedorFijo,
  filaExistente,
  guardar,
  onCerrar,
}: {
  bloque: BloqueDetalleMensual;
  etiqueta: string;
  vendedorFijo: string | null;
  filaExistente: DetalleMensual | null;
  guardar: ReturnType<typeof useGuardarDetalleMensual>;
  onCerrar: () => void;
}) {
  const esComercial = bloque === "commercial";
  const esEdicion = filaExistente !== null;

  const [vendedorClave, setVendedorClave] = useState(
    filaExistente?.vendedor_clave ?? "",
  );
  const [clienteClave, setClienteClave] = useState(
    filaExistente?.cliente_clave ?? "",
  );
  const [categoria, setCategoria] = useState(filaExistente?.categoria ?? "");
  const [monto, setMonto] = useState(filaExistente?.monto ?? "0");
  const [kilosValor, setKilos] = useState(filaExistente?.kilos ?? "0");

  // Catálogos de vendedor y cliente, para elegir a quién. La clave es la del
  // origen —la cédula del vendedor, el NIT del cliente—, así que no se teclea:
  // se escoge del catálogo que dejó la ingesta.
  const { data: vendedores } = useDimensionesAgro("vendedor");
  const { data: clientes } = useDimensionesAgro("cliente");

  function enviar(evento: React.FormEvent) {
    evento.preventDefault();

    const vendedorSeleccionado = (vendedores ?? []).find(
      (m) => m.clave === vendedorClave,
    );
    const clienteSeleccionado = (clientes ?? []).find(
      (m) => m.clave === clienteClave,
    );

    const datos: EntradaDetalleMensual = {
      bloque,
      monto,
      kilos: kilosValor,
    };

    // El bloque comercial envía vendedor y categoría; los otros dos no los
    // envían porque el backend los fija (AGROPECUARIA / JUAN SIERRA).
    if (esComercial) {
      datos.vendedor_clave = vendedorClave || null;
      datos.vendedor_etiqueta = vendedorSeleccionado?.nombre ?? null;
      datos.categoria = categoria || null;
    }

    // El cliente es siempre libre: todos los bloques de detalle lo usan.
    datos.cliente_clave = clienteClave || null;
    datos.cliente_etiqueta = clienteSeleccionado?.nombre ?? null;

    guardar.mutate(datos, { onSuccess: onCerrar });
  }

  return (
    <Dialogo
      abierto
      titulo={
        esEdicion
          ? `Cambiar fila de ${etiqueta}`
          : `Agregar fila a ${etiqueta}`
      }
      onCerrar={onCerrar}
      pie={
        <>
          <button
            type="button"
            className="boton boton--sutil"
            onClick={onCerrar}
          >
            Cancelar
          </button>
          <button
            type="submit"
            form="formulario-detalle-mensual"
            className="boton"
            disabled={guardar.isPending}
          >
            {guardar.isPending ? "Guardando…" : "Guardar"}
          </button>
        </>
      }
    >
      <form
        id="formulario-detalle-mensual"
        className="pila--compacta"
        onSubmit={enviar}
      >
        <AvisoError error={guardar.error} />

        {vendedorFijo ? (
          <Campo etiqueta="Vendedor" ayuda={`Fijo para este bloque: ${vendedorFijo}.`}>
            <input
              className="campo__control"
              type="text"
              value={vendedorFijo}
              disabled
            />
          </Campo>
        ) : (
          <Campo
            etiqueta="Vendedor"
            ayuda="Sale del catálogo que dejó la ingesta, no se escribe a mano."
          >
            <select
              className="campo__control"
              value={vendedorClave}
              onChange={(evento) => setVendedorClave(evento.target.value)}
              required
            >
              <option value="">Elija uno…</option>
              {(vendedores ?? []).map((m) => (
                <option key={m.clave} value={m.clave}>
                  {m.nombre} · {m.clave}
                </option>
              ))}
            </select>
          </Campo>
        )}

        <Campo
          etiqueta="Cliente"
          ayuda="Sale del catálogo que dejó la ingesta, no se escribe a mano."
        >
          <select
            className="campo__control"
            value={clienteClave}
            onChange={(evento) => setClienteClave(evento.target.value)}
            required
          >
            <option value="">Elija uno…</option>
            {(clientes ?? []).map((m) => (
              <option key={m.clave} value={m.clave}>
                {m.nombre} · {m.clave}
              </option>
            ))}
          </select>
        </Campo>

        {esComercial ? (
          <Campo
            etiqueta="Categoría"
            ayuda="Categoría A–F asignada al vendedor en función de sus clientes."
          >
            <select
              className="campo__control"
              value={categoria}
              onChange={(evento) => setCategoria(evento.target.value)}
              required
            >
              <option value="">Elija una…</option>
              {CATEGORIAS_MENSUAL.map((cat) => (
                <option key={cat} value={cat}>
                  {cat}
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
            value={kilosValor}
            onChange={(evento) => setKilos(evento.target.value)}
            required
          />
        </Campo>
      </form>
    </Dialogo>
  );
}

// ── Bloque de servicio (un solo valor mensual) ───────────────────────────────

function BloqueServicio({
  periodo,
  etiqueta,
}: {
  periodo: string;
  etiqueta: string;
}) {
  const { data, isLoading, error } = useServicioMensual(periodo);
  const guardar = useGuardarServicioMensual(periodo);
  const [editando, setEditando] = useState(false);
  const [monto, setMonto] = useState("0");
  const [kilosValor, setKilos] = useState("0");

  // Cuando llegan los datos del backend, se cargan en el estado del formulario.
  // Se hace en un efecto derivado y no en el `defaultValue` del input porque el
  // backend puede responder después de que el usuario ya haya abierto el
  // formulario.
  useEffect(() => {
    if (data) {
      setMonto(data.monto);
      setKilos(data.kilos);
    }
  }, [data]);

  function guardarServicio(evento: React.FormEvent) {
    evento.preventDefault();
    const datos: EntradaServicioMensual = { monto, kilos: kilosValor };
    guardar.mutate(datos, { onSuccess: () => setEditando(false) });
  }

  return (
    <Tarjeta
      titulo={etiqueta}
      descripcion={
        <>
          Un solo valor mensual para {periodoLargo(periodo)}:{" "}
          <strong>{dinero(data?.monto)}</strong> · {kilos(data?.kilos)}.{" "}
          <em>
            El bloque de servicio no se descompone por vendedor ni por cliente:
            es una sola meta mensual.
          </em>
        </>
      }
      acciones={
        !editando ? (
          <button
            type="button"
            className="boton boton--pequeno"
            onClick={() => setEditando(true)}
          >
            Cambiar
          </button>
        ) : null
      }
    >
      <AvisoError error={error} />
      <AvisoError error={guardar.error} />

      {isLoading ? <Cargando texto="Cargando…" /> : null}

      {editando ? (
        <form className="pila--compacta" onSubmit={guardarServicio}>
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
              value={kilosValor}
              onChange={(evento) => setKilos(evento.target.value)}
              required
            />
          </Campo>
          <div className="fila">
            <button
              type="button"
              className="boton boton--sutil"
              onClick={() => setEditando(false)}
            >
              Cancelar
            </button>
            <button type="submit" className="boton" disabled={guardar.isPending}>
              {guardar.isPending ? "Guardando…" : "Guardar"}
            </button>
          </div>
        </form>
      ) : (
        <div className="fila">
          <div>
            <p className="tenue" style={{ fontWeight: 600 }}>
              Meta en pesos
            </p>
            <p style={{ fontSize: "1.25rem", fontWeight: 700 }}>
              {dinero(data?.monto)}
            </p>
          </div>
          <div>
            <p className="tenue" style={{ fontWeight: 600 }}>
              Meta en kilos
            </p>
            <p style={{ fontSize: "1.25rem", fontWeight: 700 }}>
              {kilos(data?.kilos)}
            </p>
          </div>
        </div>
      )}
    </Tarjeta>
  );
}

// ── Configuración de asignaciones (mapeos) ───────────────────────────────────

function ConfiguracionMapeos() {
  const { data: mapeos, isLoading, error } = useMapeosMensual();
  const [abrirFormulario, setAbrirFormulario] = useState(false);
  const [mapeoEditar, setMapeoEditar] = useState<MapeoMensual | null>(null);

  return (
    <Tarjeta
      titulo="Asignaciones de bloques"
      descripcion="Configura qué vendedor atiende a qué cliente, en qué bloque y con qué categoría (A–F). Es lo que hace que la captura sea configurable en lugar de codificada."
      acciones={
        <button
          type="button"
          className="boton boton--pequeno"
          onClick={() => {
            setMapeoEditar(null);
            setAbrirFormulario(true);
          }}
        >
          Nueva asignación
        </button>
      }
      sinRelleno
    >
      <AvisoError error={error} />

      {isLoading ? <Cargando texto="Cargando asignaciones…" /> : null}

      {!isLoading && (mapeos === undefined || mapeos.length === 0) ? (
        <Vacio
          titulo="No hay asignaciones configuradas"
          detalle="Las asignaciones dicen al sistema qué vendedor pertenece a qué bloque y con qué categoría. Sin ellas, la captura del presupuesto mensual no tiene guía."
        />
      ) : null}

      {mapeos && mapeos.length > 0 ? (
        <div className="tabla-envoltorio">
          <table className="tabla tabla--compacta">
            <thead>
              <tr>
                <th scope="col">Bloque</th>
                <th scope="col">Vendedor</th>
                <th scope="col">Cliente</th>
                <th scope="col">Categoría</th>
                <th scope="col">Activa</th>
                <th scope="col">
                  <span className="solo-lectores">Acciones</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {mapeos.map((mapeo) => (
                <tr key={mapeo.id}>
                  <td>{etiquetaBloque(mapeo.bloque)}</td>
                  <td className="mono">{mapeo.vendedor_clave ?? "—"}</td>
                  <td className="mono">{mapeo.cliente_clave ?? "—"}</td>
                  <td className="mono">{mapeo.categoria ?? "—"}</td>
                  <td>{mapeo.activo ? "Sí" : "No"}</td>
                  <td>
                    <button
                      type="button"
                      className="boton boton--sutil boton--pequeno"
                      onClick={() => {
                        setMapeoEditar(mapeo);
                        setAbrirFormulario(true);
                      }}
                    >
                      Cambiar
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {abrirFormulario ? (
        <FormularioMapeoMensual
          mapeoExistente={mapeoEditar}
          onCerrar={() => setAbrirFormulario(false)}
        />
      ) : null}
    </Tarjeta>
  );
}

function FormularioMapeoMensual({
  mapeoExistente,
  onCerrar,
}: {
  mapeoExistente: MapeoMensual | null;
  onCerrar: () => void;
}) {
  const guardar = useGuardarMapeoMensual();
  const esEdicion = mapeoExistente !== null;

  const [bloque, setBloque] = useState<BloqueMensual>(
    mapeoExistente?.bloque ?? "commercial",
  );
  const [vendedorClave, setVendedorClave] = useState(
    mapeoExistente?.vendedor_clave ?? "",
  );
  const [clienteClave, setClienteClave] = useState(
    mapeoExistente?.cliente_clave ?? "",
  );
  const [categoria, setCategoria] = useState(mapeoExistente?.categoria ?? "");
  const [activo, setActivo] = useState(mapeoExistente?.activo ?? true);

  // Catálogos de vendedor y cliente para elegir a quién.
  const { data: vendedores } = useDimensionesAgro("vendedor");
  const { data: clientes } = useDimensionesAgro("cliente");

  // La categoría solo aplica al bloque comercial; el bloque de servicio no
  // lleva vendedor, cliente ni categoría.
  const esComercial = bloque === "commercial";
  const esServicio = bloque === "servicio";

  function enviar(evento: React.FormEvent) {
    evento.preventDefault();

    const datos: EntradaMapeoMensual = {
      bloque,
      activo,
    };

    if (!esServicio) {
      datos.vendedor_clave = vendedorClave || null;
      datos.cliente_clave = clienteClave || null;
    }

    if (esComercial) {
      datos.categoria = categoria || null;
    }

    guardar.mutate(
      { datos, mapeoId: esEdicion ? mapeoExistente!.id : undefined },
      { onSuccess: onCerrar },
    );
  }

  return (
    <Dialogo
      abierto
      titulo={
        esEdicion ? "Cambiar asignación" : "Nueva asignación de bloque"
      }
      onCerrar={onCerrar}
      pie={
        <>
          <button
            type="button"
            className="boton boton--sutil"
            onClick={onCerrar}
          >
            Cancelar
          </button>
          <button
            type="submit"
            form="formulario-mapeo-mensual"
            className="boton"
            disabled={guardar.isPending}
          >
            {guardar.isPending ? "Guardando…" : "Guardar"}
          </button>
        </>
      }
    >
      <form
        id="formulario-mapeo-mensual"
        className="pila--compacta"
        onSubmit={enviar}
      >
        <AvisoError error={guardar.error} />

        <Campo etiqueta="Bloque">
          <select
            className="campo__control"
            value={bloque}
            onChange={(evento) => setBloque(evento.target.value as BloqueMensual)}
            required
            disabled={esEdicion}
          >
            {BLOQUES_MENSUAL.map((b) => (
              <option key={b.valor} value={b.valor}>
                {b.etiqueta}
              </option>
            ))}
          </select>
        </Campo>

        {esServicio ? (
          <p className="tenue">
            El bloque de servicio no admite vendedor, cliente ni categoría: es
            un solo valor mensual.
          </p>
        ) : (
          <>
            <Campo
              etiqueta="Vendedor"
              ayuda="Opcional. Sale del catálogo que dejó la ingesta."
            >
              <select
                className="campo__control"
                value={vendedorClave}
                onChange={(evento) => setVendedorClave(evento.target.value)}
              >
                <option value="">(sin vendedor)</option>
                {(vendedores ?? []).map((m) => (
                  <option key={m.clave} value={m.clave}>
                    {m.nombre} · {m.clave}
                  </option>
                ))}
              </select>
            </Campo>

            <Campo
              etiqueta="Cliente"
              ayuda="Opcional. Sale del catálogo que dejó la ingesta."
            >
              <select
                className="campo__control"
                value={clienteClave}
                onChange={(evento) => setClienteClave(evento.target.value)}
              >
                <option value="">(sin cliente)</option>
                {(clientes ?? []).map((m) => (
                  <option key={m.clave} value={m.clave}>
                    {m.nombre} · {m.clave}
                  </option>
                ))}
              </select>
            </Campo>

            {esComercial ? (
              <Campo
                etiqueta="Categoría"
                ayuda="Obligatoria para el bloque comercial. Categoría A–F asignada al vendedor."
              >
                <select
                  className="campo__control"
                  value={categoria}
                  onChange={(evento) => setCategoria(evento.target.value)}
                  required
                >
                  <option value="">Elija una…</option>
                  {CATEGORIAS_MENSUAL.map((cat) => (
                    <option key={cat} value={cat}>
                      {cat}
                    </option>
                  ))}
                </select>
              </Campo>
            ) : null}
          </>
        )}

        <Campo etiqueta="Activa">
          <label className="fila">
            <input
              type="checkbox"
              checked={activo}
              onChange={(evento) => setActivo(evento.target.checked)}
            />
            <span className="tenue">
              Si está inactiva, la asignación se retira sin borrarla, para no
              perder la historia.
            </span>
          </label>
        </Campo>
      </form>
    </Dialogo>
  );
}


// ── Importación del Excel comercial ──────────────────────────────────────────
//
// El libro anual trae una hoja `RESUMEN (MES)` con los canales como filas
// (`SUPER MAYORISTA`, `MAYORISTA`, `TAT`, `Call Center`…) y los meses `ENE..DIC`
// como columnas. La importación lee el valor del mes del período **tal cual
// está almacenado** (sin escalar por 1 000) y lo vuelca en el bloque
// **commercial**, mapeando cada canal a vendedor, cliente y categoría A–F
// mediante la configuración de canales. Los canales sin mapeo se rechazan con
// su motivo.

function ImportarExcelComercial({ periodo }: { periodo: string }) {
  const importar = useImportarComercial(periodo);
  const [resultado, setResultado] =
    useState<ResultadoImportacionComercial | null>(null);

  function alSeleccionar(evento: React.ChangeEvent<HTMLInputElement>) {
    const archivo = evento.target.files?.[0];
    if (!archivo) return;
    importar.mutate(
      { archivo, motivo: `Importación del Excel ${archivo.name}` },
      {
        onSuccess: (res) => setResultado(res),
      },
    );
    evento.target.value = "";
  }

  return (
    <>
      <label className="boton boton--pequeno">
        {importar.isPending ? "Importando…" : "Importar Excel Comercial"}
        <input
          type="file"
          accept=".xlsx,.xlsm"
          hidden
          onChange={alSeleccionar}
        />
      </label>
      {resultado ? (
        <Dialogo
          abierto
          titulo={`Importación del Excel comercial · ${periodoLargo(periodo)}`}
          onCerrar={() => setResultado(null)}
          ancho
          pie={
            <button
              type="button"
              className="boton"
              onClick={() => setResultado(null)}
            >
              Cerrar
            </button>
          }
        >
          <div className="pila--compacta">
            <AvisoError error={importar.error} />
            <div className="fila">
              <div>
                <p className="tenue" style={{ fontWeight: 600 }}>
                  Aceptadas
                </p>
                <p style={{ fontSize: "1.25rem", fontWeight: 700 }}>
                  {resultado.aceptadas}
                </p>
              </div>
              <div>
                <p className="tenue" style={{ fontWeight: 600 }}>
                  Rechazadas
                </p>
                <p style={{ fontSize: "1.25rem", fontWeight: 700 }}>
                  {resultado.rechazadas}
                </p>
              </div>
              <div>
                <p className="tenue" style={{ fontWeight: 600 }}>
                  Total importado
                </p>
                <p style={{ fontSize: "1.25rem", fontWeight: 700 }}>
                  {dinero(resultado.total_monto)}
                </p>
              </div>
            </div>
            <p className="tenue">
              El total es la suma de las filas aceptadas, no la del libro: lo que
              se rechazó no entra al presupuesto.
            </p>

            {resultado.filas.length > 0 ? (
              <div className="tabla-envoltorio">
                <table className="tabla tabla--compacta">
                  <thead>
                    <tr>
                      <th scope="col">Canal</th>
                      <th scope="col">Vendedor</th>
                      <th scope="col">Cliente</th>
                      <th scope="col">Cat.</th>
                      <th scope="col">Monto</th>
                      <th scope="col">Estado</th>
                      <th scope="col">Motivo</th>
                    </tr>
                  </thead>
                  <tbody>
                    {resultado.filas.map((fila, indice) => (
                      <tr key={`${fila.canal}-${indice}`}>
                        <td>{fila.canal}</td>
                        <td className="mono">
                          {fila.vendedor_clave ?? "—"}
                        </td>
                        <td className="mono">
                          {fila.cliente_clave ?? "—"}
                        </td>
                        <td className="mono">{fila.categoria ?? "—"}</td>
                        <td className="numero">{dinero(fila.monto)}</td>
                        <td>
                          {fila.aceptada ? (
                            <span className="distintivo distintivo--exito">
                              Aceptada
                            </span>
                          ) : (
                            <span className="distintivo distintivo--peligro">
                              Rechazada
                            </span>
                          )}
                        </td>
                        <td className="tenue">{fila.motivo ?? ""}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
          </div>
        </Dialogo>
      ) : null}
    </>
  );
}

// ── Configuración de canales del Excel ────────────────────────────────────────

function ConfiguracionCanales() {
  const { data: mapeos, isLoading, error } = useCanalesMapeosMensual();
  const [abrirFormulario, setAbrirFormulario] = useState(false);
  const [mapeoEditar, setMapeoEditar] = useState<CanalMapeoMensual | null>(
    null,
  );

  return (
    <Tarjeta
      titulo="Mapeo de canales del Excel"
      descripcion="Configura a qué vendedor, cliente y categoría (A–F) pertenece cada canal del libro anual (`SUPER MAYORISTA`, `MAYORISTA`, `TAT`…). Es lo que usa la importación del Excel comercial: los canales sin mapeo se rechazan con su motivo."
      acciones={
        <button
          type="button"
          className="boton boton--pequeno"
          onClick={() => {
            setMapeoEditar(null);
            setAbrirFormulario(true);
          }}
        >
          Nuevo mapeo
        </button>
      }
      sinRelleno
    >
      <AvisoError error={error} />

      {isLoading ? <Cargando texto="Cargando mapeos de canal…" /> : null}

      {!isLoading && (mapeos === undefined || mapeos.length === 0) ? (
        <Vacio
          titulo="No hay mapeos de canal configurados"
          detalle="Los mapeos dicen al sistema a qué vendedor, cliente y categoría pertenece cada canal del Excel. Sin ellos, la importación rechaza todos los canales."
        />
      ) : null}

      {mapeos && mapeos.length > 0 ? (
        <div className="tabla-envoltorio">
          <table className="tabla tabla--compacta">
            <thead>
              <tr>
                <th scope="col">Canal</th>
                <th scope="col">Vendedor</th>
                <th scope="col">Cliente</th>
                <th scope="col">Categoría</th>
                <th scope="col">Activo</th>
                <th scope="col">
                  <span className="solo-lectores">Acciones</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {mapeos.map((mapeo) => (
                <tr key={mapeo.id}>
                  <td>{mapeo.canal}</td>
                  <td className="mono">{mapeo.vendedor_clave ?? "—"}</td>
                  <td className="mono">{mapeo.cliente_clave ?? "—"}</td>
                  <td className="mono">{mapeo.categoria ?? "—"}</td>
                  <td>{mapeo.activo ? "Sí" : "No"}</td>
                  <td>
                    <button
                      type="button"
                      className="boton boton--sutil boton--pequeno"
                      onClick={() => {
                        setMapeoEditar(mapeo);
                        setAbrirFormulario(true);
                      }}
                    >
                      Cambiar
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {abrirFormulario ? (
        <FormularioCanalMapeo
          mapeoExistente={mapeoEditar}
          onCerrar={() => setAbrirFormulario(false)}
        />
      ) : null}
    </Tarjeta>
  );
}

function FormularioCanalMapeo({
  mapeoExistente,
  onCerrar,
}: {
  mapeoExistente: CanalMapeoMensual | null;
  onCerrar: () => void;
}) {
  const guardar = useGuardarCanalMapeoMensual();
  const esEdicion = mapeoExistente !== null;

  const [canal, setCanal] = useState(mapeoExistente?.canal ?? "");
  const [vendedorClave, setVendedorClave] = useState(
    mapeoExistente?.vendedor_clave ?? "",
  );
  const [clienteClave, setClienteClave] = useState(
    mapeoExistente?.cliente_clave ?? "",
  );
  const [categoria, setCategoria] = useState(mapeoExistente?.categoria ?? "A");
  const [activo, setActivo] = useState(mapeoExistente?.activo ?? true);

  // Catálogos de vendedor y cliente para elegir a quién. La clave es la del
  // origen —la cédula del vendedor, el NIT del cliente—, así que no se teclea:
  // se escoge del catálogo que dejó la ingesta.
  const { data: vendedores } = useDimensionesAgro("vendedor");
  const { data: clientes } = useDimensionesAgro("cliente");

  function enviar(evento: React.FormEvent) {
    evento.preventDefault();
    const datos: EntradaCanalMapeoMensual = {
      canal,
      vendedor_clave: vendedorClave,
      cliente_clave: clienteClave,
      categoria,
      activo,
    };
    guardar.mutate(
      { datos, mapeoId: esEdicion ? mapeoExistente!.id : undefined },
      { onSuccess: onCerrar },
    );
  }

  return (
    <Dialogo
      abierto
      titulo={esEdicion ? "Cambiar mapeo de canal" : "Nuevo mapeo de canal"}
      onCerrar={onCerrar}
      pie={
        <>
          <button
            type="button"
            className="boton boton--sutil"
            onClick={onCerrar}
          >
            Cancelar
          </button>
          <button
            type="submit"
            form="formulario-canal-mapeo"
            className="boton"
            disabled={guardar.isPending}
          >
            {guardar.isPending ? "Guardando…" : "Guardar"}
          </button>
        </>
      }
    >
      <form
        id="formulario-canal-mapeo"
        className="pila--compacta"
        onSubmit={enviar}
      >
        <AvisoError error={guardar.error} />

        <Campo
          etiqueta="Canal del Excel"
          ayuda="El nombre tal como aparece en la hoja `RESUMEN (MES)`. Se normaliza (mayúsculas, sin tildes) al guardar."
        >
          <input
            className="campo__control"
            type="text"
            minLength={1}
            maxLength={120}
            value={canal}
            onChange={(evento) => setCanal(evento.target.value)}
            required
            disabled={esEdicion}
            placeholder="SUPER MAYORISTA"
          />
        </Campo>

        <Campo
          etiqueta="Vendedor"
          ayuda="Sale del catálogo que dejó la ingesta, no se escribe a mano."
        >
          <select
            className="campo__control"
            value={vendedorClave}
            onChange={(evento) => setVendedorClave(evento.target.value)}
            required
          >
            <option value="">Elija uno…</option>
            {(vendedores ?? []).map((m) => (
              <option key={m.clave} value={m.clave}>
                {m.nombre} · {m.clave}
              </option>
            ))}
          </select>
        </Campo>

        <Campo
          etiqueta="Cliente"
          ayuda="Sale del catálogo que dejó la ingesta, no se escribe a mano."
        >
          <select
            className="campo__control"
            value={clienteClave}
            onChange={(evento) => setClienteClave(evento.target.value)}
            required
          >
            <option value="">Elija uno…</option>
            {(clientes ?? []).map((m) => (
              <option key={m.clave} value={m.clave}>
                {m.nombre} · {m.clave}
              </option>
            ))}
          </select>
        </Campo>

        <Campo
          etiqueta="Categoría"
          ayuda="Categoría A–F del bloque comercial. Obligatoria."
        >
          <select
            className="campo__control"
            value={categoria}
            onChange={(evento) => setCategoria(evento.target.value)}
            required
          >
            {CATEGORIAS_MENSUAL.map((cat) => (
              <option key={cat} value={cat}>
                {cat}
              </option>
            ))}
          </select>
        </Campo>

        <Campo etiqueta="Activo">
          <label className="fila">
            <input
              type="checkbox"
              checked={activo}
              onChange={(evento) => setActivo(evento.target.checked)}
            />
            <span className="tenue">
              Si está inactivo, el mapeo se retira sin borrarse: la importación
              lo ignora.
            </span>
          </label>
        </Campo>
      </form>
    </Dialogo>
  );
}
