"""Revisión: idempotencia y transaccionalidad de la ingesta (§5, §7)."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.application.services import ingesta_service
from app.application.services.ingesta_service import IngestaService
from app.domain.enums import FuenteIngesta
from app.domain.puertos import LineaVenta
from app.infrastructure.models.venta import VentaLinea
from tests.conftest import id_punto_venta


class FuenteFalsa:
    """Fuente de prueba: emite las líneas dadas y opcionalmente revienta."""

    nombre = "fuente-de-revision"

    def __init__(self, lineas: list[LineaVenta], reventar_en: int | None = None) -> None:
        self._lineas = lineas
        self._reventar_en = reventar_en
        self.rechazos: list[object] = []

    def obtener_ventas(
        self, desde: date, hasta: date, centros: Sequence[str] | None = None
    ) -> Iterator[LineaVenta]:
        for indice, linea in enumerate(self._lineas):
            if self._reventar_en is not None and indice == self._reventar_en:
                raise RuntimeError("SIESA cortó la conexión a mitad de la descarga")
            yield linea


def _linea(centro: str, dia: int, valor: str, fila: int) -> LineaVenta:
    return LineaVenta(
        centro_operacion=centro,
        fecha=date(2026, 8, dia),
        valor_subtotal=Decimal(valor),
        costo_promedio=Decimal("0"),
        cantidad_inv=Decimal("0"),
        categoria_siesa="0001 - RES",
        nit_cliente="900123456",
        razon_social="CLIENTE",
        margen_siesa=None,
        domicilio="No",
        clase_cliente="002 - CLIENTES NACIONALES",
        condicion_pago="CON",
        fila_origen=fila,
    )


def _total(sesion: Session, centro: str, dia: int) -> Decimal:
    return sesion.scalar(
        select(func.coalesce(func.sum(VentaLinea.valor_subtotal), 0)).where(
            VentaLinea.punto_venta_id == id_punto_venta(sesion, centro),
            VentaLinea.fecha == date(2026, 8, dia),
        )
    )


@pytest.fixture
def ingesta_con(monkeypatch: pytest.MonkeyPatch) -> object:
    def _montar(lineas: list[LineaVenta], reventar_en: int | None = None) -> FuenteFalsa:
        fuente = FuenteFalsa(lineas, reventar_en)
        monkeypatch.setattr(ingesta_service, "obtener_fuente", lambda *_a, **_k: fuente)
        return fuente

    return _montar


def test_reprocesar_no_duplica_ni_borra_de_mas(
    sesion: Session,
    estructura: None,
    ingesta_con,  # type: ignore[no-untyped-def]
) -> None:
    """Comportamiento correcto que conviene NO tocar.

    Se carga el 5 de agosto para MALAMBO y LAGRANJA; luego se reprocesa un
    archivo que solo trae MALAMBO. El día de MALAMBO se reemplaza entero y el de
    LAGRANJA queda intacto.
    """
    ingesta_con([_linea("402", 5, "100", 2), _linea("403", 5, "200", 3)])
    IngestaService(sesion).ejecutar(date(2026, 8, 1), date(2026, 8, 31), FuenteIngesta.EXCEL)
    sesion.commit()

    ingesta_con([_linea("402", 5, "999", 2)])
    IngestaService(sesion).ejecutar(date(2026, 8, 1), date(2026, 8, 31), FuenteIngesta.EXCEL)
    sesion.commit()

    print()
    print(f"  MALAMBO 5-ago  : {_total(sesion, '402', 5)}  (esperado 999)")
    print(f"  LAGRANJA 5-ago : {_total(sesion, '403', 5)}  (esperado 200)")

    assert _total(sesion, "402", 5) == Decimal("999.00")
    assert _total(sesion, "403", 5) == Decimal("200.00")


def test_corrida_fallida_a_media_carga_no_deja_el_dia_borrado(
    sesion: Session,
    estructura: None,
    ingesta_con,  # type: ignore[no-untyped-def]
) -> None:
    """Una corrida que revienta a mitad no puede dejar un día borrado y sin reponer.

    Escenario: hay 100 cargados para MALAMBO el 5 de agosto. Se lanza un
    reproceso de 2 500 líneas —más de un lote de `TAMANO_LOTE`— que revienta en
    la línea 2 100, después de que el primer lote ya borrara e insertara.
    """
    ingesta_con([_linea("402", 5, "100", 2)])
    IngestaService(sesion).ejecutar(date(2026, 8, 1), date(2026, 8, 31), FuenteIngesta.EXCEL)
    sesion.commit()
    assert _total(sesion, "402", 5) == Decimal("100.00")

    muchas = [_linea("402", 5, "1", 2 + n) for n in range(2500)]
    ingesta_con(muchas, reventar_en=2100)
    salida = IngestaService(sesion).ejecutar(
        date(2026, 8, 1), date(2026, 8, 31), FuenteIngesta.EXCEL
    )
    sesion.commit()

    print()
    print(f"  estado de la corrida : {salida.estado}")
    print(f"  leidas/aceptadas     : {salida.filas_leidas}/{salida.aceptadas}")
    print(f"  MALAMBO 5-ago tras el fallo : {_total(sesion, '402', 5)}  (esperado 100)")

    assert _total(sesion, "402", 5) == Decimal("100.00"), "el SAVEPOINT no repuso el día"


def test_dos_cargas_del_mismo_dia_en_la_misma_corrida(
    sesion: Session,
    estructura: None,
    ingesta_con,  # type: ignore[no-untyped-def]
) -> None:
    """El borrado por par ocurre una sola vez por corrida, aunque el archivo
    traiga el mismo (fecha, PDV) repartido en varios lotes.

    Escenario: 3 000 líneas del mismo día y punto de venta, es decir dos lotes.
    Si el segundo lote volviera a borrar, se perderían las 2 000 primeras.
    """
    ingesta_con([_linea("402", 5, "1", 2 + n) for n in range(3000)])
    salida = IngestaService(sesion).ejecutar(
        date(2026, 8, 1), date(2026, 8, 31), FuenteIngesta.EXCEL
    )
    sesion.commit()

    filas = sesion.scalar(
        select(func.count())
        .select_from(VentaLinea)
        .where(VentaLinea.punto_venta_id == id_punto_venta(sesion, "402"))
    )
    print()
    print(
        f"  aceptadas={salida.aceptadas}  filas en base={filas}  total={_total(sesion, '402', 5)}"
    )
    assert filas == 3000
    assert _total(sesion, "402", 5) == Decimal("3000.00")
