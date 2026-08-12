/** Piezas de interfaz reutilizadas por todas las pantallas. */

import { useEffect, useRef } from "react";
import type { ReactNode } from "react";

import { ErrorApi } from "@/api/cliente";

// ── Estados de carga, vacío y error ──────────────────────────────────────────

export function Cargando({ texto = "Cargando…" }: { texto?: string }) {
  return (
    <div className="cargando" role="status" aria-live="polite">
      {texto}
    </div>
  );
}

export function Vacio({ titulo, detalle }: { titulo: string; detalle?: string }) {
  return (
    <div className="vacio">
      <p style={{ fontWeight: 600 }}>{titulo}</p>
      {detalle ? <p className="tenue">{detalle}</p> : null}
    </div>
  );
}

/**
 * Muestra un error de la API con su mensaje real.
 *
 * El backend redacta mensajes accionables («El período 2026-07 está cerrado»);
 * sustituirlos por un «Ocurrió un error» genérico desperdicia esa información y
 * genera una llamada a soporte.
 */
export function AvisoError({ error }: { error: unknown }) {
  if (!error) return null;

  const mensaje =
    error instanceof ErrorApi
      ? error.mensaje
      : error instanceof Error
        ? error.message
        : "Ocurrió un error inesperado.";

  const codigo = error instanceof ErrorApi ? error.codigo : null;

  return (
    <div className="aviso aviso--error" role="alert">
      <div>
        <strong>{mensaje}</strong>
        {codigo ? <p className="tenue" style={{ marginTop: 4 }}>Código: {codigo}</p> : null}
      </div>
    </div>
  );
}

// ── Tarjeta ──────────────────────────────────────────────────────────────────

export function Tarjeta({
  titulo,
  descripcion,
  acciones,
  children,
  pie,
  sinRelleno,
}: {
  titulo?: ReactNode;
  descripcion?: ReactNode;
  acciones?: ReactNode;
  children: ReactNode;
  pie?: ReactNode;
  /** Para tablas, que llegan al borde de la tarjeta. */
  sinRelleno?: boolean;
}) {
  return (
    <section className="tarjeta">
      {titulo ? (
        <header className="tarjeta__cabecera">
          <div>
            <h2>{titulo}</h2>
            {descripcion ? <p className="tenue">{descripcion}</p> : null}
          </div>
          {acciones ? <div className="empujar">{acciones}</div> : null}
        </header>
      ) : null}
      <div className={sinRelleno ? "" : "tarjeta__cuerpo"}>{children}</div>
      {pie ? <footer className="tarjeta__pie">{pie}</footer> : null}
    </section>
  );
}

// ── Distintivo ───────────────────────────────────────────────────────────────

export type Tono = "neutro" | "info" | "exito" | "aviso" | "peligro";

export function Distintivo({ tono = "neutro", children }: { tono?: Tono; children: ReactNode }) {
  return <span className={`distintivo distintivo--${tono}`}>{children}</span>;
}

// ── Diálogo ──────────────────────────────────────────────────────────────────

/**
 * Modal sobre `<dialog>` nativo: el navegador aporta el foco atrapado, el cierre
 * con Escape y el rol ARIA correcto. Reimplementarlo a mano es la vía habitual
 * para romper la accesibilidad sin darse cuenta.
 */
export function Dialogo({
  abierto,
  titulo,
  onCerrar,
  children,
  pie,
}: {
  abierto: boolean;
  titulo: string;
  onCerrar: () => void;
  children: ReactNode;
  pie?: ReactNode;
}) {
  const referencia = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialogo = referencia.current;
    if (!dialogo) return;

    if (abierto && !dialogo.open) dialogo.showModal();
    if (!abierto && dialogo.open) dialogo.close();
  }, [abierto]);

  return (
    <dialog ref={referencia} className="dialogo" onCancel={onCerrar} onClose={onCerrar}>
      <header className="dialogo__cabecera">
        <h2>{titulo}</h2>
        <button
          type="button"
          className="boton boton--sutil boton--pequeno empujar"
          onClick={onCerrar}
          aria-label="Cerrar"
        >
          ✕
        </button>
      </header>
      <div className="dialogo__cuerpo">{children}</div>
      {pie ? <footer className="dialogo__pie">{pie}</footer> : null}
    </dialog>
  );
}

// ── Campo de formulario ──────────────────────────────────────────────────────

export function Campo({
  etiqueta,
  ayuda,
  error,
  children,
}: {
  etiqueta: string;
  ayuda?: string;
  error?: string;
  children: ReactNode;
}) {
  return (
    <label className="campo">
      <span className="campo__etiqueta">{etiqueta}</span>
      {children}
      {ayuda && !error ? <span className="campo__ayuda">{ayuda}</span> : null}
      {error ? <span className="campo__error">{error}</span> : null}
    </label>
  );
}

// ── Nota informativa desplegable ─────────────────────────────────────────────

/**
 * Explicación al lado del dato, sobre `<details>` nativo.
 *
 * Un `title` no lo lee el teclado ni el móvil, y un tooltip a mano exige
 * reimplementar el foco. `<details>` se abre con Enter, se cierra con Escape y
 * lo anuncian los lectores de pantalla sin una línea de JavaScript. El panel se
 * posiciona en absoluto para no descolocar la fila de la tabla al abrirse.
 */
export function Pista({
  etiqueta,
  children,
  alineacion = "izquierda",
}: {
  /** Qué explica esta pista; forma el nombre accesible del control. */
  etiqueta: string;
  children: ReactNode;
  alineacion?: "izquierda" | "derecha";
}) {
  return (
    <details className={`pista pista--${alineacion}`}>
      <summary
        className="pista__disparador"
        aria-label={`Cómo se calcula: ${etiqueta}`}
        title={`Cómo se calcula: ${etiqueta}`}
      >
        <span aria-hidden="true">ⓘ</span>
      </summary>
      <div className="pista__cuerpo">
        <p className="pista__titulo">{etiqueta}</p>
        {children}
      </div>
    </details>
  );
}
