/** Marco de la aplicación: barra lateral, cabecera y área de contenido. */

import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";

import { MODO_EJEMPLOS } from "@/api/cliente";
import type { Rol } from "@/api/tipos";
import { useAuth } from "@/auth/ContextoAuth";
import { useFiltros } from "@/componentes/filtros";
import { fechaLarga, periodoLargo } from "@/utilidades/formato";
import logo from "@/recursos/carnes-santacruz.png";

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

/** Las pantallas de §6 de la especificación. */
const MENU: GrupoNav[] = [
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
      { ruta: "/presupuesto", etiqueta: "Presupuesto", icono: "≡", roles: ["GERENTE", "ANALISTA"] },
      { ruta: "/calendario", etiqueta: "Días hábiles", icono: "◷" },
      { ruta: "/ingesta", etiqueta: "Ingesta", icono: "⇄" },
    ],
  },
];

const TITULOS: Record<string, string> = {
  "/": "Tablero gerencial",
  "/cumplimiento": "Cumplimiento por punto de venta",
  "/venta-diaria": "Venta diaria",
  "/clientes": "Clientes y vendedores",
  "/presupuesto": "Parametrización de presupuesto",
  "/calendario": "Calendario de días hábiles",
  "/ingesta": "Ingesta desde SIESA",
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
  const siguiente: Record<Tema, Tema> = { sistema: "claro", claro: "oscuro", oscuro: "sistema" };
  const iconos: Record<Tema, string> = { sistema: "◐", claro: "☀", oscuro: "☾" };

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

function BarraLateral() {
  const { tieneRol, usuario } = useAuth();

  return (
    <aside className="barra-lateral">
      <div className="marca">
        <img className="marca__logo" src={logo} alt="Carnes Santacruz" width={40} height={42} />
        <span>
          <span className="marca__nombre">SIGREP</span>
          <br />
          <span className="marca__lema">Grupo Santa Cruz</span>
        </span>
      </div>

      <nav className="navegacion" aria-label="Navegación principal">
        {MENU.map((grupo) => {
          const visibles = grupo.items.filter((item) => !item.roles || tieneRol(...item.roles));
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

      {usuario ? (
        <div className="barra-lateral__usuario">
          <div className="barra-lateral__nombre">{usuario.nombre}</div>
          <div className="tenue">{usuario.rol.replaceAll("_", " ").toLowerCase()}</div>
        </div>
      ) : null}
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
            <button type="button" className="boton boton--pequeno" onClick={salir}>
              Cerrar sesión
            </button>
          </div>
        </header>

        <main className="contenido">{children ?? <Outlet />}</main>
      </div>
    </div>
  );
}
