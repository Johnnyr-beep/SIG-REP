"""Semáforo de cumplimiento (§4.1 de la especificación).

Los umbrales **se inyectan**, no son constantes de módulo. La especificación los
declara «parámetro del sistema, no constantes en el código» y además están
pendientes de confirmación con el usuario (§8.3): el día que Gerencia decida que
el amarillo empieza en el 95 % del ideal, eso es un cambio de configuración, no
un despliegue.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.domain.enums import Semaforo


@dataclass(frozen=True, slots=True)
class UmbralesSemaforo:
    """Frontera entre amarillo y rojo, expresada como fracción del ideal.

    | Estado   | Condición                                       |
    |----------|-------------------------------------------------|
    | Verde    | `cumplimiento >= ideal`                         |
    | Amarillo | `ideal × factor_amarillo <= cumplimiento < ideal`|
    | Rojo     | `cumplimiento < ideal × factor_amarillo`        |

    SUPUESTO: `factor_amarillo = 0.90`, la propuesta inicial de §4.1. Se
    configura con `SIGREP_FACTOR_SEMAFORO_AMARILLO`.
    """

    factor_amarillo: Decimal = Decimal("0.90")

    def __post_init__(self) -> None:
        if not (Decimal(0) < self.factor_amarillo <= Decimal(1)):
            raise ValueError(
                "El factor del amarillo debe estar en (0, 1]: es una fracción del ideal."
            )

    def a_diccionario(self) -> dict[str, str]:
        """Representación para el bloque `parametros_calculo` de la respuesta.

        La pantalla muestra con qué umbrales se pintó cada semáforo; un color
        sin su regla al lado es un número sin origen.
        """
        return {"factor_amarillo": str(self.factor_amarillo)}


def evaluar_semaforo(
    cumplimiento: Decimal | None,
    ideal: Decimal | None,
    umbrales: UmbralesSemaforo,
) -> Semaforo:
    """Traduce cumplimiento e ideal a un color.

    Devuelve `SIN_PRESUPUESTO` cuando no hay nada contra qué medir: sin
    presupuesto no hay cumplimiento (el caso de 432 EVENTOS BUCARAMANGA) y sin
    calendario no hay ideal. Pintar verde o rojo en esos casos sería inventar.
    """
    if cumplimiento is None or ideal is None:
        return Semaforo.SIN_PRESUPUESTO
    if cumplimiento >= ideal:
        return Semaforo.VERDE
    if cumplimiento >= ideal * umbrales.factor_amarillo:
        return Semaforo.AMARILLO
    return Semaforo.ROJO
