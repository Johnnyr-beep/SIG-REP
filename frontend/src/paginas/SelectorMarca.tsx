/**
 * Selector de unidad de negocio: la primera pantalla, antes del acceso.
 *
 * Tres tarjetas, cada una pintada con los colores muestreados de su propio
 * logo —el atributo `data-marca-tarjeta` monta la rampa de esa marca dentro de
 * la tarjeta—, para que la elección se vea antes de hacerla.
 *
 * Las dos unidades sin desplegar **no se ocultan**: existen en el grupo y quien
 * las busque tiene que encontrarlas y entender por qué no puede entrar. Son
 * botones de verdad, alcanzables con el tabulador y anunciados como
 * `aria-disabled` —no `disabled`, que las sacaría del recorrido de foco y
 * dejaría al usuario de teclado sin manera de leer el motivo—; al pulsarlas se
 * explica la situación en una región viva en lugar de continuar al acceso.
 */

import { useState } from "react";

import { useMarca } from "@/marca/ContextoMarca";
import { MARCAS, anchoLogo } from "@/marca/marcas";

/** El mismo que fija `.tarjeta-marca__logo` en la hoja. */
const ALTO_LOGO = 84;

export function SelectorMarca() {
  const { elegir } = useMarca();
  const [aviso, setAviso] = useState("");

  // Sale del censo, no de una cadena escrita a mano: el día que se despliegue
  // la segunda unidad, el mensaje se corrige solo al cambiarle el estado.
  const desplegadas = MARCAS.filter((marca) => marca.estado === "activa")
    .map((marca) => marca.nombre)
    .join(", ");

  return (
    <div className="selector">
      <main className="selector__panel">
        <header className="selector__cabecera">
          <h1 className="selector__titulo">SIGREP</h1>
          <p className="tenue">Sistema Gerencial de Reportes · Grupo Santa Cruz</p>
          <p className="selector__instruccion">
            Elija la unidad de negocio. La aplicación adopta su logo, su nombre y sus colores, y
            recuerda la elección para las próximas veces.
          </p>
        </header>

        <ul className="selector__lista">
          {MARCAS.map((marca) => {
            const activa = marca.estado === "activa";
            const idDetalle = `marca-detalle-${marca.clave}`;

            return (
              <li key={marca.clave} className="selector__opcion">
                <button
                  type="button"
                  className={`tarjeta-marca${activa ? "" : " tarjeta-marca--pendiente"}`}
                  data-marca-tarjeta={marca.clave}
                  aria-disabled={activa ? undefined : true}
                  aria-describedby={idDetalle}
                  onClick={() => {
                    if (!activa) {
                      setAviso(
                        `${marca.nombre} todavía no está desplegada: no hay datos ni servidor ` +
                          `detrás. Por ahora solo se puede entrar a ${desplegadas}.`,
                      );
                      return;
                    }
                    setAviso("");
                    elegir(marca.clave);
                  }}
                >
                  <img
                    className="tarjeta-marca__logo"
                    src={marca.logo}
                    alt=""
                    width={anchoLogo(marca, ALTO_LOGO)}
                    height={ALTO_LOGO}
                  />
                  <span className="tarjeta-marca__nombre">{marca.nombre}</span>
                  <span
                    className={`distintivo distintivo--${activa ? "exito" : "neutro"}`}
                  >
                    <span aria-hidden="true">{activa ? "✓" : "◷"}</span>
                    {activa ? "Disponible" : "Próximamente"}
                  </span>
                </button>

                <p className="selector__detalle tenue" id={idDetalle}>
                  {marca.descripcion}
                </p>
              </li>
            );
          })}
        </ul>

        {/* Vive siempre en el árbol, vacía mientras no haga falta: una región
            que aparece y desaparece no la anuncian todos los lectores. */}
        <p className="selector__aviso" role="status" aria-live="polite">
          {aviso ? (
            <span className="aviso aviso--advertencia">
              <span>
                <span aria-hidden="true">⚠ </span>
                {aviso}
              </span>
            </span>
          ) : null}
        </p>
      </main>
    </div>
  );
}
