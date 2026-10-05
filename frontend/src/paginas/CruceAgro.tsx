/**
 * Vendedor × cliente, y el mismo cruce abierto por producto.
 *
 * Es lo que hoy se saca con una tabla dinámica sobre el libro de 18 MB, que es
 * justo la operación que este proyecto viene a quitar de en medio.
 *
 * La pantalla tiene una responsabilidad que las demás no tienen: **decir que la
 * lista está recortada**. El backend publica las filas de mayor venta hasta el
 * límite configurado y avisa con `truncado`; en una carga real de siete días, el
 * cruce de tres ejes dejó 198 millones fuera de las 500 filas publicadas. El
 * consolidado, en cambio, es el del corte entero —por eso la participación sigue
 * siendo cierta—, así que la suma de la columna **no** da el total de arriba. Sin
 * un aviso que se lea, esa diferencia parece un error de cuadre y no lo es.
 */

import { useMemo } from "react";
import { useSearchParams } from "react-router-dom";

import {
  useCruceAgro,
  useExportarAgro,
  useVentaDiariaAgro,
} from "@/api/consultasAgro";
import { AvisoError, Cargando, Tarjeta, Vacio } from "@/componentes/comunes";
import { useAuth } from "@/auth/ContextoAuth";
import {
  BarraFiltrosAgro,
  filtrosAgroDe,
  useFiltros,
} from "@/componentes/filtros";
import {
  AvisoCuadre,
  CeldasIndicadoresAgro,
  EncabezadosIndicadoresAgro,
  PieCalculoAgro,
} from "@/componentes/indicadoresAgro";
import {
  EJES_CRUCE,
  esEjeCruce,
  etiquetaEjeCrudo,
} from "@/utilidades/dominioAgro";
import { dinero, kilos, numero, porcentaje, sumar } from "@/utilidades/formato";

function periodoMesAnterior(periodo: string): string {
  const anio = Number(periodo.slice(0, 4));
  const mes = Number(periodo.slice(5, 7));
  const fecha = new Date(Date.UTC(anio, mes - 2, 1));
  return `${fecha.getUTCFullYear()}-${String(fecha.getUTCMonth() + 1).padStart(2, "0")}`;
}

function fechaMismoDiaMesAnterior(fecha: string): string | null {
  const [anioTexto, mesTexto, diaTexto] = fecha.split("-");
  const anio = Number(anioTexto);
  const mes = Number(mesTexto);
  const dia = Number(diaTexto);
  const fechaAnterior = new Date(Date.UTC(anio, mes - 2, 1));
  const anioAnterior = fechaAnterior.getUTCFullYear();
  const mesAnterior = fechaAnterior.getUTCMonth() + 1;
  const ultimoDia = new Date(Date.UTC(anioAnterior, mesAnterior, 0)).getUTCDate();
  if (dia > ultimoDia) return null;
  return `${anioAnterior}-${String(mesAnterior).padStart(2, "0")}-${String(dia).padStart(2, "0")}`;
}

function variacionPorcentual(actual: string, anterior: string): string {
  const [enteroActual = "0", fraccionActual = ""] = actual.split(".");
  const [enteroAnterior = "0", fraccionAnterior = ""] = anterior.split(".");
  const escala = Math.max(fraccionActual.length, fraccionAnterior.length);
  const valorActual = BigInt(enteroActual + fraccionActual.padEnd(escala, "0"));
  const valorAnterior = BigInt(enteroAnterior + fraccionAnterior.padEnd(escala, "0"));
  if (valorAnterior === 0n) return "—";

  const diferencia = valorActual - valorAnterior;
  const numerador = (diferencia < 0n ? -diferencia : diferencia) * 1000n;
  const milesimas = (numerador + valorAnterior / 2n) / valorAnterior;
  const signo = diferencia < 0n && milesimas > 0n ? "-" : "";
  const razon = `${signo}${milesimas / 1000n}.${String(milesimas % 1000n).padStart(3, "0")}`;
  return porcentaje(razon);
}

export function CruceAgro() {
  const { tienePermiso, usuario } = useAuth();
  const granular = usuario?.rol === "CONSULTA" && usuario.permisos.some((codigo) => codigo.startsWith("PERMISO_AGRO_"));
  const control = useFiltros();
  const { filtros } = control;

  const [parametros, setParametros] = useSearchParams();
  const crudo = parametros.get("por");
  const eje = esEjeCruce(crudo) ? crudo : "vendedor-cliente";
  const opcion = EJES_CRUCE.find((o) => o.valor === eje) ?? EJES_CRUCE[0]!;

  const filtrosAgro = useMemo(() => filtrosAgroDe(filtros), [filtros]);
  const { data, isLoading, error } = useCruceAgro(filtrosAgro, eje);
  const diariaActual = useVentaDiariaAgro(filtrosAgro, eje === "vendedor-cliente");
  const comparativoDiario = useMemo(() => {
    const diaria = diariaActual.data;
    if (!diaria) return null;

    const fechasAnteriores = diaria.fechas
      .map(fechaMismoDiaMesAnterior)
      .filter((fecha): fecha is string => fecha !== null);
    if (fechasAnteriores.length === 0) return null;

    return {
      filtros: {
        ...filtrosAgro,
        periodo: periodoMesAnterior(filtrosAgro.periodo),
        desde: fechasAnteriores[0],
        hasta: fechasAnteriores[fechasAnteriores.length - 1],
      },
    };
  }, [diariaActual.data, filtrosAgro]);
  const diariaAnterior = useVentaDiariaAgro(
    comparativoDiario?.filtros ?? filtrosAgro,
    comparativoDiario !== null,
  );
  const exportar = useExportarAgro();

  const medida = data?.medida ?? filtros.medida;
  const filas = data?.filas ?? [];
  const conMeta = false; // Ningún cruce se presupuesta: la meta no se reparte por pares.

  function cambiarEje(valor: string) {
    const siguientes = new URLSearchParams(parametros);
    siguientes.set("por", valor);
    setParametros(siguientes, { replace: true });
  }

  return (
    <div className="pila">
      <BarraFiltrosAgro
        control={control}
        acciones={
          <>
            {!granular || tienePermiso("PERMISO_AGRO_CONFIGURAR_EJE_CRUCE") ? <label className="filtros__campo">
              <span>Cruce</span>
              <select
                className="campo__control"
                value={eje}
                onChange={(evento) => cambiarEje(evento.target.value)}
                title={opcion.ayuda}
              >
                {EJES_CRUCE.map((o) => (
                  <option key={o.valor} value={o.valor} title={o.ayuda}>
                    {o.etiqueta}
                  </option>
                ))}
              </select>
            </label> : null}
            {!granular || tienePermiso("PERMISO_AGRO_DESCARGAR_CRUCE") ? <button
              type="button"
              className="boton boton--pequeno"
              onClick={() =>
                exportar.mutate({
                  reporte: "cruce",
                  filtros: filtrosAgro,
                  por: eje,
                })
              }
              disabled={exportar.isPending || !data}
            >
              {exportar.isPending ? "Generando…" : "Exportar a Excel"}
            </button> : null}
          </>
        }
      />

      <AvisoError error={error} />
      <AvisoError error={exportar.error} />
      {eje === "vendedor-cliente" ? <AvisoError error={diariaActual.error} /> : null}

      {isLoading ? <Cargando texto="Cruzando la venta…" /> : null}

      {data ? (
        <>
          <AvisoCuadre cuadre={data.parametros_calculo.cuadre} />

          {data.truncado ? (
            <div className="aviso aviso--atencion" role="note">
              <div>
                <strong>
                  Está viendo las {numero(filas.length)} combinaciones de mayor
                  venta, no todas.
                </strong>
                <p>
                  El cruce se recorta en {numero(data.limite)} filas. El
                  consolidado de la primera línea es el del corte{" "}
                  <em>completo</em> —por eso la participación de cada fila sigue
                  siendo cierta—, así que sumar la columna de venta da menos que
                  ese total, y la diferencia es exactamente la venta de las
                  filas que no se publican. Para ver menos combinaciones y que
                  quepan todas, estreche el rango de fechas o filtre por centro.
                </p>
              </div>
            </div>
          ) : null}

          <Tarjeta
            titulo={opcion.etiqueta}
            descripcion={opcion.ayuda}
            sinRelleno
            pie={
              <PieCalculoAgro
                parametros={data.parametros_calculo}
                medida={medida}
              />
            }
          >
            {filas.length === 0 ? (
              <Vacio
                titulo="Sin combinaciones"
                detalle="Ninguna línea coincide con los filtros seleccionados."
              />
            ) : (
              <div className="tabla-envoltorio tabla-envoltorio--alta">
                <table className="tabla tabla--anclada">
                  <caption className="solo-lectores">
                    Venta cruzada por {data.ejes.join(", ")}, al{" "}
                    {data.fecha_corte}.
                  </caption>
                  <thead>
                    <tr>
                      {/* Una columna por eje, tomada de `ejes`: los dos cruces
                          tienen distinto número y con campos fijos el de dos
                          arrastraría una columna vacía. */}
                      {data.ejes.map((nombre, indice) => (
                        <th
                          key={nombre}
                          scope="col"
                          className={indice === 0 ? "columna-ancla" : undefined}
                        >
                          {etiquetaEjeCrudo(nombre)}
                        </th>
                      ))}
                      <EncabezadosIndicadoresAgro
                        medida={medida}
                        conMeta={conMeta}
                        formulas={data.parametros_calculo.formulas}
                      />
                    </tr>
                  </thead>
                  <tbody>
                    <tr className="fila-total">
                      <th scope="row" className="columna-ancla">
                        CONSOLIDADO
                      </th>
                      {data.ejes.slice(1).map((nombre) => (
                        <td key={nombre} className="tenue">
                          {data.truncado ? "corte completo" : ""}
                        </td>
                      ))}
                      <CeldasIndicadoresAgro
                        fila={data.consolidado}
                        medida={medida}
                        conMeta={conMeta}
                        sujeto="la compañía"
                      />
                    </tr>

                    {filas.map((fila) => (
                      <tr key={fila.claves.join("·")}>
                        {fila.nombres.map((nombre, indice) => (
                          <th
                            key={`${fila.claves.join("·")}-${indice}`}
                            scope={indice === 0 ? "row" : undefined}
                            className={
                              indice === 0 ? "columna-ancla" : "columna-texto"
                            }
                          >
                            {nombre}
                          </th>
                        ))}
                        <CeldasIndicadoresAgro
                          fila={fila}
                          medida={medida}
                          conMeta={conMeta}
                          sujeto="esta combinación"
                        />
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Tarjeta>

          {eje === "vendedor-cliente" && diariaActual.data ? (
            <Tarjeta
              titulo="Comparativo diario vs. mes anterior"
              descripcion="Compara cada fecha con el mismo día calendario del mes anterior."
              sinRelleno
            >
              {diariaActual.isLoading || diariaAnterior.isLoading ? (
                <Cargando texto="Comparando ventas diarias…" />
              ) : diariaAnterior.error ? (
                <AvisoError error={diariaAnterior.error} />
              ) : comparativoDiario && diariaAnterior.data ? (
                <div className="tabla-envoltorio tabla-envoltorio--alta">
                  <table className="tabla tabla--compacta">
                    <thead>
                      <tr>
                        <th scope="col">Día</th>
                        <th scope="col" className="numero">Venta mes actual</th>
                        <th scope="col">Día mes anterior</th>
                        <th scope="col" className="numero">Venta mes anterior</th>
                        <th scope="col" className="numero">Diferencia</th>
                        <th scope="col" className="numero">Variación</th>
                      </tr>
                    </thead>
                    <tbody>
                      {diariaActual.data.fechas.map((fecha, indice) => {
                        const fechaAnterior = fechaMismoDiaMesAnterior(fecha);
                        const indiceAnterior = fechaAnterior
                          ? diariaAnterior.data.fechas.indexOf(fechaAnterior)
                          : -1;
                        const valorActual = diariaActual.data.totales.valores[indice] ?? "0";
                        const valorAnterior = indiceAnterior >= 0
                          ? diariaAnterior.data.totales.valores[indiceAnterior] ?? "0"
                          : null;
                        const diferencia = valorAnterior === null
                          ? null
                          : sumar(valorActual, `-${valorAnterior}`);
                        const formatearMedida = medida === "kilos" ? kilos : dinero;

                        return (
                          <tr key={fecha}>
                            <th scope="row">{fecha}</th>
                            <td className="numero">{formatearMedida(valorActual)}</td>
                            <td>{fechaAnterior ?? "—"}</td>
                            <td className="numero">{valorAnterior === null ? "—" : formatearMedida(valorAnterior)}</td>
                            <td className="numero">{diferencia === null ? "—" : formatearMedida(diferencia)}</td>
                            <td className="numero">{valorAnterior === null ? "—" : variacionPorcentual(valorActual, valorAnterior)}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              ) : (
                <Vacio
                  titulo="Sin días comparables"
                  detalle="El rango no contiene fechas con el mismo día calendario en el mes anterior."
                />
              )}
            </Tarjeta>
          ) : null}
        </>
      ) : null}
    </div>
  );
}
