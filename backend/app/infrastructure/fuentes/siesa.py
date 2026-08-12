"""`FuenteVentaSiesa`: el hueco reservado para la API de SIESA (§5).

**La API de SIESA todavía no se ha entregado.** Este módulo existe con la firma
correcta y falla con un `NotImplementedError` explicativo —que `core/errors.py`
traduce a un 501— en lugar de con un contrato inventado.

No se inventan endpoints, ni nombres de campo, ni autenticación. Un cliente HTTP
escrito contra una API imaginaria no es trabajo adelantado: es trabajo que habrá
que tirar, y mientras tanto da la falsa impresión de que la integración está
hecha. Lo que sí está hecho es lo que importa: el resto del sistema consume el
puerto `FuenteVenta`, así que el día que llegue la especificación solo hay que
rellenar `obtener_ventas` aquí y cambiar `SIGREP_FUENTE_VENTA`.

Lo que hará falta saber cuando llegue la especificación:

1. URL base, mecanismo de autenticación y vigencia de las credenciales.
2. El endpoint de detalle de venta por rango de fechas y su paginación —son
   ~14 600 filas al día, así que paginar no es opcional—.
3. El nombre y el tipo de cada campo de §3.4, y si el C.O. y los NIT llegan con
   los mismos vicios que en el Excel (`606` numérico, NIT con relleno).
4. Si la API expone marca de modificación, para hacer carga incremental en lugar
   de reprocesar el rango completo.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from datetime import date

from app.domain.puertos import LineaVenta

MENSAJE_SIESA_PENDIENTE = (
    "La fuente SIESA todavía no está implementada porque su API no se ha entregado. "
    "El puerto `FuenteVenta` y toda la ingesta ya funcionan contra `FuenteVentaExcel`: "
    "use la fuente «excel» o `POST /ingesta/archivo` mientras tanto. Ver §5 de "
    "docs/ESPECIFICACION.md."
)


class FuenteVentaSiesa:
    """Implementación del puerto `FuenteVenta` contra la API de SIESA.

    Se construye sin problema —para que `obtener_fuente` pueda devolverla y para
    que la selección por variable de entorno se pueda probar— y falla al usarla.
    """

    def __init__(self, base_url: str | None = None, token: str | None = None) -> None:
        self.base_url = base_url
        self._token = token

    def obtener_ventas(
        self,
        desde: date,
        hasta: date,
        centros: Sequence[str] | None = None,
    ) -> Iterator[LineaVenta]:
        """Pendiente: la API de SIESA no se ha entregado (§5)."""
        raise NotImplementedError(f"{MENSAJE_SIESA_PENDIENTE} Rango solicitado: {desde} a {hasta}.")
