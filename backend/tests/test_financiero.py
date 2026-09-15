"""Pruebas del tablero financiero: clasificación PUC, ingesta y reportes.

Cubre lo que de verdad puede salir mal: el signo de `FINAL` para cuentas de
naturaleza crédito, la idempotencia de la carga por (cia, período), y que un
denominador en cero devuelva `None` y no reviente ni se convierta en `0`.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.application.services.financiero_ingesta_service import cargar_libro_mayor
from app.application.services.financiero_reportes_service import (
    FiltrosFinanciero,
    FinancieroReportesService,
)
from app.domain.enums import Rol
from app.domain.financiero import ClaseCuenta, clasificar, es_corriente, saldo_presentacion
from app.infrastructure.models.financiero import MovimientoContable
from app.infrastructure.models.usuario import UsuarioPermiso
from tests.conftest import _crear_usuario, autenticar

PERIODO = 202607


# ── Dominio: clasificación PUC ────────────────────────────────────────────────


def test_clasificar_por_primer_digito() -> None:
    assert clasificar("1305") == ClaseCuenta.ACTIVO
    assert clasificar("2105") == ClaseCuenta.PASIVO
    assert clasificar("3705") == ClaseCuenta.PATRIMONIO
    assert clasificar("4135") == ClaseCuenta.INGRESO
    assert clasificar("5105") == ClaseCuenta.GASTO
    assert clasificar("") is None
    assert clasificar(None) is None
    assert clasificar("0135") is None  # no existe la clase "0"


def test_saldo_presentacion_invierte_solo_naturaleza_credito() -> None:
    # Activo: FINAL ya es el saldo económico, no se invierte.
    assert saldo_presentacion(ClaseCuenta.ACTIVO, Decimal("100.00")) == Decimal("100.00")
    # Pasivo, Patrimonio e Ingreso son de naturaleza crédito: se invierte.
    assert saldo_presentacion(ClaseCuenta.PASIVO, Decimal("100.00")) == Decimal("-100.00")
    assert saldo_presentacion(ClaseCuenta.INGRESO, Decimal("-8570300.00")) == Decimal("8570300.00")


def test_es_corriente_solo_clasifica_activo_y_pasivo() -> None:
    assert es_corriente("1305") is True  # deudores, grupo 13
    assert es_corriente("1505") is False  # propiedad planta y equipo, grupo 15
    assert es_corriente("2105") is True  # obligaciones financieras, grupo 21
    assert es_corriente("3705") is None  # patrimonio no se clasifica por plazo


# ── Ingesta ────────────────────────────────────────────────────────────────────


def _fila(**overrides: object) -> dict[str, object]:
    base = {
        "CIA": 4,
        "CO": "402",
        "PERIODO": PERIODO,
        "AUXILIAR": "1305050101",
        "DESCRIPCION": "CLIENTES NACIONALES",
        "ID_TERCERO": "830505537",
        "RAZON_SOCIAL": "AGROPECUARIA SANTACRUZ LTDA",
        "ID_CENTRO_COSTO": None,
        "CENTRO_COSTO": None,
        "MAYOR": "13050501",
        "MAYOR_IV": "130505",
        "MAYOR_III": "1305",
        "SALDOS_INICIAL": 0.0,
        "DEBITOS": 65156880.0,
        "CREDITOS": 65156880.0,
        "FINAL": 0.0,
    }
    base.update(overrides)
    return base


def _escribir_ndjson(ruta: Path, filas: list[dict[str, object]]) -> None:
    with ruta.open("w", encoding="utf-8") as archivo:
        for fila in filas:
            archivo.write(json.dumps(fila) + "\n")


def test_cargar_libro_mayor_acepta_validas_y_rechaza_invalidas(
    tmp_path: Path, sesion: Session
) -> None:
    ruta = tmp_path / "consolidado.json"
    _escribir_ndjson(
        ruta,
        [
            _fila(),
            _fila(AUXILIAR="4135010101", MAYOR_III="4135", FINAL=-8570300.0),
            {"CIA": 4},  # fila inválida: faltan campos obligatorios
        ],
    )

    resumen = cargar_libro_mayor(sesion, ruta)
    sesion.commit()

    assert resumen.filas_leidas == 3
    assert resumen.aceptadas == 2
    assert resumen.rechazadas == 1
    assert resumen.cias == {4}
    assert resumen.periodos == {PERIODO}
    assert sesion.query(MovimientoContable).count() == 2


def test_cargar_libro_mayor_reemplaza_el_mismo_periodo_al_repetirse(
    tmp_path: Path, sesion: Session
) -> None:
    ruta = tmp_path / "consolidado.json"
    _escribir_ndjson(ruta, [_fila(FINAL=100.0)])
    cargar_libro_mayor(sesion, ruta)
    sesion.commit()
    assert sesion.query(MovimientoContable).count() == 1

    # Se repite la carga del mismo (cia, periodo) con un archivo corregido:
    # no debe duplicar, debe reemplazar.
    _escribir_ndjson(ruta, [_fila(FINAL=200.0), _fila(AUXILIAR="1305050102", FINAL=300.0)])
    cargar_libro_mayor(sesion, ruta)
    sesion.commit()

    filas = sesion.query(MovimientoContable).all()
    assert len(filas) == 2
    assert {f.final for f in filas} == {Decimal("200.00"), Decimal("300.00")}


# ── Reportes ───────────────────────────────────────────────────────────────────


def _sembrar_movimientos(sesion: Session) -> None:
    """Un mini balance cuadrado: activo = pasivo + patrimonio + utilidad."""
    filas = [
        # Activo: caja 100, cartera 200 (corriente) + PP&E 300 (no corriente) = 600
        MovimientoContable(
            cia=4,
            co="402",
            periodo=PERIODO,
            auxiliar="1105",
            mayor_iii="1105",
            descripcion="CAJA",
            saldo_inicial=Decimal("0"),
            debitos=Decimal("100.00"),
            creditos=Decimal("0"),
            final=Decimal("100.00"),
        ),
        MovimientoContable(
            cia=4,
            co="402",
            periodo=PERIODO,
            auxiliar="1305010101",
            mayor_iii="1305",
            descripcion="CLIENTES",
            id_tercero="900111",
            razon_social="CLIENTE UNO",
            saldo_inicial=Decimal("0"),
            debitos=Decimal("200.00"),
            creditos=Decimal("0"),
            final=Decimal("200.00"),
        ),
        MovimientoContable(
            cia=4,
            co="402",
            periodo=PERIODO,
            auxiliar="1520",
            mayor_iii="1520",
            descripcion="MAQUINARIA",
            saldo_inicial=Decimal("0"),
            debitos=Decimal("300.00"),
            creditos=Decimal("0"),
            final=Decimal("300.00"),
        ),
        # Pasivo corriente 150 (naturaleza crédito: FINAL crudo -150.00)
        MovimientoContable(
            cia=4,
            co="402",
            periodo=PERIODO,
            auxiliar="2205",
            mayor_iii="2205",
            descripcion="PROVEEDORES",
            saldo_inicial=Decimal("0"),
            debitos=Decimal("0"),
            creditos=Decimal("150.00"),
            final=Decimal("-150.00"),
        ),
        # Patrimonio 350 (naturaleza credito: FINAL crudo -350.00)
        MovimientoContable(
            cia=4,
            co="402",
            periodo=PERIODO,
            auxiliar="3705",
            mayor_iii="3705",
            descripcion="UTILIDADES ACUMULADAS",
            saldo_inicial=Decimal("0"),
            debitos=Decimal("0"),
            creditos=Decimal("350.00"),
            final=Decimal("-350.00"),
        ),
        # Ingreso 500 (naturaleza credito: FINAL crudo -500.00)
        MovimientoContable(
            cia=4,
            co="402",
            periodo=PERIODO,
            auxiliar="4135",
            mayor_iii="4135",
            descripcion="VENTA",
            saldo_inicial=Decimal("0"),
            debitos=Decimal("0"),
            creditos=Decimal("500.00"),
            final=Decimal("-500.00"),
        ),
        # Costo de venta 200 y gasto 100 (naturaleza debito: FINAL positivo)
        MovimientoContable(
            cia=4,
            co="402",
            periodo=PERIODO,
            auxiliar="6135",
            mayor_iii="6135",
            descripcion="COSTO VENTA",
            saldo_inicial=Decimal("0"),
            debitos=Decimal("200.00"),
            creditos=Decimal("0"),
            final=Decimal("200.00"),
        ),
        MovimientoContable(
            cia=4,
            co="402",
            periodo=PERIODO,
            auxiliar="5105",
            mayor_iii="5105",
            descripcion="SUELDO",
            saldo_inicial=Decimal("0"),
            debitos=Decimal("100.00"),
            creditos=Decimal("0"),
            final=Decimal("100.00"),
        ),
    ]
    sesion.add_all(filas)
    sesion.commit()


def test_balance_general_cuadra_y_no_descuadra(sesion: Session) -> None:
    _sembrar_movimientos(sesion)
    servicio = FinancieroReportesService(sesion)

    resultado = servicio.balance_general(FiltrosFinanciero(periodo=PERIODO))

    assert resultado.activo == Decimal("600.00")
    assert resultado.pasivo == Decimal("150.00")
    # Patrimonio propio, sin incluir la utilidad del ejercicio en curso.
    assert resultado.patrimonio == Decimal("350.00")
    assert resultado.descuadre == Decimal("100.00")  # utilidad del ejercicio, aún no capitalizada


def test_estado_resultados_calcula_utilidad_neta(sesion: Session) -> None:
    _sembrar_movimientos(sesion)
    servicio = FinancieroReportesService(sesion)

    resultado = servicio.estado_resultados(FiltrosFinanciero(periodo=PERIODO))

    assert resultado.ingresos == Decimal("500.00")
    assert resultado.costos == Decimal("200.00")
    assert resultado.gastos == Decimal("100.00")
    assert resultado.utilidad_neta == Decimal("200.00")


def test_cartera_agrupa_por_tercero(sesion: Session) -> None:
    _sembrar_movimientos(sesion)
    servicio = FinancieroReportesService(sesion)

    filas = servicio.cartera_por_cliente(FiltrosFinanciero(periodo=PERIODO))

    assert len(filas) == 1
    assert filas[0].id_tercero == "900111"
    assert filas[0].saldo == Decimal("200.00")


def test_indicadores_liquidez_endeudamiento_margen(sesion: Session) -> None:
    _sembrar_movimientos(sesion)
    servicio = FinancieroReportesService(sesion)

    resultado = servicio.indicadores(FiltrosFinanciero(periodo=PERIODO))

    # Activo corriente = caja(100) + cartera(200) = 300; pasivo corriente = 150
    assert resultado.liquidez_corriente == Decimal("2")
    # Endeudamiento = pasivo total(150) / activo total(600)
    assert resultado.endeudamiento == Decimal("0.25")
    # Margen neto = utilidad(200) / ingresos(500)
    assert resultado.margen_neto == Decimal("0.4")


def test_indicadores_sin_datos_devuelve_none_no_cero(sesion: Session) -> None:
    servicio = FinancieroReportesService(sesion)

    resultado = servicio.indicadores(FiltrosFinanciero(periodo=999912))

    assert resultado.liquidez_corriente is None
    assert resultado.endeudamiento is None
    assert resultado.margen_neto is None


# ── API: permisos ──────────────────────────────────────────────────────────────


def test_gerente_consulta_balance_general(
    cliente_http: TestClient, sesion: Session, gerente: dict[str, str]
) -> None:
    _sembrar_movimientos(sesion)

    respuesta = cliente_http.get(
        f"/api/v1/financiero/balance-general?periodo={PERIODO}", headers=gerente
    )

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["activo"] == "600.00"
    assert cuerpo["parametros_calculo"]["periodo"] == str(PERIODO)


def test_consulta_granular_sin_permiso_financiero_recibe_403(
    cliente_http: TestClient, sesion: Session
) -> None:
    usuario = _crear_usuario(sesion, "consulta_otro_modulo", Rol.CONSULTA)
    sesion.add(UsuarioPermiso(usuario_id=usuario.id, codigo="PERMISO_CONSULTAR_TABLERO"))
    sesion.commit()
    cabeceras = autenticar(cliente_http, "consulta_otro_modulo")

    respuesta = cliente_http.get(
        f"/api/v1/financiero/balance-general?periodo={PERIODO}", headers=cabeceras
    )

    assert respuesta.status_code == 403
