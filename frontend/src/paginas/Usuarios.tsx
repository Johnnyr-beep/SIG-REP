/**
 * Administración de cuentas (§ «Usuarios» del contrato).
 *
 * Solo la ve el rol `ADMIN`; los otros cuatro reciben 403 en todo el bloque,
 * `GERENTE` incluido. Esta pantalla reparte accesos, así que sus dos peligros no
 * son de cálculo sino de operación:
 *
 *  · **La clave provisional se muestra una sola vez.** No vuelve en ninguna
 *    respuesta y no se guarda en ningún sitio salvo su hash Argon2id. Aquí vive
 *    en el estado de un componente y muere al cerrarlo: ni `localStorage`, ni la
 *    URL, ni la caché de consultas, ni la de mutaciones —de ahí el `reset()`
 *    inmediato en cuanto el valor pasa al estado local—.
 *  · **Desactivar y restablecer dejan a una persona fuera** hasta que alguien
 *    actúe, y las dos se pulsan desde un botón pequeño dentro de una fila. Las
 *    dos piden confirmación.
 *
 * Los mensajes de error se muestran tal como los envía la API. Un 403
 * `sin_autoadministracion` o un 409 `ultimo_admin_activo` dicen exactamente qué
 * pasó y qué hacer; sustituirlos por un «Ocurrió un error» genérico convierte
 * una explicación en una llamada a soporte.
 */

import { useMemo, useRef, useState } from "react";
import type { FormEvent } from "react";

import type { FiltrosUsuarios } from "@/api/consultas";
import {
  useActualizarUsuario,
  useAuditoriaUsuarios,
  useCambiarEstadoUsuario,
  useCambiarPermisoUsuario,
  useCrearUsuario,
  useFijarPuntosVenta,
  usePuntosVenta,
  useRestablecerClave,
  useUsuarios,
} from "@/api/consultas";

import type {
  EventoAuditoria,
  PuntoVenta,
  ReferenciaSimple,
  Rol,
  UsuarioAdministrado,
} from "@/api/tipos";
import { LARGO_MINIMO_NOMBRE, PATRON_USUARIO } from "@/api/tipos";
import { useAuth } from "@/auth/ContextoAuth";
import {
  AvisoError,
  Campo,
  Confirmacion,
  Dialogo,
  Distintivo,
  Tarjeta,
  Vacio,
} from "@/componentes/comunes";

import { codigoDe, etiquetaDe } from "@/utilidades/dominio";
import { fechaHora, humanizar } from "@/utilidades/formato";

// ── Vocabulario de roles ─────────────────────────────────────────────────────

interface DescripcionRol {
  valor: Rol;
  etiqueta: string;
  alcance: string;
}

const ROLES: DescripcionRol[] = [
  {
    valor: "ADMIN",
    etiqueta: "Administrador",
    alcance:
      "Administra cuentas y entra en todos los reportes. Ve toda la compañía.",
  },
  {
    valor: "GERENTE",
    etiqueta: "Gerente",
    alcance: "Ve todas las cifras de la compañía y cierra períodos.",
  },
  {
    valor: "ANALISTA",
    etiqueta: "Analista",
    alcance: "Parametriza presupuesto y calendario, y ejecuta la ingesta.",
  },
  {
    valor: "JEFE_PDV",
    etiqueta: "Jefe de punto de venta",
    alcance: "Ve únicamente los puntos de venta que se le asignen.",
  },
  {
    valor: "CONSULTA",
    etiqueta: "Consulta",
    alcance: "Solo lectura sobre toda la compañía.",
  },
];

function etiquetaRol(rol: Rol): string {
  return ROLES.find((entrada) => entrada.valor === rol)?.etiqueta ?? rol;
}

/**
 * Roles en los que el alcance por punto de venta cambia algo.
 *
 * `JEFE_PDV` está limitado por definición, y a un `ANALISTA` se le puede acotar
 * la escritura. En `GERENTE`, `ADMIN` y `CONSULTA` la asignación no restringe
 * nada —los tres ven la compañía entera—, así que el control se oculta en el
 * alta y, en el alcance de una cuenta ya creada, se muestra con el aviso de que
 * no tiene efecto: es la única forma de limpiar lo que quedó de un rol anterior.
 */
const ROLES_CON_ALCANCE: Rol[] = ["JEFE_PDV", "ANALISTA"];

const PERMISOS_CONSULTA = [
  ["PERMISO_CONSULTAR_PDV", "Consultar puntos de venta"],
  ["PERMISO_VENTA_DIARIA_ASADERO", "Consultar venta diaria de Asadero"],
  ["PERMISO_CONSULTAR_TABLERO", "Consultar tablero"],
  ["PERMISO_CONSULTAR_CUMPLIMIENTO", "Consultar cumplimiento"],
  ["PERMISO_CONSULTAR_COSTOS", "Consultar costos y margen"],
  ["PERMISO_CONSULTAR_VENTA_DIARIA", "Consultar venta diaria"],
  ["PERMISO_CONSULTAR_CLIENTES", "Consultar clientes y vendedores"],
  ["PERMISO_CONSULTAR_PRESUPUESTO", "Consultar presupuesto"],
  ["PERMISO_CONSULTAR_CALENDARIO", "Consultar calendario"],
  ["PERMISO_CONSULTAR_INGESTA", "Consultar ingesta"],
  ["PERMISO_CONSULTAR_HISTORIA", "Consultar venta del año anterior"],
] as const;

function alcanceAplica(rol: Rol): boolean {
  return ROLES_CON_ALCANCE.includes(rol);
}

// ── Lectura del rastro de auditoría ──────────────────────────────────────────

const ACCIONES: Record<string, string> = {
  CREAR: "Cuenta creada",
  MODIFICAR: "Datos modificados",
  ASIGNAR_ALCANCE: "Alcance asignado",
  ACTIVAR: "Cuenta activada",
  DESACTIVAR: "Cuenta desactivada",
  RESTABLECER_CLAVE: "Clave restablecida",
};

function etiquetaAccion(accion: string): string {
  return ACCIONES[accion] ?? humanizar(accion);
}

/** «Quién» y «sobre quién», vengan con el nombre del contrato o con el del backend. */
function quienDe(evento: EventoAuditoria): string {
  return evento.quien ?? evento.actor ?? "—";
}

function sobreQuienDe(evento: EventoAuditoria): string {
  return evento.sobre_quien ?? evento.usuario ?? "—";
}

/**
 * Detalle legible del cambio.
 *
 * Cuando el backend desglosa el movimiento en campo, valor anterior y valor
 * nuevo, se recompone como «rol: GERENTE → ANALISTA», que es la forma en que se
 * lee una auditoría: qué cambió y de qué a qué.
 */
function detalleDe(evento: EventoAuditoria): string {
  if (evento.detalle) return evento.detalle;
  if (!evento.campo) return "—";
  const anterior = evento.valor_anterior ?? "—";
  const nuevo = evento.valor_nuevo ?? "—";
  return `${evento.campo}: ${anterior} → ${nuevo}`;
}

// ── Alcance: de referencia de catálogo a código C.O. ─────────────────────────

/**
 * Códigos C.O. del alcance de un usuario.
 *
 * El contrato deja abierta la forma de la referencia (texto suelto u objeto) y
 * `PUT /usuarios/{id}/puntos-venta` exige códigos. Lo que llega solo con nombre
 * se resuelve contra el catálogo; lo que no se resuelve se descarta, porque
 * mandarlo tal cual haría que el `PUT` —que reemplaza la lista entera— perdiera
 * silenciosamente ese punto.
 */
function codigosDeAlcance(
  referencias: ReferenciaSimple[] | null | undefined,
  puntosVenta: PuntoVenta[],
): string[] {
  const codigosConocidos = new Set(puntosVenta.map((pdv) => pdv.codigo_co));
  const porNombre = new Map(
    puntosVenta.map((pdv) => [pdv.nombre.toUpperCase(), pdv.codigo_co]),
  );

  const salida: string[] = [];
  for (const referencia of referencias ?? []) {
    const codigo = codigoDe(referencia);
    if (codigo !== null) {
      salida.push(codigo);
      continue;
    }
    const etiqueta = etiquetaDe(referencia);
    if (codigosConocidos.has(etiqueta)) {
      salida.push(etiqueta);
      continue;
    }
    const resuelto = porNombre.get(etiqueta.toUpperCase());
    if (resuelto !== undefined) salida.push(resuelto);
  }
  return salida;
}

/** Nombres legibles del alcance, para pintarlo en la tabla. */
function nombresDeAlcance(
  referencias: ReferenciaSimple[] | null | undefined,
  puntosVenta: PuntoVenta[],
): string[] {
  const porCodigo = new Map(
    puntosVenta.map((pdv) => [pdv.codigo_co, pdv.nombre]),
  );
  return (referencias ?? []).map((referencia) => {
    const codigo = codigoDe(referencia);
    const etiqueta = etiquetaDe(referencia);
    if (codigo !== null) return porCodigo.get(codigo) ?? codigo;
    return porCodigo.get(etiqueta) ?? etiqueta;
  });
}

// ── Selector de puntos de venta ──────────────────────────────────────────────

/**
 * Lista de puntos de venta con casilla.
 *
 * Es un `<fieldset>` y no un `Campo`, que envuelve en `<label>`: una etiqueta
 * alrededor de dieciséis casillas se asocia a la primera y deja a las demás sin
 * nombre accesible.
 */
function SelectorPuntosVenta({
  puntosVenta,
  seleccion,
  onCambiar,
}: {
  puntosVenta: PuntoVenta[];
  seleccion: string[];
  onCambiar: (codigos: string[]) => void;
}) {
  const marcados = new Set(seleccion);

  function alternar(codigo: string) {
    const siguiente = new Set(marcados);
    if (siguiente.has(codigo)) siguiente.delete(codigo);
    else siguiente.add(codigo);
    onCambiar([...siguiente]);
  }

  return (
    <fieldset className="seleccion-pdv">
      <legend className="campo__etiqueta">Puntos de venta</legend>

      <div className="seleccion-pdv__acciones">
        <button
          type="button"
          className="boton boton--sutil boton--pequeno"
          onClick={() => onCambiar(puntosVenta.map((pdv) => pdv.codigo_co))}
        >
          Marcar todos
        </button>
        <button
          type="button"
          className="boton boton--sutil boton--pequeno"
          onClick={() => onCambiar([])}
        >
          Ninguno
        </button>
        <span className="tenue empujar">{seleccion.length} seleccionados</span>
      </div>

      <div className="seleccion-pdv__lista">
        {puntosVenta.map((pdv) => (
          <label key={pdv.codigo_co} className="casilla">
            <input
              type="checkbox"
              checked={marcados.has(pdv.codigo_co)}
              onChange={() => alternar(pdv.codigo_co)}
            />
            <span>
              {pdv.nombre}
              <span className="tenue"> · {pdv.codigo_co}</span>
            </span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}

// ── Clave provisional ────────────────────────────────────────────────────────

interface Secreto {
  usuario: string;
  nombre: string;
  clave: string;
  origen: "alta" | "restablecimiento";
}

/**
 * Cuadro de la clave provisional.
 *
 * Es la pieza más delicada de la pantalla y por eso no se comporta como un
 * aviso cualquiera:
 *
 *  · el diálogo es `persistente` —sin aspa y con Escape desactivado—, de modo
 *    que ni un teclazo reflejo ni un clic fuera lo cierran;
 *  · cerrar exige marcar antes la casilla de que la clave ya está copiada, lo
 *    que convierte el cierre en una afirmación y no en un descarte;
 *  · el valor se puede copiar con un botón y también seleccionar a mano, para
 *    cuando el portapapeles no está disponible (el navegador solo lo concede en
 *    contexto seguro);
 *  · el propio cuadro dice cuál es el remedio si se pierde, que es restablecer
 *    la clave y volver a empezar.
 */
function PanelClaveProvisional({
  secreto,
  onCerrar,
}: {
  secreto: Secreto;
  onCerrar: () => void;
}) {
  const [copiado, setCopiado] = useState<"no" | "si" | "manual">("no");
  const [entregada, setEntregada] = useState(false);
  const referencia = useRef<HTMLElement>(null);

  async function copiar() {
    try {
      await navigator.clipboard.writeText(secreto.clave);
      setCopiado("si");
    } catch {
      // Sin permiso de portapapeles se selecciona el texto para que baste un
      // Ctrl+C. Nunca se deja al administrador sin forma de llevarse la clave.
      const nodo = referencia.current;
      if (nodo) {
        const rango = document.createRange();
        rango.selectNodeContents(nodo);
        const seleccion = window.getSelection();
        seleccion?.removeAllRanges();
        seleccion?.addRange(rango);
      }
      setCopiado("manual");
    }
  }

  return (
    <Dialogo
      abierto
      persistente
      ancho
      titulo={
        secreto.origen === "alta"
          ? "Cuenta creada · clave provisional"
          : "Clave restablecida"
      }
      onCerrar={onCerrar}
      pie={
        <button
          type="button"
          className="boton boton--principal"
          onClick={onCerrar}
          disabled={!entregada}
        >
          Cerrar
        </button>
      }
    >
      <div className="pila">
        <div className="aviso aviso--advertencia" role="alert">
          <div>
            <strong>Esta clave se muestra una sola vez.</strong>
            <p>
              El servidor guarda únicamente su hash: no vuelve a aparecer en
              ninguna pantalla, en ninguna respuesta ni en ningún registro. Si
              la pierde antes de entregarla, el remedio es «Restablecer clave»,
              que genera otra distinta.
            </p>
          </div>
        </div>

        <div className="clave-provisional">
          <p className="clave-provisional__destinatario">
            Para <strong>{secreto.nombre}</strong> · usuario{" "}
            <span className="mono">{secreto.usuario}</span>
          </p>
          <code className="clave-provisional__valor" ref={referencia}>
            {secreto.clave}
          </code>
          <div className="clave-provisional__acciones">
            <button
              type="button"
              className="boton boton--principal"
              onClick={() => void copiar()}
            >
              Copiar la clave
            </button>
            <span className="tenue" role="status" aria-live="polite">
              {copiado === "si"
                ? "Copiada al portapapeles."
                : copiado === "manual"
                  ? "El navegador no dio acceso al portapapeles. La clave quedó seleccionada: cópiela con Ctrl+C."
                  : ""}
            </span>
          </div>
        </div>

        <p className="tenue">
          Al entrar con ella, esta cuenta no podrá abrir ninguna pantalla hasta
          cambiarla por una propia de al menos 12 caracteres.
        </p>

        <label className="casilla">
          <input
            type="checkbox"
            checked={entregada}
            onChange={(evento) => setEntregada(evento.target.checked)}
          />
          <span>
            Ya copié la clave y la voy a entregar. Entiendo que no podré volver
            a verla.
          </span>
        </label>
      </div>
    </Dialogo>
  );
}

// ── Alta ─────────────────────────────────────────────────────────────────────

function DialogoAlta({
  puntosVenta,
  onCerrar,
  onCreada,
}: {
  puntosVenta: PuntoVenta[];
  onCerrar: () => void;
  onCreada: (secreto: Secreto) => void;
}) {
  const crear = useCrearUsuario();
  const [usuario, setUsuario] = useState("");
  const [nombre, setNombre] = useState("");
  const [email, setEmail] = useState("");
  const [rol, setRol] = useState<Rol>("CONSULTA");
  const [alcance, setAlcance] = useState<string[]>([]);

  const aplica = alcanceAplica(rol);
  const descripcion = ROLES.find((entrada) => entrada.valor === rol);

  // El formato lo impone el backend; avisarlo aquí evita rellenar el formulario
  // entero para recibir un 422 que solo dice «string does not match pattern».
  const errorUsuario =
    usuario !== "" && !PATRON_USUARIO.test(usuario)
      ? "Entre 3 y 50 caracteres: minúsculas, dígitos, punto, guion o guion bajo, y sin empezar por signo."
      : undefined;
  const errorNombre =
    nombre !== "" && nombre.trim().length < LARGO_MINIMO_NOMBRE
      ? `El nombre necesita al menos ${LARGO_MINIMO_NOMBRE} caracteres.`
      : undefined;
  const completo =
    usuario !== "" &&
    nombre.trim() !== "" &&
    errorUsuario === undefined &&
    errorNombre === undefined;

  function alEnviar(evento: FormEvent) {
    evento.preventDefault();
    if (!completo) return;

    crear.mutate(
      {
        usuario: usuario.trim(),
        nombre: nombre.trim(),
        email: email.trim() === "" ? null : email.trim(),
        rol,
        // Un alcance que el rol ignora no se manda: dejaría en el registro una
        // asignación que no restringe nada y que confunde a quien la audite.
        puntos_venta: aplica ? alcance : [],
      },
      {
        onSuccess: (creado) => {
          const nuevo: Secreto = {
            usuario: creado.usuario.usuario,
            nombre: creado.usuario.nombre,
            clave: creado.clave_provisional,
            origen: "alta",
          };
          // El valor pasa al estado del componente que lo pinta y desaparece de
          // la caché de mutaciones en el mismo instante.
          crear.reset();
          onCreada(nuevo);
        },
      },
    );
  }

  return (
    <Dialogo
      abierto
      ancho
      titulo="Crear cuenta"
      onCerrar={onCerrar}
      pie={
        <>
          <button
            type="button"
            className="boton"
            onClick={onCerrar}
            disabled={crear.isPending}
          >
            Cancelar
          </button>
          <button
            type="submit"

            form="formulario-alta-usuario"
            className="boton boton--principal"
            disabled={crear.isPending || !completo}
          >
            {crear.isPending ? "Creando…" : "Crear y generar clave"}
          </button>
        </>
      }
    >
      <form id="formulario-alta-usuario" className="pila" onSubmit={alEnviar}>
        <AvisoError error={crear.error} />

        <Campo
          etiqueta="Usuario"
          ayuda="Con lo que inicia sesión. No se puede cambiar después."
          error={errorUsuario}
        >
          <input
            className="campo__control mono"
            value={usuario}
            // Se normaliza a minúsculas mientras se escribe: el backend no las
            // admite en mayúscula y corregirlo después es una fricción gratuita.
            onChange={(evento) =>
              setUsuario(evento.target.value.toLowerCase().trim())
            }
            autoComplete="off"
            required
            maxLength={50}
          />
        </Campo>

        <Campo etiqueta="Nombre" error={errorNombre}>
          <input
            className="campo__control"
            value={nombre}
            onChange={(evento) => setNombre(evento.target.value)}
            required
            minLength={LARGO_MINIMO_NOMBRE}
            maxLength={150}
          />
        </Campo>

        <Campo etiqueta="Correo" ayuda="Opcional.">
          <input
            className="campo__control"
            type="email"
            value={email}
            onChange={(evento) => setEmail(evento.target.value)}
            maxLength={160}
          />
        </Campo>

        <Campo etiqueta="Rol" ayuda={descripcion?.alcance}>
          <select
            className="campo__control"
            value={rol}
            onChange={(evento) => setRol(evento.target.value as Rol)}
          >
            {ROLES.map((entrada) => (
              <option key={entrada.valor} value={entrada.valor}>
                {entrada.etiqueta}
              </option>
            ))}
          </select>
        </Campo>

        {aplica ? (
          <SelectorPuntosVenta
            puntosVenta={puntosVenta}
            seleccion={alcance}
            onCambiar={setAlcance}
          />
        ) : (
          <div className="aviso aviso--info">
            <div>
              El alcance por punto de venta no aplica a {etiquetaRol(rol)}: ve
              toda la compañía. Asignarlo no restringiría nada, así que la
              cuenta se crea sin puntos asociados.
            </div>
          </div>
        )}
      </form>
    </Dialogo>
  );
}

// ── Modificación ─────────────────────────────────────────────────────────────

function DialogoEdicion({
  usuario,
  onCerrar,
}: {
  usuario: UsuarioAdministrado;
  onCerrar: () => void;
}) {
  const actualizar = useActualizarUsuario();
  const [nombre, setNombre] = useState(usuario.nombre);
  const [email, setEmail] = useState(usuario.email ?? "");
  const [rol, setRol] = useState<Rol>(usuario.rol);

  const descripcion = ROLES.find((entrada) => entrada.valor === rol);
  const pierdeAlcance =
    alcanceAplica(usuario.rol) &&
    !alcanceAplica(rol) &&
    usuario.puntos_venta.length > 0;

  function alEnviar(evento: FormEvent) {
    evento.preventDefault();
    actualizar.mutate(
      {
        id: usuario.id,
        datos: {
          nombre: nombre.trim(),
          email: email.trim() === "" ? null : email.trim(),
          rol,
        },
      },
      { onSuccess: onCerrar },
    );
  }

  return (
    <Dialogo
      abierto
      titulo={`Modificar «${usuario.usuario}»`}
      onCerrar={onCerrar}
      pie={
        <>
          <button
            type="button"
            className="boton"
            onClick={onCerrar}
            disabled={actualizar.isPending}
          >
            Cancelar
          </button>
          <button
            type="submit"
            form="formulario-edicion-usuario"

            className="boton boton--principal"
            disabled={
              actualizar.isPending || nombre.trim().length < LARGO_MINIMO_NOMBRE
            }
          >
            {actualizar.isPending ? "Guardando…" : "Guardar"}
          </button>
        </>
      }
    >
      <form
        id="formulario-edicion-usuario"
        className="pila"
        onSubmit={alEnviar}
      >
        <AvisoError error={actualizar.error} />

        <Campo
          etiqueta="Usuario"
          ayuda="El identificador de acceso no se modifica."
        >
          <input
            className="campo__control mono"
            value={usuario.usuario}
            disabled
            readOnly
          />
        </Campo>

        <Campo
          etiqueta="Nombre"
          error={
            nombre !== "" && nombre.trim().length < LARGO_MINIMO_NOMBRE
              ? `El nombre necesita al menos ${LARGO_MINIMO_NOMBRE} caracteres.`
              : undefined
          }
        >
          <input
            className="campo__control"
            value={nombre}
            onChange={(evento) => setNombre(evento.target.value)}
            required
            minLength={LARGO_MINIMO_NOMBRE}
            maxLength={150}
          />
        </Campo>

        <Campo etiqueta="Correo" ayuda="Opcional. Dejarlo vacío lo elimina.">
          <input
            className="campo__control"
            type="email"
            value={email}
            onChange={(evento) => setEmail(evento.target.value)}
            maxLength={160}
          />
        </Campo>

        <Campo etiqueta="Rol" ayuda={descripcion?.alcance}>
          <select
            className="campo__control"
            value={rol}
            onChange={(evento) => setRol(evento.target.value as Rol)}
          >
            {ROLES.map((entrada) => (
              <option key={entrada.valor} value={entrada.valor}>
                {entrada.etiqueta}
              </option>
            ))}
          </select>
        </Campo>

        {pierdeAlcance ? (
          <div className="aviso aviso--advertencia">
            <div>
              Con el rol {etiquetaRol(rol)}, los {usuario.puntos_venta.length}{" "}
              puntos de venta asignados dejan de restringir: la cuenta pasará a
              ver toda la compañía. La asignación no se borra sola; para
              limpiarla, abra «Alcance» y deje la lista vacía.
            </div>
          </div>
        ) : null}
      </form>
    </Dialogo>
  );
}

// ── Alcance ──────────────────────────────────────────────────────────────────

function DialogoAlcance({
  usuario,
  puntosVenta,
  onCerrar,
}: {
  usuario: UsuarioAdministrado;
  puntosVenta: PuntoVenta[];
  onCerrar: () => void;
}) {
  const fijar = useFijarPuntosVenta();
  const [seleccion, setSeleccion] = useState<string[]>(() =>
    codigosDeAlcance(usuario.puntos_venta, puntosVenta),
  );

  const aplica = alcanceAplica(usuario.rol);

  return (
    <Dialogo
      abierto
      ancho
      titulo={`Alcance de «${usuario.usuario}»`}
      onCerrar={onCerrar}
      pie={
        <>
          <button
            type="button"
            className="boton"
            onClick={onCerrar}
            disabled={fijar.isPending}
          >
            Cancelar
          </button>
          <button
            type="button"
            className="boton boton--principal"
            onClick={() =>
              fijar.mutate(
                { id: usuario.id, puntos_venta: seleccion },
                { onSuccess: onCerrar },
              )
            }
            disabled={fijar.isPending}
          >
            {fijar.isPending ? "Guardando…" : "Guardar el alcance"}
          </button>
        </>
      }
    >
      <div className="pila">
        <AvisoError error={fijar.error} />

        {aplica ? null : (
          <div className="aviso aviso--info">
            <div>
              <strong>Este rol no se restringe por punto de venta.</strong>
              <p>
                {etiquetaRol(usuario.rol)} ve toda la compañía, así que lo que
                marque aquí no cambia lo que puede consultar. La lista queda
                editable solo para poder limpiar una asignación heredada de un
                rol anterior.
              </p>
            </div>
          </div>
        )}

        <p className="tenue">
          Se envía el conjunto completo: lo que quede marcado es exactamente lo
          que tendrá la cuenta. Desmarcarlo todo la deja sin ningún punto
          asignado.
        </p>

        <SelectorPuntosVenta
          puntosVenta={puntosVenta}
          seleccion={seleccion}
          onCambiar={setSeleccion}
        />
      </div>
    </Dialogo>
  );
}

// ── Auditoría ────────────────────────────────────────────────────────────────

function Auditoria({
  usuarios,
  habilitado,
}: {
  usuarios: UsuarioAdministrado[];
  habilitado: boolean;
}) {
  const [sobre, setSobre] = useState<number | null>(null);
  const [limite, setLimite] = useState(50);
  const { data, isLoading, error } = useAuditoriaUsuarios(
    sobre,
    limite,
    habilitado,
  );

  return (
    <Tarjeta
      titulo="Auditoría"
      descripcion="Quién hizo qué, sobre quién y cuándo. Toda operación de esta pantalla queda registrada."
      acciones={
        <div className="fila fila--envolvente">
          <label className="filtros__campo">
            <span>Sobre</span>
            <select
              className="campo__control"
              value={sobre === null ? "" : String(sobre)}
              onChange={(evento) =>
                setSobre(
                  evento.target.value === ""
                    ? null
                    : Number(evento.target.value),
                )
              }
            >
              <option value="">Todas las cuentas</option>
              {usuarios.map((cuenta) => (
                <option key={cuenta.id} value={cuenta.id}>
                  {cuenta.usuario}
                </option>
              ))}
            </select>
          </label>
          <label className="filtros__campo">
            <span>Últimos</span>
            <select
              className="campo__control"
              value={String(limite)}
              onChange={(evento) => setLimite(Number(evento.target.value))}
            >
              <option value="50">50</option>
              <option value="100">100</option>
              <option value="200">200</option>
            </select>
          </label>
        </div>
      }
      sinRelleno
    >
      {error ? (
        <div className="tarjeta__cuerpo">
          <AvisoError error={error} />
        </div>
      ) : isLoading ? (
        <p className="cargando">Cargando la auditoría…</p>
      ) : (data ?? []).length === 0 ? (
        <Vacio
          titulo="Sin movimientos"
          detalle="Todavía no hay operaciones registradas."
        />
      ) : (
        <div className="tabla-envoltorio tabla-envoltorio--alta">
          <table className="tabla">
            <thead>
              <tr>
                <th scope="col">Cuándo</th>
                <th scope="col">Quién</th>
                <th scope="col">Sobre quién</th>
                <th scope="col">Acción</th>
                <th scope="col">Detalle</th>
              </tr>
            </thead>
            <tbody>
              {(data ?? []).map((evento, indice) => (
                <tr key={`${evento.cuando}-${evento.accion}-${indice}`}>
                  <td>{fechaHora(evento.cuando)}</td>

                  <td className="mono">{quienDe(evento)}</td>
                  <td className="mono">{sobreQuienDe(evento)}</td>
                  <td>{etiquetaAccion(evento.accion)}</td>
                  <td className="tenue">{detalleDe(evento)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Tarjeta>
  );
}

// ── Pantalla ─────────────────────────────────────────────────────────────────

type Pendiente = {
  tipo: "activar" | "desactivar" | "restablecer";
  usuario: UsuarioAdministrado;
};

export function Usuarios() {
  const { usuario: yo, esAdmin } = useAuth();

  const [filtros, setFiltros] = useState<FiltrosUsuarios>({
    rol: "",
    activo: "",
  });
  const { data: usuarios, isLoading, error } = useUsuarios(filtros, esAdmin);
  const { data: puntosVenta } = usePuntosVenta();

  const [alta, setAlta] = useState(false);
  const [edicion, setEdicion] = useState<UsuarioAdministrado | null>(null);
  const [alcance, setAlcance] = useState<UsuarioAdministrado | null>(null);
  const [pendiente, setPendiente] = useState<Pendiente | null>(null);
  /** Vive aquí y solo aquí: al ponerlo en `null` la clave desaparece del cliente. */
  const [secreto, setSecreto] = useState<Secreto | null>(null);

  const cambiarEstado = useCambiarEstadoUsuario();
  const cambiarPermiso = useCambiarPermisoUsuario();
  const restablecer = useRestablecerClave();

  const catalogo = useMemo(
    () =>
      [...(puntosVenta ?? [])].sort((a, b) =>
        a.nombre.localeCompare(b.nombre, "es"),
      ),
    [puntosVenta],
  );

  const filas = usuarios ?? [];
  const trabajando = cambiarEstado.isPending || restablecer.isPending;

  function cerrarPendiente() {
    setPendiente(null);
    cambiarEstado.reset();
    restablecer.reset();
  }

  function confirmar() {
    if (!pendiente) return;
    const objetivo = pendiente.usuario;

    if (pendiente.tipo === "restablecer") {
      restablecer.mutate(objetivo.id, {
        onSuccess: (respuesta) => {
          const nuevo: Secreto = {
            usuario: respuesta.usuario,
            nombre: objetivo.nombre,
            clave: respuesta.clave_provisional,
            origen: "restablecimiento",
          };
          restablecer.reset();
          setPendiente(null);
          setSecreto(nuevo);
        },
      });
      return;
    }

    cambiarEstado.mutate(
      { id: objetivo.id, activar: pendiente.tipo === "activar" },
      { onSuccess: () => cerrarPendiente() },
    );
  }

  return (
    <div className="pila">
      <section className="filtros" aria-label="Filtros de cuentas">
        <label className="filtros__campo">
          <span>Rol</span>
          <select
            className="campo__control"
            value={filtros.rol ?? ""}
            onChange={(evento) =>
              setFiltros((anteriores) => ({
                ...anteriores,
                rol: evento.target.value as Rol | "",
              }))
            }
          >
            <option value="">Todos</option>
            {ROLES.map((entrada) => (
              <option key={entrada.valor} value={entrada.valor}>
                {entrada.etiqueta}
              </option>
            ))}
          </select>
        </label>

        <label className="filtros__campo">
          <span>Estado</span>
          <select
            className="campo__control"
            value={filtros.activo ?? ""}
            onChange={(evento) =>
              setFiltros((anteriores) => ({
                ...anteriores,
                activo: evento.target.value as "true" | "false" | "",
              }))
            }
          >
            <option value="">Todos</option>
            <option value="true">Activas</option>
            <option value="false">Inactivas</option>
          </select>
        </label>

        <div className="filtros__acciones">
          <button
            type="button"
            className="boton boton--principal boton--pequeno"
            onClick={() => setAlta(true)}
          >
            Crear cuenta
          </button>
        </div>
      </section>

      <AvisoError error={error} />

      <Tarjeta
        titulo="Cuentas"
        descripcion="No hay borrado: la baja de una cuenta es su desactivación, para no destruir el rastro de lo que hizo."
        sinRelleno
      >
        {isLoading ? (
          <p className="cargando">Cargando las cuentas…</p>
        ) : filas.length === 0 ? (
          <Vacio
            titulo="Sin cuentas"
            detalle="Ninguna coincide con los filtros seleccionados."
          />
        ) : (
          <div className="tabla-envoltorio">
            <table className="tabla tabla--anclada">
              <thead>
                <tr>
                  <th scope="col" className="columna-ancla">
                    Usuario
                  </th>
                  <th scope="col">Nombre</th>
                  <th scope="col">Rol</th>
                  <th scope="col">Estado</th>
                  <th scope="col">Clave</th>
                  <th scope="col">Último acceso</th>
                  <th scope="col">Puntos de venta</th>
                  <th scope="col">Permisos de consulta</th>
                  <th scope="col">
                    <span className="solo-lectores">Acciones</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {filas.map((cuenta) => {
                  const propia = yo !== null && cuenta.id === yo.id;
                  // Regla 1 del contrato: nadie se administra a sí mismo. Los
                  // controles de la fila propia van deshabilitados en lugar de
                  // dejar que el administrador pulse y reciba un 403.
                  const motivoPropia = propia
                    ? "Nadie se administra a sí mismo. Para su clave, use «Cambiar mi clave» en el menú de la barra lateral."
                    : undefined;
                  const nombres = nombresDeAlcance(
                    cuenta.puntos_venta,
                    catalogo,
                  );

                  return (
                    <tr key={cuenta.id}>
                      <th scope="row" className="columna-ancla mono">
                        {cuenta.usuario}
                        {propia ? (
                          <span className="columna-ancla__nota">es usted</span>
                        ) : null}
                      </th>
                      <td>
                        {cuenta.nombre}
                        {cuenta.email ? (
                          <span className="columna-ancla__nota">
                            {cuenta.email}
                          </span>
                        ) : null}
                      </td>
                      <td>
                        <Distintivo
                          tono={cuenta.rol === "ADMIN" ? "info" : "neutro"}
                        >
                          {etiquetaRol(cuenta.rol)}
                        </Distintivo>
                      </td>
                      <td>
                        <div className="grupo-botones">
                          <Distintivo tono={cuenta.activo ? "exito" : "neutro"}>
                            {cuenta.activo ? "Activa" : "Inactiva"}
                          </Distintivo>
                          {cuenta.bloqueado ? (
                            <Distintivo tono="peligro">Bloqueada</Distintivo>
                          ) : null}
                        </div>
                      </td>
                      <td>
                        {cuenta.debe_cambiar_password ? (
                          <Distintivo tono="aviso">Provisional</Distintivo>
                        ) : (
                          <span className="tenue">Propia</span>
                        )}
                      </td>
                      <td>{fechaHora(cuenta.ultimo_acceso)}</td>
                      <td className="columna-alcance">
                        {!alcanceAplica(cuenta.rol) ? (
                          <span className="tenue">
                            Toda la compañía
                            {nombres.length > 0
                              ? ` · ${nombres.length} asignados, sin efecto en este rol`
                              : ""}
                          </span>
                        ) : nombres.length === 0 ? (
                          <span className="tenue">Sin puntos asignados</span>
                        ) : (
                          nombres.join(", ")
                        )}
                      </td>
                      <td>
                        <div className="permisos-usuario">
                          {PERMISOS_CONSULTA.map(([codigo, nombre]) => {
                            const asignado = cuenta.permisos.includes(codigo);
                            return (
                              <button
                                key={codigo}
                                type="button"
                                className="boton boton--pequeno boton--sutil"
                                onClick={() =>
                                  cambiarPermiso.mutate({
                                    id: cuenta.id,
                                    codigo,
                                    asignar: !asignado,
                                  })
                                }
                                disabled={propia || cambiarPermiso.isPending}
                                title={nombre}
                              >
                                {asignado ? "✓ " : "＋ "}{nombre}
                              </button>
                            );
                          })}
                        </div>
                      </td>
                      <td>
                        <div className="grupo-botones">
                          <button
                            type="button"
                            className="boton boton--pequeno"
                            onClick={() => setEdicion(cuenta)}
                            disabled={propia}
                            title={motivoPropia}
                          >
                            Modificar
                          </button>
                          <button
                            type="button"
                            className="boton boton--pequeno"
                            onClick={() => setAlcance(cuenta)}
                            disabled={propia}
                            title={motivoPropia}
                          >
                            Alcance
                          </button>
                          <button
                            type="button"
                            className="boton boton--pequeno"
                            onClick={() =>
                              setPendiente({
                                tipo: cuenta.activo ? "desactivar" : "activar",
                                usuario: cuenta,
                              })
                            }
                            disabled={propia}
                            title={motivoPropia}
                          >
                            {cuenta.activo ? "Desactivar" : "Activar"}
                          </button>
                          <button
                            type="button"
                            className="boton boton--pequeno"
                            onClick={() =>
                              setPendiente({
                                tipo: "restablecer",
                                usuario: cuenta,
                              })
                            }
                            disabled={propia}
                            title={motivoPropia}
                          >
                            Restablecer clave
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Tarjeta>

      <Auditoria usuarios={filas} habilitado={esAdmin} />

      {alta ? (
        <DialogoAlta
          puntosVenta={catalogo}
          onCerrar={() => setAlta(false)}
          onCreada={(nuevo) => {
            setAlta(false);
            setSecreto(nuevo);
          }}
        />
      ) : null}

      {edicion ? (
        <DialogoEdicion usuario={edicion} onCerrar={() => setEdicion(null)} />
      ) : null}

      {alcance ? (
        <DialogoAlcance
          usuario={alcance}
          puntosVenta={catalogo}
          onCerrar={() => setAlcance(null)}
        />
      ) : null}

      <Confirmacion
        abierto={pendiente !== null}
        titulo={
          pendiente?.tipo === "restablecer"
            ? "Restablecer la clave"
            : pendiente?.tipo === "activar"
              ? "Activar la cuenta"
              : "Desactivar la cuenta"
        }
        mensaje={
          pendiente === null ? null : pendiente.tipo === "restablecer" ? (
            <p>
              La clave actual de <strong>{pendiente.usuario.nombre}</strong>{" "}
              dejará de servir de inmediato y la persona quedará fuera hasta que
              le entregue la nueva. Se generará una clave provisional que solo
              se muestra una vez.
            </p>
          ) : pendiente.tipo === "activar" ? (
            <p>
              <strong>{pendiente.usuario.nombre}</strong> volverá a poder entrar
              con el rol {etiquetaRol(pendiente.usuario.rol)}.
            </p>
          ) : (
            <p>
              <strong>{pendiente.usuario.nombre}</strong> dejará de poder
              entrar. La cuenta no se borra —su rastro en el historial de
              presupuesto y en las corridas de ingesta se conserva— y se puede
              volver a activar cuando haga falta.
            </p>
          )
        }
        textoConfirmar={
          pendiente?.tipo === "restablecer"
            ? "Restablecer y generar clave"
            : pendiente?.tipo === "activar"
              ? "Activar"
              : "Desactivar"
        }
        peligrosa={pendiente?.tipo !== "activar"}
        trabajando={trabajando}
        error={cambiarEstado.error ?? restablecer.error}
        onConfirmar={confirmar}
        onCancelar={cerrarPendiente}
      />

      {secreto ? (
        <PanelClaveProvisional
          secreto={secreto}
          onCerrar={() => setSecreto(null)}
        />
      ) : null}
    </div>
  );
}
