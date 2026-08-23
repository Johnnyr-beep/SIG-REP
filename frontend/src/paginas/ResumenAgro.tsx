/**
 * Venta de agropecuaria por cualquiera de los siete ejes.
 *
 * Una pantalla y no siete. El usuario pidió la venta por centro de operaciones,
 * por bienes y servicios, por especie, por categoría, por vendedor y por
 * cliente: siete lecturas de la misma venta que se distinguen en una sola cosa,
 * el `GROUP BY`. Siete pantallas idénticas habrían sido siete sitios donde
 * arreglar el mismo defecto, y el día que la fuente traiga un eje más habría
 * que inventarse una octava.
 *
 * Lo que sí cambia con el eje es si hay meta contra la que medir. El negocio
 * presupuesta por centro, especie, tipo comercial y vendedor; por cliente, grupo
 * y tipo de ítem **no**. En esos tres la tabla no trae las columnas de
 * cumplimiento y lo dice —`AvisoEjeSinMeta`— en lugar de dejar una fila de
 * guiones que se lee como un dato pendiente de cargar.
 */

import { useMemo } from "react";
import { useSearchParams } from "react-router-dom";

import {
  useExportarAgro,
  useResumenAgro,
  useVentaDiariaAgro,
} from "@/api/consultasAgro";
import type { FilaResumenAgro, IndicadoresAgro } from "@/api/tiposAgro";
import type { Medida } from "@/api/tipos";
import { AvisoError, Cargando, Tarjeta, Vacio } from "@/componentes/comunes";
import { Indicador } from "@/componentes/indicadores";
import { AnilloCumplimiento, TendenciaAcumulada } from "@/componentes/graficos";
import type { PuntoAcumulado } from "@/componentes/graficos";
import {
  dinero,
  fecha,
  kilos,
  multiplicar,
  porcentaje,
  porMedida,
  sumar,
} from "@/utilidades/formato";
import {
  BarraFiltrosAgro,
  filtrosAgroDe,
  useFiltros,
} from "@/componentes/filtros";
import {
  AvisoCuadre,
  AvisoEjeSinMeta,
  AvisoSinPresupuestoCapturado,
  CeldasIndicadoresAgro,
  EncabezadosIndicadoresAgro,
  PieCalculoAgro,
  columnasIndicadoresAgro,
} from "@/componentes/indicadoresAgro";
import {
  EJES_RESUMEN,
  dimensionDeEje,
  esEjeResumen,
  ejeSinClavePropia,
  opcionDeEje,
} from "@/utilidades/dominioAgro";

export function ResumenAgro() {
  const control = useFiltros();
  const { filtros } = control;

  // El eje vive en la barra de direcciones, no en el estado del componente: la
  // pantalla se comparte por correo y el enlace tiene que llevar consigo qué se
  // estaba mirando, igual que lleva el período y el corte.
  const [parametros, setParametros] = useSearchParams();
  const crudo = parametros.get("por");
  const eje = esEjeResumen(crudo) ? crudo : "centro_operacion";
  const opcion = opcionDeEje(eje);

  const filtrosAgro = useMemo(() => filtrosAgroDe(filtros), [filtros]);
  const { data, isLoading, error } = useResumenAgro(filtrosAgro, eje);

  // Las tarjetas muestran pesos **y** kilos a la vez, y el presupuesto y el
  // cumplimiento vienen en la medida del reporte: una sola respuesta no trae
  // los dos. Se pide el mismo corte en la otra medida.
  //
  // No es una consulta de mas disfrazada: es la operacion correcta, sale del
  // mismo servicio —asi que las dos cifras no pueden discrepar— y deja las dos
  // medidas en cache, con lo que conmutar entre pesos y kilos pasa a ser
  // instantaneo en vez de otra espera.
  const filtrosOtraMedida = useMemo(
    () =>
      ({
        ...filtrosAgro,
        medida: filtrosAgro.medida === "kilos" ? "valor" : "kilos",
      }) as const,
    [filtrosAgro],
  );
  const { data: otra } = useResumenAgro(filtrosOtraMedida, eje);

  // La tendencia sale de la serie diaria, que es otro reporte. Se pide con el
  // mismo periodo y el mismo corte para que las dos figuras de la pantalla
  // hablen del mismo trozo de mes.
  const { data: diaria } = useVentaDiariaAgro(filtrosAgro);

  const exportar = useExportarAgro();

  const medida = data?.medida ?? filtros.medida;
  const filas = data?.filas ?? [];
  // Quien manda es la respuesta, no la tabla de ejes del frontend: si el backend
  // deja de publicar presupuesto para un eje, la pantalla se entera sola.
  const conMeta = data ? data.consolidado.presupuesto !== null : false;

  /**
   * La serie diaria convertida en dos acumulados.
   *
   * Se acumula **aqui y no en el servidor** porque no es un calculo de negocio:
   * es la misma cifra que ya publica la respuesta, sumada para dibujarla. El
   * total del ultimo punto tiene que coincidir con el que ensena la tabla, y
   * coincide por construccion: sale de los mismos valores.
   *
   * Los dias sin venta registrada llegan `null`, que no es lo mismo que un dia
   * de venta cero. Para el acumulado se tratan como que no aportan —la linea
   * sigue plana— en lugar de romper la serie: un hueco en una linea acumulada
   * se leeria como una caida, y no la hubo.
   */
  const acumulados = useMemo<PuntoAcumulado[]>(() => {
    if (!diaria) return [];

    const metaDiaria = diaria.totales.presupuesto_diario;
    let corrido: string | null = "0";

    return diaria.fechas.map((fecha, indice) => {
      const valor = diaria.totales.valores[indice] ?? null;
      // Suma exacta sobre las cadenas del contrato, sin pasar por `Number`.
      // Acumulando en coma flotante, veintiún días de cifras de mil millones
      // acaban desviando la línea de la cifra que publica la tabla de abajo, y
      // la pantalla se contradice consigo misma por un problema de binario.
      if (valor !== null) corrido = sumar(corrido, valor);

      return {
        fecha,
        acumulado: corrido,
        meta: multiplicar(metaDiaria, String(indice + 1)),
      };
    });
  }, [diaria]);

  // Cual de las dos respuestas trae los pesos y cual los kilos. Se resuelve una
  // vez: repetir el condicional en cada figura es como se acaba con una en pesos
  // y otra en kilos sin que nadie lo note.
  const consolidadoPesos =
    medida === "kilos"
      ? (otra?.consolidado ?? null)
      : (data?.consolidado ?? null);
  const consolidadoKilos =
    medida === "kilos"
      ? (data?.consolidado ?? null)
      : (otra?.consolidado ?? null);

  const enPesos = {
    cumplimiento: consolidadoPesos?.cumplimiento ?? null,
    ideal: consolidadoPesos?.ideal ?? null,
    semaforo: consolidadoPesos?.semaforo,
  };
  const enKilos = {
    cumplimiento: consolidadoKilos?.cumplimiento ?? null,
    ideal: consolidadoKilos?.ideal ?? null,
    semaforo: consolidadoKilos?.semaforo,
  };

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
            <label className="filtros__campo">
              <span>Ver por</span>
              <select
                className="campo__control"
                value={eje}
                onChange={(evento) => cambiarEje(evento.target.value)}
                title={opcion.ayuda}
              >
                {EJES_RESUMEN.map((opcion) => (
                  <option
                    key={opcion.valor}
                    value={opcion.valor}
                    title={opcion.ayuda}
                  >
                    {opcion.etiqueta}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              className="boton boton--pequeno"
              onClick={() =>
                exportar.mutate({
                  reporte: "resumen",
                  filtros: filtrosAgro,
                  por: eje,
                })
              }
              disabled={exportar.isPending || !data}
            >
              {exportar.isPending ? "Generando…" : "Exportar a Excel"}
            </button>
          </>
        }
      />

      <AvisoError error={error} />
      <AvisoError error={exportar.error} />

      {isLoading ? (
        <Cargando texto={`Calculando la venta por ${opcion.singular}…`} />
      ) : null}

      {data ? (
        <>
          <AvisoCuadre cuadre={data.parametros_calculo.cuadre} />
          {/* Dos avisos distintos para dos hechos distintos, que el backend
              no separa: en los dos manda `presupuesto` vacio. Si el eje es una
              de las cuatro dimensiones presupuestables, hay vara y lo que falta
              es capturarla —y el aviso lleva al sitio donde se captura—; si no
              lo es, ahi no hay vara y no la va a haber. Decir lo segundo
              agrupando por centro se contradecia con su propia frase
              siguiente. */}
          {conMeta ? null : dimensionDeEje(eje) ? (
            <AvisoSinPresupuestoCapturado
              eje={opcion.singular}
              dimension={dimensionDeEje(eje)!}
              periodo={filtros.periodo}
            />
          ) : (
            <AvisoEjeSinMeta eje={opcion.singular} />
          )}

          <TarjetasResumen
            enPesos={consolidadoPesos}
            enKilos={consolidadoKilos}
          />

          <div className="rejilla rejilla--panel">
            <Tarjeta titulo="Cumplimiento del mes">
              <div className="anillos">
                <AnilloCumplimiento etiqueta="Pesos" {...enPesos} />
                <AnilloCumplimiento etiqueta="Kilos" {...enKilos} />
              </div>
            </Tarjeta>

            <Tarjeta
              titulo="Tendencia de ventas"
              descripcion="Las dos series van acumuladas: la distancia entre ellas es lo que falta para la meta."
            >
              <TendenciaAcumulada
                puntos={acumulados}
                titulo="Venta acumulada contra meta acumulada"
                formatear={(valor) => porMedida(valor, medida)}
              />
            </Tarjeta>

            <Tarjeta
              titulo={`Mayores por ${opcion.singular}`}
              descripcion={`Los diez de mayor venta del corte, de ${filas.length}.`}
              sinRelleno
            >
              <Escalafon
                filas={filas.slice(0, 10)}
                medida={medida}
                sujeto={opcion.singular}
              />
            </Tarjeta>
          </div>

          <Tarjeta
            titulo={`Venta por ${opcion.singular}`}
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
                titulo={`Sin venta por ${opcion.singular}`}
                detalle="Ninguna línea coincide con los filtros seleccionados."
              />
            ) : (
              <div className="tabla-envoltorio tabla-envoltorio--alta">
                <table className="tabla tabla--anclada">
                  <caption className="solo-lectores">
                    Venta de agropecuaria agrupada por {opcion.singular}, al{" "}
                    {data.fecha_corte}.
                  </caption>
                  <thead>
                    <tr>
                      <th scope="col" className="columna-ancla">
                        {opcion.etiqueta}
                      </th>
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
                        CONSOLIDADO · {filas.length} {opcion.singular}
                        {filas.length === 1 ? "" : "s"}
                      </th>
                      <CeldasIndicadoresAgro
                        fila={data.consolidado}
                        medida={medida}
                        conMeta={conMeta}
                        sujeto="la compañía"
                      />
                    </tr>

                    {filas.map((fila) => (
                      <tr key={fila.clave}>
                        <th scope="row" className="columna-ancla">
                          {fila.nombre}
                          {/* En el eje cliente la clave **es** el nombre: la
                              fuente no entrega NIT ni código de tercero. Pintar
                              la columna repetiría la misma cadena al lado. */}
                          {ejeSinClavePropia(eje) ? null : (
                            <span className="tenue mono"> · {fila.clave}</span>
                          )}
                        </th>
                        <CeldasIndicadoresAgro
                          fila={fila}
                          medida={medida}
                          conMeta={conMeta}
                          sujeto={`el ${opcion.singular}`}
                        />
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Tarjeta>
        </>
      ) : null}
    </div>
  );
}

/**
 * Los mayores del corte, con su ultima venta.
 *
 * Es la misma informacion que las primeras filas de la tabla, en una forma que
 * se lee de un vistazo y sin desplazamiento lateral. No sustituye a la tabla:
 * la tabla trae los indicadores completos y este escalafon responde otra
 * pregunta, la de «quien pesa» y «cuando fue la ultima vez».
 *
 * **No hay pestana de «no compran»**, y es deliberado. Para decir que alguien
 * dejo de comprar hay que emparejar al mismo cliente entre dos periodos, y la
 * API de agropecuaria no entrega identificador de cliente: solo el nombre. El
 * dia que alguien corrija una razon social en SIESA, el sistema diria que uno
 * dejo de comprar y aparecio otro nuevo —una alerta falsa con toda la pinta de
 * un dato—. Queda fuera hasta que la fuente entregue el NIT; esta pedido en
 * `docs/INTEGRACION-SIESA.md` §4.5.
 */
function Escalafon({
  filas,
  medida,
  sujeto,
}: {
  filas: FilaResumenAgro[];
  medida: Medida;
  /** «cliente», «vendedor»: la fecha se rotula segun de quien sea la fila. */
  sujeto: string;
}) {
  if (filas.length === 0) {
    return (
      <Vacio
        titulo="Sin venta en el corte"
        detalle="Nadie registro venta con estos filtros."
      />
    );
  }

  return (
    <ol className="escalafon">
      {filas.map((fila, indice) => (
        <li key={fila.clave} className="escalafon__fila">
          <span className="escalafon__puesto" aria-hidden="true">
            {indice + 1}
          </span>
          <span className="escalafon__nombre">{fila.nombre}</span>
          <span className="escalafon__cifra">
            {porMedida(fila.venta, medida)}
            {fila.ultima_venta ? (
              <span
                className="escalafon__fecha"
                title={`Ultimo dia con venta dentro del corte. No es la ultima ${
                  sujeto === "cliente" ? "compra" : "venta"
                } historica.`}
              >
                {fecha(fila.ultima_venta)}
              </span>
            ) : null}
          </span>
        </li>
      ))}
    </ol>
  );
}

/**
 * El corte en cuatro cifras, encima de la tabla.
 *
 * Cada tarjeta lleva la magnitud en pesos arriba y su equivalente en kilos
 * debajo, porque son dos lecturas del mismo hecho y la gerencia mira las dos: un
 * mes puede cumplir en pesos y no en kilos —o al reves— y eso, que es
 * exactamente lo que hay que ver, se pierde si solo se ensena una.
 *
 * Tres de las cuatro salen vacias mientras nadie capture el presupuesto de
 * agropecuaria. **Es informacion, no un hueco por cargar**: sin meta no hay
 * cumplimiento que calcular ni proyeccion que hacer, y publicar un cero ahi
 * seria afirmar que la meta es cero.
 */
function TarjetasResumen({
  enPesos,
  enKilos,
}: {
  enPesos: IndicadoresAgro | null;
  enKilos: IndicadoresAgro | null;
}) {
  // La venta no necesita la segunda consulta: el contrato ya publica
  // `venta_valor` siempre en pesos y `kilos` siempre en kilos, precisamente
  // para poder ensenar las dos sin volver a preguntar.
  const base = enPesos ?? enKilos;

  return (
    <div className="rejilla rejilla--indicadores">
      <Indicador
        etiqueta="Presupuesto del mes"
        valor={dinero(enPesos?.presupuesto ?? null)}
        nota={
          enKilos?.presupuesto
            ? `${kilos(enKilos.presupuesto)} de meta`
            : "Sin meta en kilos"
        }
      />
      <Indicador
        etiqueta="Ventas acumuladas"
        valor={dinero(base?.venta_valor ?? null)}
        nota={base ? `${kilos(base.kilos)} vendidos` : undefined}
      />
      <Indicador
        etiqueta="Cumplimiento"
        valor={porcentaje(enPesos?.cumplimiento ?? null)}
        nota={
          enKilos?.cumplimiento
            ? `${porcentaje(enKilos.cumplimiento)} en kilos`
            : "Sin cumplimiento en kilos"
        }
      />
      <Indicador
        etiqueta="Proyección al cierre"
        valor={dinero(enPesos?.proyeccion ?? null)}
        nota={
          enPesos?.cumplimiento_proyectado
            ? `${porcentaje(enPesos.cumplimiento_proyectado)} del presupuesto`
            : "Necesita presupuesto para proyectar"
        }
      />
    </div>
  );
}

/** Las columnas que ocupa la tabla, para los `colSpan` de las filas de aviso. */
export function columnasResumenAgro(conMeta: boolean): number {
  return columnasIndicadoresAgro(conMeta) + 1;
}
