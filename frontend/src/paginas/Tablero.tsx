/**
 * Tablero gerencial — la pantalla que abre el gerente.
 *
 * Está construida alrededor de una sola pregunta: ¿la compañía va donde debería
 * ir hoy? La respuesta se da tres veces con distinto grado de detalle —semáforo,
 * barra contra el ideal, cifras— para que se pueda leer en tres segundos, en
 * treinta, o con la calculadora al lado.
 */

import { Link } from "react-router-dom";

import { useExportar, useTablero } from "@/api/consultas";
import type { FilaGrupo } from "@/api/tipos";
import { useAuth } from "@/auth/ContextoAuth";
import { AvisoError, Cargando, Tarjeta, Vacio } from "@/componentes/comunes";
import { BarraFiltros, useFiltros } from "@/componentes/filtros";
import { BarraContraIdeal } from "@/componentes/graficos";
import {
  Indicador,
  PieCalculo,
  Semaforo,
  notaComparativa,
} from "@/componentes/indicadores";
import { FORMULAS } from "@/utilidades/dominio";
import {
  dineroCorto,
  kilos,
  porMedida,
  porcentaje,
  puntos,
} from "@/utilidades/formato";

export function Tablero() {
  const control = useFiltros();
  const { filtros } = control;
  const { data, isLoading, error } = useTablero(filtros);
  const exportar = useExportar();
  const { tienePermiso } = useAuth();

  const medida = data?.medida ?? filtros.medida;
  const grande = (valor: string | null) =>
    medida === "kilos" ? kilos(valor) : dineroCorto(valor);

  return (
    <div className="pila">
      <BarraFiltros
        control={control}
        mostrar={{ grupo: false, puntoVenta: false }}
        acciones={tienePermiso("PERMISO_DESCARGAR_TABLERO") ? (
          <button
            type="button"
            className="boton boton--pequeno"
            onClick={() => exportar.mutate({ reporte: "tablero", filtros })}
            disabled={exportar.isPending}
          >
            {exportar.isPending ? "Generando…" : "Exportar a Excel"}
          </button>
        ) : undefined}
      />

      <AvisoError error={error} />
      <AvisoError error={exportar.error} />

      {isLoading ? <Cargando texto="Consolidando el período…" /> : null}

      {data ? (
        <>
          <Tarjeta
            titulo="Consolidado de la compañía"
            descripcion={`Venta acumulada contra presupuesto del mes, al ${data.fecha_corte}.`}
            pie={
              <PieCalculo
                parametros={data.parametros_calculo}
                medida={medida}
              />
            }
          >
            <div className="consolidado">
              <div className="consolidado__foco">
                <p className="consolidado__etiqueta">Cumplimiento</p>
                <p className="consolidado__cifra">
                  {porcentaje(data.consolidado.cumplimiento)}
                </p>
                <Semaforo estado={data.consolidado.semaforo} />
                <p className="consolidado__brecha">
                  {puntos(data.consolidado.brecha)} frente al ideal
                </p>
                <p className="tenue">
                  {notaComparativa(
                    data.consolidado.cumplimiento,
                    data.consolidado.ideal,
                  )}
                </p>
              </div>

              <div className="consolidado__barra">
                <BarraContraIdeal
                  cumplimiento={data.consolidado.cumplimiento}
                  ideal={data.consolidado.ideal}
                  semaforo={data.consolidado.semaforo}
                  etiqueta="Consolidado de la compañía"
                />
              </div>
            </div>

            <div className="rejilla rejilla--indicadores">
              <Indicador
                etiqueta="Presupuesto del mes"
                valor={grande(data.consolidado.presupuesto)}
                nota={porMedida(data.consolidado.presupuesto, medida)}
              />
              <Indicador
                etiqueta="Venta acumulada"
                valor={grande(data.consolidado.venta)}
                nota={porMedida(data.consolidado.venta, medida)}
              />
              <Indicador
                etiqueta="Proyección al cierre"
                valor={grande(data.consolidado.proyeccion)}
                nota={`${porcentaje(data.consolidado.cumplimiento_proyectado)} del presupuesto`}
                pista={<p className="formula">{FORMULAS.proyeccion}</p>}
              />
              <Indicador
                etiqueta="Venta diaria requerida"
                valor={grande(data.consolidado.venta_diaria_requerida)}
                nota="Para llegar al presupuesto con los días que quedan"
                pista={
                  <p className="formula">{FORMULAS.venta_diaria_requerida}</p>
                }
              />
              <Indicador
                etiqueta="Venta diaria promedio"
                valor={grande(data.consolidado.venta_diaria_promedio)}
                nota="Ritmo actual"
                pista={
                  <p className="formula">{FORMULAS.venta_diaria_promedio}</p>
                }
              />
              <Indicador
                etiqueta="Crecimiento año anterior"
                valor={porcentaje(data.consolidado.crecimiento)}
                nota={`Año anterior: ${porMedida(data.consolidado.venta_anio_anterior, medida)}`}
                pista={<p className="formula">{FORMULAS.crecimiento}</p>}
              />
              <Indicador
                etiqueta="Margen"
                valor={porcentaje(data.consolidado.margen_porcentaje)}
                nota={porMedida(data.consolidado.margen_valor, "valor")}
                pista={
                  <>
                    <p className="formula">{FORMULAS.margen_porcentaje}</p>
                    <p className="tenue">
                      Se calcula sobre los totales, nunca promediando el
                      porcentaje que envía SIESA línea a línea.
                    </p>
                  </>
                }
              />
            </div>
          </Tarjeta>

          <Tarjeta
            titulo="Los cuatro grupos"
            descripcion="Cada barra llega hasta donde se ha cumplido; la marca vertical es dónde debería ir hoy."
          >
            {data.grupos.length === 0 ? (
              <Vacio
                titulo="Sin grupos"
                detalle="El período no tiene agrupaciones con presupuesto."
              />
            ) : (
              <div className="rejilla rejilla--grupos">
                {data.grupos.map((grupo) => (
                  <TarjetaGrupo
                    key={grupo.codigo}
                    grupo={grupo}
                    medida={medida}
                  />
                ))}
              </div>
            )}
          </Tarjeta>

          <Tarjeta
            titulo="Venta sin presupuesto"
            descripcion="Puntos que venden y no están presupuestados. Se reportan aparte y no descuadran el consolidado."
          >
            {data.sin_presupuesto.length === 0 ? (
              <p className="tenue">
                Ningún punto de venta registró venta fuera del presupuesto en
                este período.
              </p>
            ) : (
              <ul className="lista-simple">
                {data.sin_presupuesto.map((punto) => (
                  <li key={punto.codigo_co}>
                    <span className="mono">{punto.codigo_co}</span>{" "}
                    {punto.nombre}
                    <strong className="empujar">
                      {porMedida(punto.venta, medida)}
                    </strong>
                  </li>
                ))}
              </ul>
            )}
          </Tarjeta>
        </>
      ) : null}
    </div>
  );
}

function TarjetaGrupo({
  grupo,
  medida,
}: {
  grupo: FilaGrupo;
  medida: "valor" | "kilos";
}) {
  return (
    <article className="grupo">
      <header className="grupo__cabecera">
        <div>
          <h3>{grupo.nombre}</h3>
          <span className="tenue mono">{grupo.codigo}</span>
        </div>
        <Semaforo estado={grupo.semaforo} />
      </header>

      <p className="grupo__cifra">{porcentaje(grupo.cumplimiento)}</p>
      <p className="tenue">
        Ideal {porcentaje(grupo.ideal)} · brecha {puntos(grupo.brecha)}
      </p>

      <BarraContraIdeal
        cumplimiento={grupo.cumplimiento}
        ideal={grupo.ideal}
        semaforo={grupo.semaforo}
        etiqueta={grupo.nombre}
        compacta
      />

      <dl className="grupo__detalle">
        <div>
          <dt>Presupuesto</dt>
          <dd>{porMedida(grupo.presupuesto, medida)}</dd>
        </div>
        <div>
          <dt>Venta</dt>
          <dd>{porMedida(grupo.venta, medida)}</dd>
        </div>
        <div>
          <dt>Proyección</dt>
          <dd>
            {porMedida(grupo.proyeccion, medida)}{" "}
            <span className="tenue">
              ({porcentaje(grupo.cumplimiento_proyectado)})
            </span>
          </dd>
        </div>
        <div>
          <dt>V. diaria requerida</dt>
          <dd>{porMedida(grupo.venta_diaria_requerida, medida)}</dd>
        </div>
      </dl>

      <Link
        className="grupo__enlace"
        to={`/cumplimiento?grupo=${grupo.codigo}&medida=${medida}`}
      >
        Ver los puntos de venta del grupo →
      </Link>
    </article>
  );
}
