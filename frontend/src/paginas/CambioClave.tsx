/**
 * Cambio de clave: el obligatorio y el voluntario, con un solo formulario.
 *
 * Son la misma operación —`POST /auth/cambiar-clave`— vista desde dos sitios, y
 * conviene que lo sigan siendo: si mañana el mínimo sube de doce a catorce
 * caracteres, se cambia en un punto y las dos entradas quedan alineadas.
 *
 * El largo mínimo se valida aquí, antes de enviar. Dejar que el usuario lo
 * descubra con un 422 del servidor es hacerle escribir dos veces una clave que
 * para entonces ya no recordará por qué fue rechazada.
 */

import { useState } from "react";
import type { FormEvent } from "react";

import { useCambiarClave } from "@/api/consultas";
import { LARGO_MINIMO_CLAVE } from "@/api/tipos";
import { useAuth } from "@/auth/ContextoAuth";
import { AvisoError, Campo } from "@/componentes/comunes";
import logo from "@/recursos/carnes-santacruz.png";

export function FormularioCambioClave({
  onListo,
  textoEnvio = "Cambiar la clave",
}: {
  /** Se invoca cuando el backend confirma el cambio. */
  onListo?: () => void;
  textoEnvio?: string;
}) {
  const cambiar = useCambiarClave();
  const [actual, setActual] = useState("");
  const [nueva, setNueva] = useState("");
  const [confirmacion, setConfirmacion] = useState("");

  const faltan = LARGO_MINIMO_CLAVE - nueva.length;
  const errorNueva =
    nueva !== "" && faltan > 0
      ? `Faltan ${faltan} caracteres para llegar al mínimo de ${LARGO_MINIMO_CLAVE}.`
      : nueva !== "" && nueva === actual
        ? "La clave nueva tiene que ser distinta de la actual."
        : undefined;
  const errorConfirmacion =
    confirmacion !== "" && confirmacion !== nueva ? "Las dos claves no coinciden." : undefined;

  const puedeEnviar =
    actual !== "" &&
    nueva !== "" &&
    confirmacion === nueva &&
    errorNueva === undefined &&
    !cambiar.isPending;

  function alEnviar(evento: FormEvent) {
    evento.preventDefault();
    if (!puedeEnviar) return;

    cambiar.mutate(
      { clave_actual: actual, clave_nueva: nueva },
      {
        onSuccess: () => {
          // Ninguna de las tres cadenas debe sobrevivir al envío.
          setActual("");
          setNueva("");
          setConfirmacion("");
          onListo?.();
        },
      },
    );
  }

  return (
    <form className="acceso__formulario" onSubmit={alEnviar}>
      <AvisoError error={cambiar.error} />

      <Campo etiqueta="Clave actual">
        <input
          className="campo__control"
          type="password"
          value={actual}
          onChange={(evento) => setActual(evento.target.value)}
          autoComplete="current-password"
          required
          maxLength={200}
        />
      </Campo>

      <Campo
        etiqueta="Clave nueva"
        ayuda={`Mínimo ${LARGO_MINIMO_CLAVE} caracteres.`}
        error={errorNueva}
      >
        <input
          className="campo__control"
          type="password"
          value={nueva}
          onChange={(evento) => setNueva(evento.target.value)}
          autoComplete="new-password"
          minLength={LARGO_MINIMO_CLAVE}
          required
          maxLength={200}
        />
      </Campo>

      <Campo etiqueta="Repita la clave nueva" error={errorConfirmacion}>
        <input
          className="campo__control"
          type="password"
          value={confirmacion}
          onChange={(evento) => setConfirmacion(evento.target.value)}
          autoComplete="new-password"
          required
          maxLength={200}
        />
      </Campo>

      <button type="submit" className="boton boton--principal boton--bloque" disabled={!puedeEnviar}>
        {cambiar.isPending ? "Guardando…" : textoEnvio}
      </button>
    </form>
  );
}

/**
 * Pantalla de cambio obligatorio.
 *
 * `App` la renderiza **en lugar** del enrutador, no como una ruta más: así no
 * existe URL que la esquive. Al terminar, el perfil deja de traer la marca y la
 * aplicación aparece en el mismo instante, sin repetir el inicio de sesión.
 */
export function CambioClaveObligatorio() {
  const { usuario, salir } = useAuth();

  return (
    <div className="acceso">
      <div className="acceso__tarjeta acceso__tarjeta--ancha">
        <div className="acceso__marca">
          <img
            className="marca__logo marca__logo--grande"
            src={logo}
            alt="Carnes Santacruz"
            width={96}
            height={102}
          />
          <h1>Cambie su clave</h1>
          <p className="tenue">
            {usuario ? `${usuario.nombre} · ${usuario.usuario}` : "Sesión iniciada"}
          </p>
        </div>

        <div className="aviso aviso--advertencia" role="alert">
          <div>
            <strong>Su clave es provisional.</strong>
            <p>
              La generó el sistema al crear la cuenta o al restablecerla, y alguien más la vio para
              poder entregársela. Hasta que la cambie no se puede abrir ninguna otra pantalla.
            </p>
          </div>
        </div>

        <FormularioCambioClave textoEnvio="Cambiar y continuar" />

        <p className="acceso__salida tenue">
          ¿No es su cuenta?{" "}
          <button type="button" className="boton boton--sutil boton--pequeno" onClick={salir}>
            Cerrar sesión
          </button>
        </p>
      </div>
    </div>
  );
}
