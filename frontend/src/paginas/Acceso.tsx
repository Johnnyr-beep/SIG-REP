/** Pantalla de inicio de sesión. */

import { useState } from "react";
import type { FormEvent } from "react";

import { MODO_EJEMPLOS } from "@/api/cliente";
import { AvisoError } from "@/componentes/comunes";
import { useAuth } from "@/auth/ContextoAuth";
import { useMarca, useMarcaElegida } from "@/marca/ContextoMarca";
import { anchoLogo } from "@/marca/marcas";

/** El mismo que fija `.marca__logo--grande` en la hoja. */
const ALTO_LOGO = 96;

export function Acceso() {
  const { entrar } = useAuth();
  const { olvidar } = useMarca();
  const marca = useMarcaElegida();
  const [usuario, setUsuario] = useState("");
  const [clave, setClave] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [enviando, setEnviando] = useState(false);

  async function alEnviar(evento: FormEvent) {
    evento.preventDefault();
    setError(null);
    setEnviando(true);
    try {
      await entrar(usuario.trim(), clave);
    } catch (fallo) {
      setError(fallo);
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className="acceso">
      <div className="acceso__tarjeta">
        <div className="acceso__marca">
          <img
            className="marca__logo marca__logo--grande"
            src={marca.logo}
            alt={marca.nombre}
            width={anchoLogo(marca, ALTO_LOGO)}
            height={ALTO_LOGO}
          />
          <h1>SIGREP</h1>
          <p className="tenue">{marca.nombre} · Grupo Santa Cruz</p>
        </div>

        <form className="acceso__formulario" onSubmit={alEnviar}>
          <AvisoError error={error} />

          {MODO_EJEMPLOS ? (
            <div className="aviso aviso--advertencia">
              <div>
                <strong>Modo de datos de ejemplo.</strong>
                <p>
                  La aplicación no consulta el backend. Entre con cualquier usuario y contraseña
                  para revisar las pantallas; las cifras que verá son ficticias.
                </p>
              </div>
            </div>
          ) : null}

          <label className="campo">
            <span className="campo__etiqueta">Usuario</span>
            <input
              className="campo__control"
              value={usuario}
              onChange={(evento) => setUsuario(evento.target.value)}
              autoComplete="username"
              autoFocus
              required
              maxLength={50}
            />
          </label>

          <label className="campo">
            <span className="campo__etiqueta">Contraseña</span>
            <input
              className="campo__control"
              type="password"
              value={clave}
              onChange={(evento) => setClave(evento.target.value)}
              autoComplete="current-password"
              required
              maxLength={200}
            />
          </label>

          <button
            type="submit"
            className="boton boton--principal boton--bloque"
            disabled={enviando || !usuario || !clave}
          >
            {enviando ? "Verificando…" : "Ingresar"}
          </button>
        </form>

        {/* Discreto y fuera del formulario: quien llega aquí ya eligió, y solo
            necesita esta salida si se equivocó de unidad. Devuelve al selector
            sin tocar la sesión —no hay ninguna abierta todavía—. */}
        <p className="acceso__salida tenue">
          <button type="button" className="boton boton--sutil boton--pequeno" onClick={olvidar}>
            Cambiar unidad de negocio
          </button>
        </p>
      </div>
    </div>
  );
}
