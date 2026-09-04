/**
 * Filtros comunes a todas las pantallas: período, corte, agrupación y medida.
 *
 * El estado vive en la barra de direcciones, no en un `useState`. Así el gerente
 * puede pegar el enlace de «cumplimiento del grupo 3 en kilos al 9 de agosto» en
 * un correo y quien lo abra ve exactamente lo mismo; recargar la página tampoco
 * pierde la selección.
 */

import {
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
} from "react";
import { useSearchParams } from "react-router-dom";

import type { FiltrosReporte } from "@/api/consultas";
import { useCategorias, useGrupos, usePuntosVenta } from "@/api/consultas";
import { useAuth } from "@/auth/ContextoAuth";
import type { FiltrosAgro } from "@/api/consultasAgro";
import { useCalendarioAgro } from "@/api/consultasAgro";
import type { Medida, PuntoVenta } from "@/api/tipos";
import { MAXIMO_DIAS_VENTA_DIARIA } from "@/api/tipos";
import type { CalendarioAgro } from "@/api/tiposAgro";
import { MEDIDAS, esMedida } from "@/utilidades/dominio";
import {
  diasDelRango,
  fecha as formatearFecha,
  fechaHoy,
  finDeMes,
  periodoActual,
  periodoDeFecha,
  periodoLargo,
  sumarDias,
} from "@/utilidades/formato";

/** Cambios que se aplican a la vez sobre la barra de direcciones. */
export type CambioFiltros = Partial<Record<keyof FiltrosReporte, string>>;

export interface ControlFiltros {
  filtros: FiltrosReporte;
  fijar: (clave: keyof FiltrosReporte, valor: string) => void;
  /**
   * Varios filtros de una sola escritura.
   *
   * El rango obliga a moverlos en bloque: fijar `hasta` arrastra el `periodo` de
   * referencia y, a veces, corrige `desde`. Encadenar tres `fijar` sobre
   * `useSearchParams` es pedir que el segundo lea el estado previo al primero.
   */
  fijarVarios: (cambios: CambioFiltros) => void;
  /** La selección de puntos de venta ya desgranada. Vacía = todos. */
  puntosSeleccionados: string[];
  /**
   * La selección de centros de operación de agropecuaria. Vacía = todos.
   *
   * Convive con la anterior en vez de sustituirla: las dos unidades filtran por
   * cosas distintas —dieciséis puntos de venta frente a dos centros— y el enlace
   * que alguien pegue en un correo tiene que decir cuál de las dos pidió.
   */
  centrosSeleccionados: string[];
}

// ── Selección múltiple de códigos ────────────────────────────────────────────

/**
 * Desgrana `"402, 405,,402"` en `["402", "405"]`.
 *
 * Recorta espacios, descarta vacíos y repetidos y ordena, exactamente como hace
 * el backend —el de carnes con `punto_venta` y el de agropecuaria con `centro`,
 * que aplican la misma regla—. Ordenar no es cosmético: la selección es parte de
 * la clave de caché de TanStack Query, y sin un orden canónico `405,402` y
 * `402,405` serían dos consultas distintas al mismo dato.
 */
export function listaCodigos(valor: string | undefined | null): string[] {
  if (!valor) return [];
  const codigos = valor
    .split(",")
    .map((codigo) => codigo.trim())
    .filter((codigo) => codigo !== "");
  return [...new Set(codigos)].sort((a, b) => a.localeCompare(b, "es"));
}

/** Junta la selección en el formato del contrato. Vacía = cadena vacía = sin filtro. */
export function textoCodigos(codigos: string[]): string {
  return listaCodigos(codigos.join(",")).join(",");
}

// ── Estado en la barra de direcciones ────────────────────────────────────────

export function useFiltros(): ControlFiltros {
  const [parametros, setParametros] = useSearchParams();

  const filtros = useMemo<FiltrosReporte>(() => {
    const medida = parametros.get("medida");
    return {
      periodo: parametros.get("periodo") ?? periodoActual(),
      desde: parametros.get("desde") ?? undefined,
      hasta: parametros.get("hasta") ?? undefined,
      grupo: parametros.get("grupo") ?? undefined,
      punto_venta:
        textoCodigos(listaCodigos(parametros.get("punto_venta"))) || undefined,
      centro: textoCodigos(listaCodigos(parametros.get("centro"))) || undefined,
      categoria: parametros.get("categoria") ?? undefined,
      medida: esMedida(medida) ? medida : "valor",
    };
  }, [parametros]);

  const fijarVarios = useCallback(
    (cambios: CambioFiltros) => {
      setParametros(
        (anteriores) => {
          const siguientes = new URLSearchParams(anteriores);

          for (const [clave, valor] of Object.entries(cambios)) {
            if (valor === undefined || valor === "") siguientes.delete(clave);
            else siguientes.set(clave, valor);
          }

          // Filtrar por puntos de venta concretos y a la vez por su grupo es
          // redundante y produce lecturas confusas si no coinciden.
          if (cambios.punto_venta) siguientes.delete("grupo");
          if (cambios.grupo) siguientes.delete("punto_venta");

          return siguientes;
        },
        { replace: true },
      );
    },
    [setParametros],
  );

  const fijar = useCallback(
    (clave: keyof FiltrosReporte, valor: string) =>
      fijarVarios({ [clave]: valor }),
    [fijarVarios],
  );

  const puntosSeleccionados = useMemo(
    () => listaCodigos(filtros.punto_venta),
    [filtros.punto_venta],
  );

  const centrosSeleccionados = useMemo(
    () => listaCodigos(filtros.centro),
    [filtros.centro],
  );

  return {
    filtros,
    fijar,
    fijarVarios,
    puntosSeleccionados,
    centrosSeleccionados,
  };
}

/**
 * Los filtros que entiende `/agro`, sacados de los de la barra.
 *
 * Es una traducción y no una copia del estado: la barra de direcciones es una
 * sola y `useFiltros` la gobierna entera, pero el router de agropecuaria no
 * conoce `grupo`, `punto_venta` ni `categoria`, y mandárselos sería enviar
 * parámetros que no están en su firma.
 */
export function filtrosAgroDe(filtros: FiltrosReporte): FiltrosAgro {
  return {
    periodo: filtros.periodo,
    desde: filtros.desde,
    hasta: filtros.hasta,
    centro: filtros.centro,
    medida: filtros.medida,
  };
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

// ── Filtro de puntos de venta ────────────────────────────────────────────────

/**
 * Selección múltiple de puntos de venta.
 *
 * ── Por qué una lista de casillas y no un `<select multiple>` ───────────────
 *
 * Son dieciséis puntos. Un `<select multiple>` los muestra en una caja de tres o
 * cuatro líneas, exige Ctrl+clic para añadir uno sin perder el anterior y borra
 * toda la selección con un clic despistado. En la práctica no se usa sin
 * arrastrar el ratón, y arrastrar dentro de una lista con desplazamiento es peor.
 * Una casilla por punto no tiene ese modo oculto: se marca lo que se quiere, se
 * desmarca lo que no, cada opción es un objetivo de clic completo y el teclado la
 * recorre con Tab y la conmuta con la barra espaciadora, sin ninguna combinación
 * que haya que conocer de antemano.
 *
 * Van dentro de un panel desplegable —y no siempre a la vista— porque dieciséis
 * casillas ocuparían más alto que el resto de la barra junta en un portátil de
 * trece pulgadas. El disparador dice de un vistazo cuántos hay elegidos y cuáles.
 *
 * ── La ausencia de filtro es «todos», y no es la selección de los dieciséis ──
 *
 * `?punto_venta=` equivale a no filtrar, así que desmarcarlos todos no puede
 * significar «no muestres nada»: la selección vacía vuelve al estado «Todos» y el
 * panel lo dice con todas las letras, en lugar de dejar al usuario ante una tabla
 * en blanco preguntándose qué rompió.
 */
/** Un miembro elegible del selector, ya despojado de su catálogo de origen. */
export interface OpcionSeleccion {
  /** Lo que viaja al backend: código C.O. en carnes, código de centro en agro. */
  clave: string;
  nombre: string;
  /** Apostilla tras el nombre. En carnes marca los puntos sin presupuesto. */
  nota?: string;
}

/**
 * El selector, escrito una vez para las dos unidades.
 *
 * Carnes filtra por dieciséis puntos de venta y agropecuaria por dos centros de
 * operación, pero es **el mismo control con la misma regla**: la selección vacía
 * significa «todos», marcar todos da el mismo resultado que no filtrar, y un
 * código heredado de un enlace viejo sigue contando aunque ya no esté en el
 * catálogo. Copiar el componente para la segunda unidad habría sido copiar
 * también esas tres reglas, que es exactamente por donde empiezan a divergir.
 */
function SelectorMultiple({
  etiqueta,
  plural,
  singular,
  opciones,
  seleccion,
  onCambiar,
  vacio,
}: {
  /** Nombre del campo, en la barra: «Punto de venta», «Centro». */
  etiqueta: string;
  /** «puntos de venta», «centros de operación»: para los textos de resumen. */
  plural: string;
  /** «un punto», «un centro»: para la nota cuando hay uno solo elegido. */
  singular: string;
  opciones: OpcionSeleccion[];
  seleccion: string[];
  onCambiar: (codigos: string[]) => void;
  /**
   * Qué decir cuando **no hay ninguna opción**.
   *
   * Sin esto el desplegable se abría vacío, con un «0 de 0» y la nota de
   * siempre —«sin ninguno marcado, el reporte incluye todos»—, que es cierta y
   * no sirve de nada: quien lo ve por primera vez no tiene forma de saber si el
   * catálogo está vacío o si algo se rompió. Y lo natural es pensar lo segundo.
   *
   * El motivo cambia según el filtro —los centros de agropecuaria nacen de la
   * ingesta, los puntos de venta vienen del catálogo—, así que lo aporta quien
   * lo usa en lugar de intentar adivinarlo aquí.
   */
  vacio?: string;
}) {
  const [abierto, setAbierto] = useState(false);
  const contenedor = useRef<HTMLDivElement>(null);
  const disparador = useRef<HTMLButtonElement>(null);

  const base = useId();
  const idEtiqueta = `${base}-etiqueta`;
  const idBoton = `${base}-boton`;
  const idPanel = `${base}-panel`;

  const marcados = useMemo(() => new Set(seleccion), [seleccion]);
  const total = opciones.length;
  const elegidos = opciones.filter((opcion) => marcados.has(opcion.clave));
  // Un código que quedó en el enlace y ya no está en el catálogo sigue contando:
  // el reporte lo recibe igual, así que el resumen no puede dar a entender lo
  // contrario. Simplemente no casará con ninguna fila, como dice el contrato.
  const huerfanos = seleccion.filter(
    (codigo) => !opciones.some((opcion) => opcion.clave === codigo),
  );

  const nombres = [...elegidos.map((opcion) => opcion.nombre), ...huerfanos];
  const resumen = seleccion.length === 0 ? "Todos" : nombres.join(", ");
  const lectura =
    seleccion.length === 0
      ? total === 0
        ? "Sin datos"
        : `Todos los ${plural}`
      : `${seleccion.length} de ${total} ${plural}: ${nombres.join(", ")}`;

  function alternar(codigo: string) {
    const siguiente = new Set(marcados);
    if (siguiente.has(codigo)) siguiente.delete(codigo);
    else siguiente.add(codigo);
    onCambiar([...siguiente]);
  }

  /**
   * Cierre por Escape y por pulsación fuera.
   *
   * Escape devuelve el foco al disparador —si no, el teclado se queda huérfano en
   * mitad del documento—; la pulsación fuera no lo toca, porque el usuario ya está
   * señalando dónde quiere seguir.
   */
  useEffect(() => {
    if (!abierto) return;

    function alPulsarFuera(evento: PointerEvent) {
      const nodo = evento.target;
      if (nodo instanceof Node && !contenedor.current?.contains(nodo))
        setAbierto(false);
    }

    function alTeclear(evento: KeyboardEvent) {
      if (evento.key !== "Escape") return;
      evento.stopPropagation();
      setAbierto(false);
      disparador.current?.focus();
    }

    document.addEventListener("pointerdown", alPulsarFuera);
    document.addEventListener("keydown", alTeclear);
    return () => {
      document.removeEventListener("pointerdown", alPulsarFuera);
      document.removeEventListener("keydown", alTeclear);
    };
  }, [abierto]);

  return (
    <div
      className="filtros__campo selector-pdv"
      ref={contenedor}
      // Tabular más allá de la última casilla cierra el panel: el foco ya salió de
      // él y dejarlo abierto tapa los filtros de al lado.
      onBlur={(evento) => {
        const siguiente = evento.relatedTarget;
        if (
          siguiente instanceof Node &&
          evento.currentTarget.contains(siguiente)
        )
          return;
        setAbierto(false);
      }}
    >
      <span id={idEtiqueta}>{etiqueta}</span>

      <button
        type="button"
        id={idBoton}
        ref={disparador}
        className="campo__control selector-pdv__disparador"
        aria-labelledby={`${idEtiqueta} ${idBoton}`}
        aria-expanded={abierto}
        aria-controls={abierto ? idPanel : undefined}
        onClick={() => setAbierto((anterior) => !anterior)}
      >
        {seleccion.length > 0 ? (
          <span className="selector-pdv__conteo" aria-hidden="true">
            {seleccion.length}
          </span>
        ) : null}
        <span
          className="selector-pdv__resumen"
          aria-hidden="true"
          title={resumen}
        >
          {resumen}
        </span>
        <span className="solo-lectores">{lectura}</span>
        <span className="selector-pdv__flecha" aria-hidden="true">
          ▾
        </span>
      </button>

      {abierto ? (
        <div className="selector-pdv__panel" id={idPanel}>
          <div className="selector-pdv__acciones">
            <button
              type="button"
              className="boton boton--sutil boton--pequeno"
              onClick={() => {
                onCambiar(opciones.map((opcion) => opcion.clave));
                // El botón queda deshabilitado tras el clic y el navegador
                // retiraría el foco al documento, lo que cerraría el panel:
                // se devuelve al disparador antes de que eso ocurra.
                disparador.current?.focus();
              }}
              disabled={total === 0 || elegidos.length === total}
            >
              Marcar todos
            </button>
            <button
              type="button"
              className="boton boton--sutil boton--pequeno"
              onClick={() => {
                onCambiar([]);
                disparador.current?.focus();
              }}
              disabled={seleccion.length === 0}
              title={`Vuelve al estado «Todos»: sin filtro, el reporte incluye todos los ${plural}.`}
            >
              Quitar filtro
            </button>
            <span className="tenue empujar">
              {seleccion.length} de {total}
            </span>
          </div>

          <fieldset className="selector-pdv__lista">
            <legend className="solo-lectores">
              {etiqueta}: qué se incluye en el reporte
            </legend>
            {total === 0 ? (
              <p className="selector-pdv__vacio tenue">
                {vacio ?? `Todavía no hay ${plural} que mostrar.`}
              </p>
            ) : null}
            {opciones.map((opcion) => (
              <label key={opcion.clave} className="casilla">
                <input
                  type="checkbox"
                  checked={marcados.has(opcion.clave)}
                  onChange={() => alternar(opcion.clave)}
                />
                <span>
                  {opcion.nombre}
                  <span className="tenue"> · {opcion.clave}</span>
                  {opcion.nota ? (
                    <span className="tenue"> · {opcion.nota}</span>
                  ) : null}
                </span>
              </label>
            ))}
          </fieldset>

          <p className="selector-pdv__nota" role="status">
            {total === 0
              ? "El filtro se activa solo cuando hay algo que filtrar."
              : seleccion.length === 0
                ? `Sin ninguno marcado, el reporte incluye todos los ${plural}.`
                : elegidos.length === total && huerfanos.length === 0
                  ? `Están marcados los ${total}: el resultado es el mismo que sin filtro.`
                  : `El reporte se limita a ${
                      seleccion.length === 1
                        ? singular
                        : `${seleccion.length} ${plural}`
                    }.`}
          </p>
        </div>
      ) : null}
    </div>
  );
}

/** El selector de carnes: dieciséis puntos de venta del catálogo de §3. */
function FiltroPuntosVenta({
  puntos,
  seleccion,
  onCambiar,
}: {
  puntos: PuntoVenta[];
  seleccion: string[];
  onCambiar: (codigos: string[]) => void;
}) {
  const opciones = useMemo<OpcionSeleccion[]>(
    () =>
      puntos.map((punto) => ({
        clave: punto.codigo_co,
        nombre: punto.nombre,
        // 432 EVENTOS vende sin estar presupuestado; conviene verlo al elegir.
        nota: punto.presupuestado ? undefined : "sin presupuesto",
      })),
    [puntos],
  );

  return (
    <SelectorMultiple
      etiqueta="Punto de venta"
      plural="puntos de venta"
      singular="un punto de venta"
      opciones={opciones}
      seleccion={seleccion}
      onCambiar={onCambiar}
    />
  );
}

/**
 * El selector de agropecuaria: los dos centros de operación.
 *
 * Las opciones salen del **calendario** del período y no de un catálogo de
 * dimensiones, porque ese catálogo no está expuesto: `MiembroDimensionSalida`
 * existe en el esquema del backend pero ningún endpoint lo devuelve. El
 * calendario es la única respuesta que publica código y nombre de los dos
 * centros juntos, y además es exactamente la lista que tiene sentido ofrecer:
 * un centro sin calendario no puede medirse contra nada.
 */
function FiltroCentros({
  centros,
  seleccion,
  onCambiar,
}: {
  centros: CalendarioAgro[];
  seleccion: string[];
  onCambiar: (codigos: string[]) => void;
}) {
  const opciones = useMemo<OpcionSeleccion[]>(
    () =>
      centros.map((centro) => ({
        clave: centro.centro,
        nombre: centro.nombre,
      })),
    [centros],
  );

  return (
    <SelectorMultiple
      etiqueta="Centro de operación"
      plural="centros de operación"
      singular="un centro de operación"
      opciones={opciones}
      seleccion={seleccion}
      onCambiar={onCambiar}
      vacio={
        "Los centros de operación aparecen con la primera ingesta: no son un " +
        "catálogo que se dé de alta, salen de los datos que entrega la API de " +
        "la compañía. Cargue un rango en Parametrización → Ingesta y vuelva aquí."
      }
    />
  );
}

// ── Filtro de rango de fechas ────────────────────────────────────────────────

/**
 * Días que abarca el rango que se va a pedir, contando los dos extremos.
 *
 * Sin `hasta` el rango se cierra hoy, tal como hace el backend; así el aviso del
 * tope aparece antes de enviar y no después de un 422.
 */
export function diasDelRangoPedido(
  desde?: string,
  hasta?: string,
): number | null {
  if (!desde) return null;
  return diasDelRango(desde, hasta && hasta !== "" ? hasta : fechaHoy());
}

/**
 * Corte por rango, con la validación puesta en el propio selector.
 *
 * Los dos rechazos del contrato —rango invertido y más de 92 días— son errores
 * que el usuario no debería poder cometer, así que aquí no se pueden: cada campo
 * lleva `min` y `max` derivados del otro, con lo que el calendario nativo apaga
 * los días fuera de rango, y además todo cambio arrastra al otro extremo cuando
 * hace falta. Un rango invertido no llega a existir ni un instante.
 *
 * El `periodo` deja de editarse a mano mientras haya `desde`: el contrato manda
 * enviar como período de referencia el mes al que pertenece `hasta`, y dos
 * controles que dicen cosas distintas sobre lo mismo son una trampa.
 */
function FiltroRango({
  periodo,
  desde,
  hasta,
  onCambiar,
}: {
  periodo: string;
  desde?: string;
  hasta?: string;
  onCambiar: (cambios: CambioFiltros) => void;
}) {
  const hoy = fechaHoy();
  const ultimo = MAXIMO_DIAS_VENTA_DIARIA - 1;
  const finPeriodo = finDeMes(periodo);

  /**
   * Dónde cierra el reporte si nadie ha fijado `hasta`.
   *
   * Con rango, el contrato lo cierra hoy. Sin rango manda el período, y en uno ya
   * pasado el corte natural es su último día, no hoy. La distinción importa
   * porque de aquí sale el `min` de «desde»: tomando «hoy» a secas, abrir un
   * rango dentro de un período de marzo caería fuera del tope de 92 días y el
   * calendario apagaría esos días sin explicar por qué.
   */
  const cierrePredeterminado = desde
    ? hoy
    : finPeriodo !== null && finPeriodo < hoy
      ? finPeriodo
      : hoy;
  const hastaEfectivo = hasta && hasta !== "" ? hasta : cierrePredeterminado;

  /** El período de referencia siempre lo fija el mes de `hasta`. */
  function conPeriodo(
    cambios: CambioFiltros,
    hastaNuevo: string,
  ): CambioFiltros {
    return {
      ...cambios,
      periodo: periodoDeFecha(hastaNuevo) ?? periodoDeFecha(hoy) ?? "",
    };
  }

  function alCambiarDesde(valor: string) {
    if (valor === "") {
      // Volver al modo de siempre: el mes completo hasta el corte. El `periodo`
      // recupera su papel de control editable y no se toca aquí.
      onCambiar({ desde: "" });
      return;
    }

    let destino = hastaEfectivo;
    if (destino < valor) destino = valor;
    const tope = sumarDias(valor, ultimo);
    if (destino > tope) destino = tope;

    onCambiar(conPeriodo({ desde: valor, hasta: destino }, destino));
  }

  function alCambiarHasta(valor: string) {
    // Sin `desde` manda el período y `hasta` es solo el corte dentro de él: no se
    // toca el período, que es lo de siempre. Con `desde`, en cambio, el período de
    // referencia tiene que seguir al mes de `hasta`, como pide el contrato.
    if (!desde) {
      onCambiar({ hasta: valor });
      return;
    }

    if (valor === "") {
      // Sin `hasta` el rango se cierra hoy, así que el período lo marca hoy.
      onCambiar(conPeriodo({ hasta: "" }, hoy));
      return;
    }

    let inicio = desde;
    if (inicio > valor) inicio = valor;
    const piso = sumarDias(valor, -ultimo);
    if (inicio < piso) inicio = piso;

    onCambiar(conPeriodo({ hasta: valor, desde: inicio }, valor));
  }

  const dias = diasDelRangoPedido(desde, hasta);

  return (
    <>
      <label className="filtros__campo">
        <span>Desde</span>
        <input
          className="campo__control"
          type="date"
          value={desde ?? ""}
          min={sumarDias(hastaEfectivo, -ultimo)}
          max={hastaEfectivo}
          onChange={(evento) => alCambiarDesde(evento.target.value)}
          title="Primer día del rango. Vacío = el mes completo del período hasta el corte."
        />
      </label>

      <label className="filtros__campo">
        <span>Hasta</span>
        <input
          className="campo__control"
          type="date"
          value={hasta ?? ""}
          // Con rango, los límites son «desde» y el tope de 92 días. Sin rango es
          // el corte de siempre, y entonces no tiene sentido fuera del período.
          min={desde || `${periodo}-01`}
          max={desde ? sumarDias(desde, ultimo) : (finPeriodo ?? undefined)}
          onChange={(evento) => alCambiarHasta(evento.target.value)}
          title={
            desde
              ? "Último día del rango. Vacío = hoy."
              : "Fecha hasta la que se acumula la venta, dentro del período. Vacío = hoy."
          }
        />
      </label>

      <p className="filtros__nota" role="status">
        {desde ? (
          <>
            <strong>
              {dias === null ? "—" : dias === 1 ? "1 día" : `${dias} días`}
            </strong>{" "}
            · {formatearFecha(desde)} a {formatearFecha(hastaEfectivo)}
            {hasta ? "" : " (hoy)"} · el máximo del reporte son{" "}
            {MAXIMO_DIAS_VENTA_DIARIA} días. Un rango que cruza de mes compara
            cada día contra el presupuesto diario de su propio mes.
          </>
        ) : (
          <>
            Sin fecha «desde» el reporte muestra el mes completo del período
            hasta el corte, como siempre. Indique un «desde» para pedir un
            rango, que puede cruzar de mes.
          </>
        )}
      </p>
    </>
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
    /** Sustituye el corte de una sola fecha por el rango `desde`/`hasta`. */
    rango?: boolean;
    grupo?: boolean;
    puntoVenta?: boolean;
    categoria?: boolean;
    medida?: boolean;
  };
  acciones?: React.ReactNode;
}) {
  const { filtros, fijar, fijarVarios, puntosSeleccionados } = control;
  const { tienePermiso, usuario } = useAuth();
  const visible = {
    corte: true,
    rango: false,
    grupo: true,
    puntoVenta: true,
    categoria: false,
    medida: true,
    ...mostrar,
  };

  const { data: grupos } = useGrupos();
  const { data: puntos } = usePuntosVenta();
  const { data: categorias } = useCategorias();

  const permisosGranulares =
    usuario?.rol === "CONSULTA" && usuario.permisos.length > 0;
  const puedeFiltrar = (permiso: string) =>
    !permisosGranulares || tienePermiso(permiso);

  /** Con rango activo el período es una consecuencia de `hasta`, no una elección. */
  const periodoDerivado = visible.rango && Boolean(filtros.desde);

  return (
    <section className="filtros" aria-label="Filtros del reporte">
      {puedeFiltrar("PERMISO_FILTRAR_PERIODO") && periodoDerivado ? (
        <div className="filtros__campo">
          <span>Período de referencia</span>
          <p
            className="campo__control filtros__derivado"
            title="El contrato pide enviar como período el mes al que pertenece «hasta»; de él salen los días hábiles del pie de cálculo."
          >
            {periodoLargo(filtros.periodo)}
          </p>
        </div>
      ) : puedeFiltrar("PERMISO_FILTRAR_PERIODO") ? (
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
      ) : null}

      {visible.rango && puedeFiltrar("PERMISO_FILTRAR_PERIODO") ? (
        <FiltroRango
          periodo={filtros.periodo}
          desde={filtros.desde}
          hasta={filtros.hasta}
          onCambiar={fijarVarios}
        />
      ) : visible.corte && puedeFiltrar("PERMISO_FILTRAR_PERIODO") ? (
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

      {visible.grupo && puedeFiltrar("PERMISO_FILTRAR_GRUPO") ? (
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

      {visible.puntoVenta && puedeFiltrar("PERMISO_FILTRAR_PDV") ? (
        <FiltroPuntosVenta
          puntos={puntos ?? []}
          seleccion={puntosSeleccionados}
          onCambiar={(codigos) => fijar("punto_venta", textoCodigos(codigos))}
        />
      ) : null}

      {visible.categoria && puedeFiltrar("PERMISO_FILTRAR_CATEGORIA") ? (
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

      {visible.medida && puedeFiltrar("PERMISO_FILTRAR_MEDIDA") ? (
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

// ── Barra de filtros de agropecuaria ─────────────────────────────────────────

/**
 * La barra de la unidad Agropecuaria.
 *
 * Es una barra distinta y no un `mostrar` más de `BarraFiltros` por una razón
 * concreta: aquella pide los tres catálogos de carnes —grupos, puntos de venta y
 * categorías— nada más montarse, y en una pantalla de agropecuaria esas tres
 * consultas no solo sobran, es que traerían el catálogo de otro negocio. Lo que
 * sí comparten es todo lo que importa: el estado en la barra de direcciones, el
 * selector de rango con sus dos guardas y el conmutador de medida.
 */
export function BarraFiltrosAgro({
  control,
  mostrar,
  acciones,
}: {
  control: ControlFiltros;
  mostrar?: {
    corte?: boolean;
    /** Sustituye el corte de una sola fecha por el rango `desde`/`hasta`. */
    rango?: boolean;
    centro?: boolean;
    medida?: boolean;
  };
  acciones?: React.ReactNode;
}) {
  const { filtros, fijar, fijarVarios, centrosSeleccionados } = control;
  const { tienePermiso, usuario } = useAuth();
  const permisosGranulares = usuario?.rol === "CONSULTA" && usuario.permisos.some((codigo) => codigo.startsWith("PERMISO_AGRO_"));
  const puedeFiltrar = (permiso: string) => !permisosGranulares || tienePermiso(permiso);
  const visible = {
    corte: true,
    rango: false,
    centro: true,
    medida: true,
    ...mostrar,
  };

  // El calendario del período es de donde salen los centros: ver `FiltroCentros`.
  const { data: centros } = useCalendarioAgro(filtros.periodo);

  /** Con rango activo el período es una consecuencia de `hasta`, no una elección. */
  const periodoDerivado = visible.rango && Boolean(filtros.desde);

  return (
    <section className="filtros" aria-label="Filtros del reporte">
      {puedeFiltrar("PERMISO_AGRO_FILTRAR_PERIODO") && periodoDerivado ? (
        <div className="filtros__campo">
          <span>Período de referencia</span>
          <p
            className="campo__control filtros__derivado"
            title="El período que se envía es el mes al que pertenece «hasta»; de él salen los días hábiles del pie de cálculo."
          >
            {periodoLargo(filtros.periodo)}
          </p>
        </div>
      ) : puedeFiltrar("PERMISO_AGRO_FILTRAR_PERIODO") ? (
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
      ) : null}

      {visible.rango && puedeFiltrar("PERMISO_AGRO_FILTRAR_PERIODO") ? (
        <FiltroRango
          periodo={filtros.periodo}
          desde={filtros.desde}
          hasta={filtros.hasta}
          onCambiar={fijarVarios}
        />
      ) : visible.corte && puedeFiltrar("PERMISO_AGRO_FILTRAR_PERIODO") ? (
        <label className="filtros__campo">
          <span>Corte</span>
          <input
            className="campo__control"
            type="date"
            value={filtros.hasta ?? ""}
            onChange={(evento) => fijar("hasta", evento.target.value)}
            title="Fecha hasta la que se acumula la venta. Vacío = hoy."
          />
        </label>
      ) : null}

      {visible.centro && puedeFiltrar("PERMISO_AGRO_FILTRAR_CENTRO") ? (
        <FiltroCentros
          centros={centros ?? []}
          seleccion={centrosSeleccionados}
          onCambiar={(codigos) => fijar("centro", textoCodigos(codigos))}
        />
      ) : null}

      {visible.medida && puedeFiltrar("PERMISO_AGRO_FILTRAR_MEDIDA") ? (
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
