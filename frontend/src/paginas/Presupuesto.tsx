/**
 * Parametrización de presupuesto.
 *
 * Es la pantalla que sustituye al armado manual del libro: se captura una vez
 * por período, punto de venta y categoría, en pesos y en kilos, con motivo
 * obligatorio. Tres reglas de §7 se hacen cumplir aquí de forma visible:
 * un período cerrado no admite cambios, todo cambio queda con autor y motivo, y
 * el total del punto no se captura —se calcula.
 *
 * Solo la ven los roles GERENTE y ANALISTA (§8.4).
 */

import { useMemo, useState } from "react";
import type { FormEvent } from "react";

import {
  useCargaMasivaPresupuesto,
  useCategorias,
  useCerrarPeriodo,
  useGuardarPresupuesto,
  useHistorialPresupuesto,
  usePeriodos,
  usePresupuesto,
  usePuntosVenta,
} from "@/api/consultas";
import type { Categoria, FilaPresupuesto } from "@/api/tipos";
import { useAuth } from "@/auth/ContextoAuth";
import {
  AvisoError,
  Campo,
  Dialogo,
  Distintivo,
  Tarjeta,
  Vacio,
} from "@/componentes/comunes";
import { useFiltros } from "@/componentes/filtros";
import { etiquetaDe } from "@/utilidades/dominio";
import {
  dinero,
  fechaHora,
  kilos,
  numero,
  periodoLargo,
} from "@/utilidades/formato";

/**
 * Normaliza lo que el usuario escribe al decimal que espera la API.
 *
 * Acepta la escritura colombiana (`1.250.000,50`) y la técnica (`1250000.50`) y
 * devuelve siempre `1250000.50`. Nunca convierte a `number`: el valor viaja como
 * cadena de extremo a extremo, igual que llegó.
 */
export function normalizarDecimal(entrada: string): string | null {
  const limpio = entrada.trim().replace(/\s/g, "");
  if (limpio === "") return null;

  let normalizado = limpio;
  if (limpio.includes(",")) {
    // Coma decimal: los puntos que haya son separadores de miles.
    normalizado = limpio.replaceAll(".", "").replace(",", ".");
  } else if ((limpio.match(/\./g) ?? []).length > 1) {
    // Varios puntos y ninguna coma: solo pueden ser separadores de miles.
    normalizado = limpio.replaceAll(".", "");
  }

  return /^\d+(\.\d{1,4})?$/.test(normalizado) ? normalizado : null;
}

interface EdicionActiva {
  categoria: Categoria;
  monto: string;
  kilos: string;
  motivo: string;
}

export function Presupuesto() {
  const { filtros, fijar } = useFiltros();
  const { tieneRol } = useAuth();

  const puntoVenta = filtros.punto_venta ?? "";
  const { data: puntos } = usePuntosVenta();
  const { data: categorias } = useCategorias();
  const { data: periodos } = usePeriodos();
  const {
    data: filas,
    isLoading,
    error,
  } = usePresupuesto(filtros.periodo, puntoVenta);
  const { data: historial } = useHistorialPresupuesto(
    filtros.periodo,
    puntoVenta,
  );

  const guardar = useGuardarPresupuesto(filtros.periodo, puntoVenta);
  const cargaMasiva = useCargaMasivaPresupuesto(filtros.periodo, puntoVenta);
  const cerrar = useCerrarPeriodo();

  const [edicion, setEdicion] = useState<EdicionActiva | null>(null);
  const [errorFormulario, setErrorFormulario] = useState<string | null>(null);
  const [archivo, setArchivo] = useState<File | null>(null);

  const periodoActualInfo = periodos?.find(
    (item) => item.periodo === filtros.periodo,
  );
  const cerrado = periodoActualInfo?.cerrado ?? false;
  const puntoSeleccionado = puntos?.find(
    (punto) => punto.codigo_co === puntoVenta,
  );

  /**
   * Se listan todas las categorías del catálogo, no solo las que ya tienen
   * presupuesto: la ausencia de una categoría no es un error (§3.1) pero sí es
   * algo que el analista debe poder ver y llenar sin adivinar cuál falta.
   */
  const lineas = useMemo(() => {
    const porCodigo = new Map<string, FilaPresupuesto>();
    for (const fila of filas ?? []) {
      const clave = etiquetaDe(fila.categoria).toUpperCase();
      porCodigo.set(clave, fila);
    }
    return (categorias ?? []).map((categoria) => ({
      categoria,
      fila:
        porCodigo.get(categoria.nombre.toUpperCase()) ??
        porCodigo.get(categoria.codigo.toUpperCase()) ??
        null,
    }));
  }, [filas, categorias]);

  function abrirEdicion(categoria: Categoria, fila: FilaPresupuesto | null) {
    setErrorFormulario(null);
    setEdicion({
      categoria,
      monto: fila?.monto ?? "",
      kilos: fila?.kilos ?? "",
      motivo: "",
    });
  }

  function alGuardar(evento: FormEvent) {
    evento.preventDefault();
    if (!edicion || !puntoSeleccionado) return;

    const monto = normalizarDecimal(edicion.monto);
    const kilosNormalizados = normalizarDecimal(edicion.kilos);

    if (monto === null || kilosNormalizados === null) {
      setErrorFormulario(
        "Escriba montos y kilos como números: 1.250.000,50 o 1250000.50. No se admiten letras ni símbolos.",
      );
      return;
    }
    if (edicion.motivo.trim().length < 5) {
      setErrorFormulario(
        "El motivo es obligatorio: un presupuesto que cambia sin rastro no sirve para evaluar a nadie.",
      );
      return;
    }

    setErrorFormulario(null);
    guardar.mutate(
      {
        periodo: filtros.periodo,
        punto_venta_id: puntoSeleccionado.id,
        categoria_id: edicion.categoria.id,
        monto,
        kilos: kilosNormalizados,
        motivo: edicion.motivo.trim(),
      },
      { onSuccess: () => setEdicion(null) },
    );
  }

  return (
    <div className="pila">
      <section
        className="filtros"
        aria-label="Selección de período y punto de venta"
      >
        <label className="filtros__campo">
          <span>Período</span>
          <input
            className="campo__control"
            type="month"
            value={filtros.periodo}
            onChange={(evento) => fijar("periodo", evento.target.value)}
          />
        </label>

        <label className="filtros__campo">
          <span>Punto de venta</span>
          <select
            className="campo__control"
            value={puntoVenta}
            onChange={(evento) => fijar("punto_venta", evento.target.value)}
          >
            <option value="">Seleccione…</option>
            {(puntos ?? [])
              .filter((punto) => punto.presupuestado)
              .map((punto) => (
                <option key={punto.codigo_co} value={punto.codigo_co}>
                  {punto.codigo_co} · {punto.nombre}
                </option>
              ))}
          </select>
        </label>

        <div className="filtros__campo">
          <span>Estado del período</span>
          <div>
            {cerrado ? (
              <Distintivo tono="peligro">Cerrado</Distintivo>
            ) : (
              <Distintivo tono="exito">Abierto</Distintivo>
            )}
          </div>
        </div>

        {tieneRol("GERENTE") && !cerrado ? (
          <div className="filtros__acciones">
            <button
              type="button"
              className="boton boton--pequeno"
              onClick={() => {
                if (
                  window.confirm(
                    `¿Cerrar el período ${filtros.periodo}? Un período cerrado no admite cambios de presupuesto.`,
                  )
                ) {
                  cerrar.mutate(filtros.periodo);
                }
              }}
              disabled={cerrar.isPending}
            >
              Cerrar período
            </button>
          </div>
        ) : null}
      </section>

      <AvisoError error={error} />
      <AvisoError error={cerrar.error} />

      {cerrado ? (
        <div className="aviso aviso--advertencia" role="status">
          <div>
            <strong>
              El período {periodoLargo(filtros.periodo)} está cerrado.
            </strong>
            <p>
              Cerrado por {periodoActualInfo?.cerrado_por ?? "—"} el{" "}
              {fechaHora(periodoActualInfo?.cerrado_en)}. La captura está
              bloqueada; el histórico se puede seguir consultando.
            </p>
          </div>
        </div>
      ) : null}

      {puntoVenta === "" ? (
        <Tarjeta titulo="Captura por categoría">
          <Vacio
            titulo="Seleccione un punto de venta"
            detalle="El presupuesto se parametriza por período, punto de venta y categoría."
          />
        </Tarjeta>
      ) : (
        <Tarjeta
          titulo={`Presupuesto de ${puntoSeleccionado?.nombre ?? puntoVenta}`}
          descripcion={`${periodoLargo(filtros.periodo)} · en pesos y en kilos`}
          sinRelleno
          pie={
            <p className="tenue">
              Aquí no se muestra el total del punto de venta a propósito: el
              presupuesto del punto es la suma de sus categorías y el del grupo
              la suma de sus puntos, y esa suma la calcula el backend con
              aritmética decimal exacta. Sumar importes en el navegador es
              precisamente lo que corrompe cifras de miles de millones.
            </p>
          }
        >
          {isLoading ? (
            <p className="cargando">Cargando el presupuesto…</p>
          ) : (
            <div className="tabla-envoltorio">
              <table className="tabla">
                <thead>
                  <tr>
                    <th scope="col">Categoría</th>
                    <th scope="col" className="numero">
                      Presupuesto ($)
                    </th>
                    <th scope="col" className="numero">
                      Presupuesto (kg)
                    </th>
                    <th scope="col">Último cambio</th>
                    <th scope="col">
                      <span className="solo-lectores">Acciones</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {lineas.map(({ categoria, fila }) => (
                    <tr key={categoria.codigo}>
                      <th scope="row">{categoria.nombre}</th>
                      <td className="numero">{dinero(fila?.monto ?? null)}</td>
                      <td className="numero">{kilos(fila?.kilos ?? null)}</td>
                      <td className="tenue">
                        {fila?.actualizado_en ? (
                          <>
                            {fechaHora(fila.actualizado_en)}
                            <br />
                            {fila.actualizado_por ?? "—"}
                          </>
                        ) : (
                          "Sin parametrizar"
                        )}
                      </td>
                      <td>
                        <button
                          type="button"
                          className="boton boton--pequeno"
                          onClick={() => abrirEdicion(categoria, fila)}
                          disabled={cerrado}
                        >
                          {fila ? "Editar" : "Parametrizar"}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Tarjeta>
      )}

      <Tarjeta
        titulo="Carga masiva"
        descripcion="Archivo .xlsx o .csv con el presupuesto del período, como se arma hoy."
      >
        <form
          className="fila fila--envolvente"
          onSubmit={(evento) => {
            evento.preventDefault();
            if (archivo) cargaMasiva.mutate(archivo);
          }}
        >
          <input
            className="campo__control"
            type="file"
            accept=".xlsx,.csv"
            aria-label="Archivo de presupuesto"
            onChange={(evento) => setArchivo(evento.target.files?.[0] ?? null)}
            disabled={cerrado}
          />
          <button
            type="submit"
            className="boton boton--principal boton--pequeno"
            disabled={!archivo || cerrado || cargaMasiva.isPending}
          >
            {cargaMasiva.isPending ? "Cargando…" : "Cargar"}
          </button>
        </form>

        <AvisoError error={cargaMasiva.error} />

        {cargaMasiva.data ? (
          <div className="pila pila--compacta" style={{ marginTop: "1rem" }}>
            <p>
              <strong>{numero(cargaMasiva.data.aceptadas)}</strong> filas
              aceptadas · <strong>{numero(cargaMasiva.data.rechazadas)}</strong>{" "}
              rechazadas.
            </p>
            {cargaMasiva.data.errores.length > 0 ? (
              <div className="tabla-envoltorio">
                <table className="tabla">
                  <thead>
                    <tr>
                      <th scope="col" className="numero">
                        Fila
                      </th>
                      <th scope="col">Motivo del rechazo</th>
                    </tr>
                  </thead>
                  <tbody>
                    {cargaMasiva.data.errores.map((fallo) => (
                      <tr key={`${fallo.fila}-${fallo.motivo}`}>
                        <td className="numero">{numero(fallo.fila)}</td>
                        <td>{fallo.motivo}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
          </div>
        ) : null}
      </Tarjeta>

      <Tarjeta
        titulo="Historial de cambios"
        descripcion="Quién cambió qué, cuándo y por qué."
        sinRelleno
      >
        {puntoVenta === "" ? (
          <Vacio titulo="Seleccione un punto de venta" />
        ) : (historial ?? []).length === 0 ? (
          <Vacio
            titulo="Sin cambios registrados"
            detalle="Este período no tiene modificaciones."
          />
        ) : (
          <div className="tabla-envoltorio">
            <table className="tabla">
              <thead>
                <tr>
                  <th scope="col">Cuándo</th>
                  <th scope="col">Quién</th>
                  <th scope="col">Campo</th>
                  <th scope="col" className="numero">
                    Antes
                  </th>
                  <th scope="col" className="numero">
                    Después
                  </th>
                  <th scope="col">Motivo</th>
                </tr>
              </thead>
              <tbody>
                {(historial ?? []).map((cambio, indice) => (
                  <tr key={`${cambio.cuando}-${indice}`}>
                    <td>{fechaHora(cambio.cuando)}</td>
                    <td>{cambio.quien}</td>
                    <td>{cambio.campo}</td>
                    <td className="numero suave">
                      {numero(cambio.valor_anterior)}
                    </td>
                    <td className="numero">{numero(cambio.valor_nuevo)}</td>
                    <td>{cambio.motivo ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Tarjeta>

      <Dialogo
        abierto={edicion !== null}
        titulo={edicion ? `Presupuesto de ${edicion.categoria.nombre}` : ""}
        onCerrar={() => setEdicion(null)}
      >
        {edicion ? (
          <form
            className="pila"
            onSubmit={alGuardar}
            id="formulario-presupuesto"
          >
            {errorFormulario ? (
              <div className="aviso aviso--error" role="alert">
                {errorFormulario}
              </div>
            ) : null}
            <AvisoError error={guardar.error} />

            <Campo
              etiqueta="Presupuesto en pesos"
              ayuda="Por ejemplo 512.000.000 o 512000000"
            >
              <input
                className="campo__control"
                inputMode="decimal"
                value={edicion.monto}
                onChange={(evento) =>
                  setEdicion({ ...edicion, monto: evento.target.value })
                }
                required
              />
            </Campo>

            <Campo
              etiqueta="Presupuesto en kilos"
              ayuda="Admite decimales: 23.272,73"
            >
              <input
                className="campo__control"
                inputMode="decimal"
                value={edicion.kilos}
                onChange={(evento) =>
                  setEdicion({ ...edicion, kilos: evento.target.value })
                }
                required
              />
            </Campo>

            <Campo
              etiqueta="Motivo del cambio"
              ayuda="Queda en el historial junto a su usuario y la fecha."
            >
              <textarea
                className="campo__control"
                value={edicion.motivo}
                onChange={(evento) =>
                  setEdicion({ ...edicion, motivo: evento.target.value })
                }
                required
                minLength={5}
                maxLength={500}
              />
            </Campo>

            <div className="grupo-botones">
              <button
                type="submit"
                className="boton boton--principal"
                disabled={guardar.isPending}
              >
                {guardar.isPending ? "Guardando…" : "Guardar"}
              </button>
              <button
                type="button"
                className="boton"
                onClick={() => setEdicion(null)}
              >
                Cancelar
              </button>
            </div>
          </form>
        ) : null}
      </Dialogo>
    </div>
  );
}
