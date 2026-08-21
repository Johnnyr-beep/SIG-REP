/** Marco de la aplicación: barra lateral, cabecera y área de contenido. */

import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";

import { MODO_EJEMPLOS } from "@/api/cliente";
import type { Rol } from "@/api/tipos";
import { useAuth } from "@/auth/ContextoAuth";
import { Dialogo } from "@/componentes/comunes";
import { useFiltros } from "@/componentes/filtros";
import { useMarcaElegida } from "@/marca/ContextoMarca";
import { anchoLogo } from "@/marca/marcas";
import type { ClaveMarca } from "@/marca/marcas";
import { FormularioCambioClave } from "@/paginas/CambioClave";
import { fechaLarga, periodoLargo } from "@/utilidades/formato";

/** El mismo que fija `.marca__logo` en la hoja. */
const ALTO_LOGO = 40;

interface ItemNav {
  ruta: string;
  etiqueta: string;
  icono: string;
  /** Roles que ven la entrada; ausente significa «todos los autenticados». */
  roles?: Rol[];
}

interface GrupoNav {
  titulo: string;
  items: ItemNav[];
}

/**
 * Las pantallas de carnes: §6 de la especificación.
 *
 * Hay un menú por unidad y no uno solo con todo dentro, porque las dos unidades
 * no miden lo mismo. Carnes agrupa por punto de venta y categoría; agropecuaria
 * por centro de operación, especie, tipo comercial y vendedor. Un menú mezclado
 * ofrecería a un gerente de carnes una pantalla de especies que su base no tiene
 * y al revés, y la primera vez que alguien la abriera vería una tabla vacía sin
 * saber si es que no hay venta o es que esa pantalla no era la suya.
 */
const MENU_CARNES: GrupoNav[] = [
  {
    titulo: "Gerencia",
    items: [
      { ruta: "/", etiqueta: "Tablero", icono: "◱" },
      { ruta: "/cumplimiento", etiqueta: "Cumplimiento por PDV", icono: "▤" },
      { ruta: "/venta-diaria", etiqueta: "Venta diaria", icono: "▦" },
      { ruta: "/clientes", etiqueta: "Clientes y vendedores", icono: "◇" },
    ],
  },
  {
    titulo: "Parametrización",
    items: [
      // Los mismos roles que exige el contrato en `PUT /presupuesto`: si la
      // entrada se viera con un rol que el servidor rechaza, el usuario llegaría
      // a un 403 sin entender por qué.

      {
        ruta: "/presupuesto",
        etiqueta: "Presupuesto",
        icono: "≡",
        roles: ["ADMIN", "GERENTE", "ANALISTA"],
      },
      { ruta: "/calendario", etiqueta: "Días hábiles", icono: "◷" },
      { ruta: "/ingesta", etiqueta: "Ingesta", icono: "⇄" },
    ],
  },
  {
    titulo: "Administración",
    items: [
      // El contrato es explícito: los otros cuatro roles reciben 403 en todo el
      // bloque `/usuarios`, `GERENTE` incluido. La entrada no se les muestra.
      { ruta: "/usuarios", etiqueta: "Usuarios", icono: "◉", roles: ["ADMIN"] },
    ],
  },
];

/** Las de agropecuaria, sobre `/agro`. Mismos roles que exige `api/v1/agro.py`. */
const MENU_AGRO: GrupoNav[] = [
  {
    titulo: "Gerencia",
    items: [
      { ruta: "/agro", etiqueta: "Venta por eje", icono: "◱" },
      { ruta: "/agro/cruce", etiqueta: "Vendedor y cliente", icono: "◇" },
      { ruta: "/agro/venta-diaria", etiqueta: "Venta diaria", icono: "▦" },
    ],
  },
  {
    titulo: "Parametrización",
    items: [
      {
        ruta: "/agro/presupuesto",
        etiqueta: "Presupuesto",
        icono: "≡",
        roles: ["ADMIN", "GERENTE", "ANALISTA"],
      },
      { ruta: "/agro/calendario", etiqueta: "Días hábiles", icono: "◷" },
      { ruta: "/agro/ingesta", etiqueta: "Ingesta", icono: "⇄" },
    ],
  },
  {
    titulo: "Administración",
    items: [
      { ruta: "/usuarios", etiqueta: "Usuarios", icono: "◉", roles: ["ADMIN"] },
    ],
  },
];

/**
 * El menú que corresponde a la marca elegida.
 *
 * `carnes-frias` todavía no tiene módulo; si alguien llegara con esa marca
 * guardada en `localStorage`, ve el de carnes en vez de una barra vacía. El
 * selector ya no deja elegirla —se lo impide `unidades` de la sonda—, así que
 * esto es el cinturón, no la vía normal.
 */
function menuDe(marca: ClaveMarca): GrupoNav[] {
  return marca === "agropecuaria" ? MENU_AGRO : MENU_CARNES;
}

const TITULOS: Record<string, string> = {
  "/agro": "Venta de agropecuaria por eje",
  "/agro/cruce": "Vendedor, cliente y producto",
  "/agro/venta-diaria": "Venta diaria por centro de operación",
  "/agro/presupuesto": "Presupuesto de agropecuaria",
  "/agro/calendario": "Días hábiles por centro de operación",
  "/agro/ingesta": "Ingesta de agropecuaria",
  "/": "Tablero gerencial",
  "/cumplimiento": "Cumplimiento por punto de venta",
  "/venta-diaria": "Venta diaria",
  "/clientes": "Clientes y vendedores",
  "/presupuesto": "Parametrización de presupuesto",

  "/calendario": "Calendario de días hábiles",
  "/ingesta": "Ingesta desde SIESA",
  "/usuarios": "Administración de usuarios",
};

type Tema = "sistema" | "claro" | "oscuro";

function useTema(): [Tema, (tema: Tema) => void] {
  const [tema, setTema] = useState<Tema>(
    () => (localStorage.getItem("sigrep_tema") as Tema | null) ?? "sistema",
  );

  useEffect(() => {
    const raiz = document.documentElement;
    if (tema === "sistema") raiz.removeAttribute("data-tema");
    else raiz.setAttribute("data-tema", tema);
    localStorage.setItem("sigrep_tema", tema);
  }, [tema]);

  return [tema, setTema];
}

function SelectorTema() {
  const [tema, setTema] = useTema();
  const siguiente: Record<Tema, Tema> = {
    sistema: "claro",
    claro: "oscuro",
    oscuro: "sistema",
  };
  const iconos: Record<Tema, string> = {
    sistema: "◐",
    claro: "☀",
    oscuro: "☾",
  };

  return (
    <button
      type="button"
      className="boton boton--sutil boton--pequeno"
      onClick={() => setTema(siguiente[tema])}
      aria-label={`Cambiar tema. Actual: ${tema}`}
      title={`Tema: ${tema}. Pulse para cambiar.`}
    >
      {iconos[tema]}
    </button>
  );
}

/**
 * Menú de usuario del pie de la barra lateral.
 *
 * Desde aquí sale el cambio de clave voluntario: el mismo formulario que impone
 * la pantalla obligatoria, disponible siempre para quien quiera cambiarla sin
 * que se lo exijan. Se apoya en `<details>`, como el resto de desplegables de
 * la interfaz, para no reimplementar el foco ni el cierre con Escape.
 */

function MenuUsuario() {
  const { usuario } = useAuth();
  const [menuAbierto, setMenuAbierto] = useState(false);
  const [dialogoAbierto, setDialogoAbierto] = useState(false);
  const [cambiada, setCambiada] = useState(false);

  if (!usuario) return null;

  function cerrarDialogo() {
    setDialogoAbierto(false);
    setCambiada(false);
  }

  return (
    <div className="barra-lateral__usuario">
      <details
        className="menu-usuario"
        open={menuAbierto}
        onToggle={(evento) => setMenuAbierto(evento.currentTarget.open)}
      >
        <summary className="menu-usuario__disparador">
          <span className="menu-usuario__identidad">
            <span className="barra-lateral__nombre">{usuario.nombre}</span>
            <span className="tenue">
              {usuario.rol.replaceAll("_", " ").toLowerCase()}
            </span>
          </span>
          <span className="menu-usuario__signo" aria-hidden="true">
            ▾
          </span>
        </summary>

        <div className="menu-usuario__panel">
          <p className="tenue">Sesión de «{usuario.usuario}»</p>
          <button
            type="button"
            className="boton boton--pequeno boton--bloque"
            onClick={() => {
              setMenuAbierto(false);
              setCambiada(false);
              setDialogoAbierto(true);
            }}
          >
            Cambiar mi clave
          </button>
        </div>
      </details>

      <Dialogo
        abierto={dialogoAbierto}
        titulo="Cambiar mi clave"
        onCerrar={cerrarDialogo}
        pie={
          cambiada ? (
            <button
              type="button"
              className="boton boton--principal"
              onClick={cerrarDialogo}
            >
              Listo
            </button>
          ) : undefined
        }
      >
        {cambiada ? (
          <div className="aviso aviso--exito" role="status">
            <div>
              <strong>Clave cambiada.</strong>
              <p>
                La próxima vez que entre use la nueva. No hace falta volver a
                iniciar sesión.
              </p>
            </div>
          </div>
        ) : (
          <FormularioCambioClave onListo={() => setCambiada(true)} />
        )}
      </Dialogo>
    </div>
  );
}

function BarraLateral() {
  const { tieneRol } = useAuth();
  const marca = useMarcaElegida();

  return (
    <aside className="barra-lateral">
      <div className="marca">
        <img
          className="marca__logo"
          src={marca.logo}
          alt=""
          width={anchoLogo(marca, ALTO_LOGO)}
          height={ALTO_LOGO}
        />
        <span>
          <span className="marca__nombre">SIGREP</span>
          <br />
          {/* El nombre de la unidad, no el del grupo: es lo que distingue a
              esta instancia de las otras dos, y el logo de al lado ya lo dice
              en imagen —por eso su `alt` va vacío, para no repetirlo—. */}
          <span className="marca__lema">{marca.nombre}</span>
        </span>
      </div>

      <nav className="navegacion" aria-label="Navegación principal">
        {menuDe(marca.clave).map((grupo) => {
          const visibles = grupo.items.filter(
            (item) => !item.roles || tieneRol(...item.roles),
          );
          if (visibles.length === 0) return null;

          return (
            <div key={grupo.titulo}>
              <p className="navegacion__grupo">{grupo.titulo}</p>
              {visibles.map((item) => (
                <NavLink
                  key={item.ruta}
                  to={item.ruta}
                  end={item.ruta === "/"}
                  className="enlace-nav"
                >
                  <span className="enlace-nav__icono" aria-hidden="true">
                    {item.icono}
                  </span>
                  {item.etiqueta}
                </NavLink>
              ))}
            </div>
          );
        })}
      </nav>

      <MenuUsuario />
    </aside>
  );
}

/**
 * Período y fecha de corte, siempre visibles.
 *
 * §6 lo pide sin excepciones y con razón: un reporte sin fecha de corte es un
 * reporte que alguien va a malinterpretar. Va en la cabecera fija, así que
 * acompaña al usuario en las siete pantallas y en cualquier punto del scroll.
 */
function Corte() {
  const { filtros } = useFiltros();
  const hoy = new Date();
  const corteEfectivo =
    filtros.hasta ??
    `${hoy.getFullYear()}-${String(hoy.getMonth() + 1).padStart(2, "0")}-${String(hoy.getDate()).padStart(2, "0")}`;

  return (
    <div className="corte">
      <span className="corte__periodo">{periodoLargo(filtros.periodo)}</span>
      <span className="corte__fecha">
        Corte: <strong>{fechaLarga(corteEfectivo)}</strong>
        {filtros.hasta ? null : <span className="corte__hoy"> (hoy)</span>}
      </span>
    </div>
  );
}

export function Disposicion({ children }: { children?: ReactNode }) {
  const { salir } = useAuth();
  const { pathname } = useLocation();
  const titulo = TITULOS[pathname] ?? "SIGREP";

  return (
    <div className="disposicion">
      <BarraLateral />

      <div className="principal">
        <header className="cabecera">
          <h1 className="cabecera__titulo">{titulo}</h1>
          <Corte />
          <div className="cabecera__acciones">
            {MODO_EJEMPLOS ? (
              <span
                className="distintivo distintivo--aviso"
                title="La aplicación no está consultando el backend: las cifras son ficticias."
              >
                ⚠ Datos de ejemplo
              </span>
            ) : null}
            <SelectorTema />
            <button
              type="button"
              className="boton boton--pequeno"
              onClick={salir}
            >
              Cerrar sesión
            </button>
          </div>
        </header>

        <main className="contenido">{children ?? <Outlet />}</main>
      </div>
    </div>
  );
}
