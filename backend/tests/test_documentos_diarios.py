"""Número de documentos diarios: fuente, sincronización y su columna en el
reporte de venta diaria (§4.4).

Ninguna prueba toca la red: la API de `facturas-pdv-resumen` se simula con
`httpx.MockTransport`, mismo patrón que `test_fuente_siesa.py`.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import httpx
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.services.documentos_diarios_service import (
    sincronizar_documentos_diarios,
)
from app.application.services.reportes_service import FiltrosReporte, ReportesService
from app.infrastructure.fuentes.facturas_siesa import (
    RUTA_FACTURAS_PDV_RESUMEN,
    FuenteFacturasSiesa,
)
from app.infrastructure.fuentes.siesa import ConfiguracionSiesa
from app.infrastructure.models.documentos import NumeroDocumentosDiarios
from app.infrastructure.models.venta import VentaLinea
from tests.conftest import id_categoria, id_periodo, id_punto_venta

D = Decimal

ENCABEZADO = "id_cia,compania,id_co,punto_venta,id_bodega,bodega,fecha,documentos"


def _fila(id_co: str, documentos: int, fecha: str = "2026-08-01", bodega: str = "01") -> str:
    return f"4,CARNES SANTACRUZ S.A.S,{id_co},PDV,{id_co}{bodega},BODEGA,{fecha},{documentos}"


def _csv(*filas: str) -> str:
    return "\n".join((ENCABEZADO, *filas)) + "\n"


def _configuracion(**extra: object) -> ConfiguracionSiesa:
    parametros: dict[str, object] = {
        "url_base": "https://apiconsulta.pruebas.local",
        "token": SecretStr("token-de-pruebas"),
        "espera_reintento_seg": 0.0,
        "companias": (4,),
    }
    parametros.update(extra)
    return ConfiguracionSiesa(**parametros)  # type: ignore[arg-type]


def _fuente_con(cuerpo: str) -> FuenteFacturasSiesa:
    def _manejar(peticion: httpx.Request) -> httpx.Response:
        assert peticion.url.path == RUTA_FACTURAS_PDV_RESUMEN
        return httpx.Response(200, text=cuerpo)

    return FuenteFacturasSiesa(
        configuracion=_configuracion(),
        sesion_http=httpx.Client(transport=httpx.MockTransport(_manejar)),
    )


# ── FuenteFacturasSiesa ────────────────────────────────────────────────────────


def test_lee_documentos_por_pdv_y_fecha() -> None:
    csv = _csv(
        _fila("402", 5, "2026-08-01"),
        _fila("406", 3, "2026-08-01"),
        _fila("402", 2, "2026-08-02"),
    )
    fuente = _fuente_con(csv)

    conteos = fuente.contar_documentos(date(2026, 8, 1), date(2026, 8, 2))

    assert conteos[("402", date(2026, 8, 1))] == 5
    assert conteos[("406", date(2026, 8, 1))] == 3
    assert conteos[("402", date(2026, 8, 2))] == 2


def test_suma_varias_bodegas_del_mismo_pdv_y_fecha() -> None:
    """Un PDV que factura desde dos bodegas el mismo día trae dos filas; se suman."""
    csv = _csv(
        _fila("402", 5, "2026-08-01", bodega="01"),
        _fila("402", 3, "2026-08-01", bodega="02"),
    )
    fuente = _fuente_con(csv)

    conteos = fuente.contar_documentos(date(2026, 8, 1), date(2026, 8, 1))

    assert conteos[("402", date(2026, 8, 1))] == 8


def test_id_co_se_normaliza_a_tres_cifras() -> None:
    csv = _csv(_fila("6", 1, "2026-08-01"))
    fuente = _fuente_con(csv)

    conteos = fuente.contar_documentos(date(2026, 8, 1), date(2026, 8, 1))

    assert ("006", date(2026, 8, 1)) in conteos


def test_una_sola_peticion_con_id_cia_separado_por_comas() -> None:
    """Medido (16-sep-2026): `id_cia` acepta una lista `4,6,7` en una sola
    petición, sin tener que pedir una vez por compañía."""
    peticiones: list[httpx.Request] = []

    def _manejar(peticion: httpx.Request) -> httpx.Response:
        peticiones.append(peticion)
        return httpx.Response(
            200,
            text=_csv(
                _fila("402", 1, "2026-08-01"),  # compañía 4
                _fila("605", 1, "2026-08-01"),  # compañía 6
                _fila("701", 1, "2026-08-01"),  # compañía 7
            ),
        )

    fuente = FuenteFacturasSiesa(
        configuracion=_configuracion(companias=(4, 6, 7)),
        sesion_http=httpx.Client(transport=httpx.MockTransport(_manejar)),
    )

    conteos = fuente.contar_documentos(date(2026, 8, 1), date(2026, 8, 1))

    assert len(peticiones) == 1
    assert peticiones[0].url.params["id_cia"] == "4,6,7"
    assert set(conteos) == {
        ("402", date(2026, 8, 1)),
        ("605", date(2026, 8, 1)),
        ("701", date(2026, 8, 1)),
    }


# ── sincronizar_documentos_diarios ────────────────────────────────────────────


class _FuenteFalsa:
    def __init__(self, conteos: dict[tuple[str, date], int]) -> None:
        self._conteos = conteos

    def contar_documentos(self, desde: date, hasta: date) -> dict[tuple[str, date], int]:
        return self._conteos


def test_sincronizar_documentos_resuelve_pdv_y_guarda(sesion: Session, estructura: None) -> None:
    malambo = id_punto_venta(sesion, "402")
    fuente = _FuenteFalsa({("402", date(2026, 8, 1)): 37})

    resumen = sincronizar_documentos_diarios(sesion, fuente, date(2026, 8, 1), date(2026, 8, 1))
    sesion.commit()

    assert resumen.filas_guardadas == 1
    assert resumen.puntos_reconocidos == 1
    fila = sesion.scalars(select(NumeroDocumentosDiarios)).one()
    assert fila.punto_venta_id == malambo
    assert fila.cantidad == 37


def test_sincronizar_documentos_anota_codigos_desconocidos(
    sesion: Session, estructura: None
) -> None:
    fuente = _FuenteFalsa({("999", date(2026, 8, 1)): 5})

    resumen = sincronizar_documentos_diarios(sesion, fuente, date(2026, 8, 1), date(2026, 8, 1))

    assert resumen.filas_guardadas == 0
    assert resumen.puntos_desconocidos == {"999"}


def test_sincronizar_documentos_reemplaza_el_mismo_rango(sesion: Session, estructura: None) -> None:
    fuente_vieja = _FuenteFalsa({("402", date(2026, 8, 1)): 10})
    sincronizar_documentos_diarios(sesion, fuente_vieja, date(2026, 8, 1), date(2026, 8, 1))
    sesion.commit()

    fuente_nueva = _FuenteFalsa({("402", date(2026, 8, 1)): 25})
    sincronizar_documentos_diarios(sesion, fuente_nueva, date(2026, 8, 1), date(2026, 8, 1))
    sesion.commit()

    filas = sesion.scalars(select(NumeroDocumentosDiarios)).all()
    assert len(filas) == 1
    assert filas[0].cantidad == 25


# ── Columna en el reporte de venta diaria ─────────────────────────────────────


def test_venta_diaria_incluye_documentos_por_dia(sesion: Session, estructura: None) -> None:
    periodo_id = id_periodo(sesion)
    malambo = id_punto_venta(sesion, "402")
    categoria_id = id_categoria(sesion, "RES")

    sesion.add(
        VentaLinea(
            periodo_id=periodo_id,
            punto_venta_id=malambo,
            categoria_id=categoria_id,
            fecha=date(2026, 8, 1),
            valor_subtotal=D("100000.00"),
            cantidad_inv=D("10.000"),
        )
    )
    sesion.add(
        NumeroDocumentosDiarios(
            punto_venta_id=malambo, fecha=date(2026, 8, 1), cantidad=12, origen="siesa"
        )
    )
    sesion.commit()

    servicio = ReportesService(sesion)
    respuesta = servicio.venta_diaria(FiltrosReporte(periodo="2026-08", puntos_venta=("402",)))

    fila = next(f for f in respuesta.filas if f.punto_venta == "402")
    indice_dia_1 = respuesta.fechas.index(date(2026, 8, 1))
    assert fila.documentos[indice_dia_1] == 12
    assert respuesta.totales.documentos[indice_dia_1] == 12
    # Un día sin conteo sincronizado es `None`, no cero.
    indice_dia_2 = respuesta.fechas.index(date(2026, 8, 2))
    assert fila.documentos[indice_dia_2] is None


# ── Programador en segundo plano ──────────────────────────────────────────────


def test_intervalo_de_una_hora() -> None:
    from app.infrastructure.programador_documentos import INTERVALO_HORAS

    assert INTERVALO_HORAS == 1


def test_tomar_turno_sin_candado_en_sqlite(sesion: Session, estructura: None) -> None:
    from app.infrastructure.programador_documentos import _tomar_turno

    assert _tomar_turno(sesion, "carnes") is True
    assert _tomar_turno(sesion, "carnes") is True  # sin candado, no hay exclusión que probar


def test_iniciar_programador_documentos_sin_token(monkeypatch) -> None:
    from app.core.config import obtener_settings
    from app.infrastructure.programador_documentos import iniciar_programador_documentos

    monkeypatch.delenv("SIGREP_SIESA_TOKEN", raising=False)
    obtener_settings.cache_clear()
    try:
        assert iniciar_programador_documentos() is None
    finally:
        obtener_settings.cache_clear()
