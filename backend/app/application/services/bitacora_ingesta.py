"""Acumulador de lo que sale mal en una corrida de ingesta (§5).

«Nada se descarta en silencio» es la regla, y esta clase es cómo se cumple sin
convertir la bitácora en un vertedero.

Hay **dos** cosas distintas que registrar y la diferencia importa:

1. **Rechazos.** La fila no entró: un punto de venta desconocido, una fecha
   ilegible. El número tiene que cuadrar: `leidas = aceptadas + rechazadas`.
2. **Anotaciones de calidad.** La fila sí entró, pero degradada: la clase de
   cliente venía corrupta y se guardó como `SIN CLASIFICAR`, el domicilio venía
   en blanco y se guardó como `NULL`. No son rechazos —contarlas como tales
   diría que se perdió venta que no se perdió— pero **tienen que dejar
   constancia**: la diferencia entre degradar por decisión y por accidente es
   que la primera se ve en alguna parte.

Una categoría de SIESA sin mapeo era hasta hace poco el ejemplo canónico del
punto 2 —entraba clasificada como `OTROS` y quedaba anotada—. Ya no: `OTROS`
desapareció con la taxonomía nueva y esas filas son ahora **rechazos** (§3.1).
El cambio se nota aquí porque mueve venta de `aceptadas` a `rechazadas`, y eso
es exactamente lo que se quería que se notara.

Y hay un problema de escala que ninguna implementación ingenua sobrevive. En el
archivo real, 95 907 de 131 819 filas traen la clase de cliente vacía: una fila
de bitácora por cada una son 96 000 registros por corrida y más de un millón al
año para decir cuatro veces lo mismo. Por eso las anotaciones se **agregan** por
(campo, motivo, valor), con su recuento y la primera fila donde apareció el
problema, y de cada motivo se conservan los `MAX_VALORES_POR_CAMPO` valores
**más frecuentes**; el resto se resume en una línea.

Que el criterio sea la frecuencia y no el orden de llegada no es un detalle: la
columna `CLASES DE CLIENTES` trae unos 3 000 sellos de tiempo distintos —uno por
transacción, todos irrelevantes uno a uno— y 109 filas con el nombre de usuario
`johana.muñoz`, que es el hallazgo que alguien tiene que ver. Ordenando por
frecuencia, `johana.muñoz` sale en la lista y los sellos de tiempo se van al
resumen. Al revés, el hallazgo quedaba sepultado bajo los primeros cincuenta
sellos de tiempo del archivo.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

#: Rechazos que se guardan fila a fila antes de empezar a agregar. Con 500 hay
#: de sobra para ir al Excel y mirar; más allá el problema no es de filas
#: sueltas, es del archivo entero.
MAX_RECHAZOS_DETALLADOS = 500

#: Valores distintos que se conservan por (campo, motivo), los más frecuentes.
MAX_VALORES_POR_CAMPO = 50

#: Tope duro de claves acumuladas por campo. Protege la memoria del caso
#: patológico —un campo con un valor distinto en cada una de 440 000 filas—;
#: pasado el tope, lo nuevo se cuenta sin conservar el ejemplo.
#:
#: 20 000 no es un número redondo por casualidad: la columna `CLASES DE
#: CLIENTES` del archivo real trae unos 12 000 sellos de tiempo distintos, y con
#: un tope por debajo de eso el recuento de `johana.muñoz` —que aparece después,
#: en las filas del C.O. numérico— caía en el saco del resumen y desaparecía del
#: informe. Son ~5 MB durante la corrida a cambio de que el hallazgo se vea.
MAX_CLAVES_ACUMULADAS = 20000

_LIMITE_CAMPO = 60
_LIMITE_VALOR = 300
_LIMITE_MOTIVO = 300


@dataclass(slots=True)
class AnotacionBitacora:
    """Una entrada de la bitácora, ya lista para `RechazoIngesta`."""

    fila: int | None
    campo: str | None
    valor: str | None
    motivo: str
    veces: int = 1

    def a_fila(self) -> dict[str, object]:
        """Campos de `RechazoIngesta`. El recuento va dentro del motivo.

        Se mete en el texto en lugar de en una columna nueva porque el modelo de
        la bitácora está cerrado y estable, y porque el motivo es justamente lo
        que el operador lee: «… (95.907 filas)» dice más que un `veces=95907` en
        una columna que la pantalla todavía no pinta.
        """
        motivo = self.motivo if self.veces == 1 else f"{self.motivo} ({_miles(self.veces)} filas)"
        return {
            "fila": self.fila,
            "campo": _acotar(self.campo, _LIMITE_CAMPO),
            "valor": _acotar(self.valor, _LIMITE_VALOR),
            "motivo": _acotar(motivo, _LIMITE_MOTIVO) or "Sin motivo.",
        }


@dataclass(slots=True)
class BitacoraIngesta:
    """Rechazos y anotaciones de calidad de una corrida."""

    rechazadas: int = 0
    _detalle: list[AnotacionBitacora] = field(default_factory=list)
    _agregadas: dict[tuple[str | None, str, str | None], AnotacionBitacora] = field(
        default_factory=dict
    )
    _claves_por_campo: dict[str | None, int] = field(default_factory=dict)

    # ── Registro ──────────────────────────────────────────────────────────────

    def rechazar(self, fila: int | None, campo: str | None, valor: object, motivo: str) -> None:
        """La fila no entró. Cuenta para `rechazadas`."""
        self.rechazadas += 1
        if len(self._detalle) < MAX_RECHAZOS_DETALLADOS:
            self._detalle.append(AnotacionBitacora(fila, campo, _texto(valor), motivo))
            return
        self._agregar(fila, campo, None, motivo)

    def anotar(self, fila: int | None, campo: str | None, valor: object, motivo: str) -> None:
        """La fila entró degradada. **No** cuenta para `rechazadas`."""
        self._agregar(fila, campo, _texto(valor), motivo)

    def _agregar(self, fila: int | None, campo: str | None, valor: str | None, motivo: str) -> None:
        clave = (campo, motivo, valor)
        anotacion = self._agregadas.get(clave)
        if anotacion is not None:
            anotacion.veces += 1
            return

        acumuladas = self._claves_por_campo.get(campo, 0)
        if valor is not None and acumuladas >= MAX_CLAVES_ACUMULADAS:
            # Se agotó el presupuesto de ejemplos de este campo: se sigue
            # contando, pero sin guardar un valor nuevo por cada fila.
            self._agregar(fila, campo, None, motivo)
            return

        self._claves_por_campo[campo] = acumuladas + 1
        self._agregadas[clave] = AnotacionBitacora(fila, campo, valor, motivo)

    # ── Volcado ───────────────────────────────────────────────────────────────

    def filas(self) -> list[dict[str, object]]:
        """Entradas listas para insertar en `rechazos_ingesta`.

        De cada motivo salen los valores más repetidos y una línea de resumen
        con lo que quedó fuera, para que el total siga cuadrando. Ordenadas por
        número de fila: la pantalla de Ingesta se lee en el mismo orden en que
        el usuario recorrería el archivo.
        """
        todas = [*self._detalle]
        for grupo in self._agrupar_por_motivo().values():
            grupo.sort(key=lambda anotacion: (-anotacion.veces, anotacion.fila or 0))
            todas.extend(grupo[:MAX_VALORES_POR_CAMPO])
            resto = grupo[MAX_VALORES_POR_CAMPO:]
            if resto:
                todas.append(_resumir(resto))

        todas.sort(key=lambda anotacion: (anotacion.fila is None, anotacion.fila or 0))
        return [anotacion.a_fila() for anotacion in todas]

    def _agrupar_por_motivo(self) -> dict[tuple[str | None, str], list[AnotacionBitacora]]:
        grupos: dict[tuple[str | None, str], list[AnotacionBitacora]] = defaultdict(list)
        for anotacion in self._agregadas.values():
            grupos[(anotacion.campo, anotacion.motivo)].append(anotacion)
        return grupos


def _resumir(anotaciones: list[AnotacionBitacora]) -> AnotacionBitacora:
    """Una sola entrada por todo lo que no cupo en el detalle."""
    referencia = anotaciones[0]
    return AnotacionBitacora(
        fila=min((a.fila for a in anotaciones if a.fila is not None), default=None),
        campo=referencia.campo,
        valor=None,
        motivo=f"{referencia.motivo} · y {_miles(len(anotaciones))} valores distintos más",
        veces=sum(a.veces for a in anotaciones),
    )


def _miles(numero: int) -> str:
    """`95907` → `'95.907'`. Separador de miles colombiano, sin depender del locale."""
    return f"{numero:,}".replace(",", ".")


def _texto(valor: object) -> str | None:
    if valor is None:
        return None
    crudo = str(valor).strip()
    return crudo[:_LIMITE_VALOR] if crudo else None


def _acotar(valor: str | None, limite: int) -> str | None:
    if valor is None:
        return None
    return valor if len(valor) <= limite else valor[: limite - 1] + "…"
