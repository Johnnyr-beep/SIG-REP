"""Revisión: alcance por usuario, filtros y cuadre consolidado/grupos."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.application.services.reportes_service import FiltrosReporte, ReportesService
from app.core.security import hashear_password
from app.domain.enums import AgrupacionClientes, Rol
from app.infrastructure.models.organizacion import Grupo, PuntoVenta
from app.infrastructure.models.usuario import Usuario, UsuarioPuntoVenta
from app.infrastructure.models.venta import Cliente, VentaLinea
from tests.conftest import (
    CLAVE,
    PERIODO,
    autenticar,
    dar_presupuesto,
    dar_venta,
    id_categoria,
    id_periodo,
    id_punto_venta,
)


def _jefe_pdv(sesion: Session, cliente_http: TestClient, codigos: list[str]) -> dict[str, str]:
    usuario = Usuario(
        usuario="jefe",
        nombre="Jefe",
        password_hash=hashear_password(CLAVE),
        rol=Rol.JEFE_PDV.value,
        activo=True,
        debe_cambiar_password=False,
    )
    sesion.add(usuario)
    sesion.flush()
    for codigo in codigos:
        sesion.add(
            UsuarioPuntoVenta(usuario_id=usuario.id, punto_venta_id=id_punto_venta(sesion, codigo))
        )
    sesion.commit()
    return autenticar(cliente_http, "jefe")


def test_jefe_pdv_ve_la_venta_de_un_punto_fuera_de_su_alcance(
    sesion: Session, cliente_http: TestClient
) -> None:
    """`sin_presupuesto` no se filtra por alcance.

    Escenario: un JEFE_PDV con alcance solo sobre MALAMBO (402) pide el tablero.
    En la respuesta viaja la venta completa de 432 EVENTOS BUCARAMANGA, un punto
    de venta sobre el que no tiene ningún alcance.
    """
    dar_presupuesto(sesion, "402", "RES", "1000000000")
    dar_venta(sesion, "402", "RES", 5, "100000000")
    dar_venta(sesion, "432", "RES", 5, "777777777")

    cabeceras = _jefe_pdv(sesion, cliente_http, ["402"])
    datos = cliente_http.get(
        "/api/v1/reportes/tablero",
        params={"periodo": PERIODO, "hasta": "2026-08-15"},
        headers=cabeceras,
    ).json()

    print()
    print(f"  filas de PDV visibles : {[g['codigo'] for g in datos['grupos']]}")
    print(f"  sin_presupuesto       : {datos['sin_presupuesto']}")

    assert datos["sin_presupuesto"] == [], (
        "un JEFE_PDV no debería recibir la venta de un punto fuera de su alcance"
    )


def test_reporte_de_clientes_ignora_el_filtro_de_categoria(
    sesion: Session, estructura: None
) -> None:
    """`docs/API.md`: «Todos aceptan los mismos filtros … `categoria`».

    Escenario: MALAMBO vende 100 M en RES y 900 M en CERDO. Se pide el reporte de
    clientes filtrando `categoria=RES`. Debería devolver 100 M; devuelve 1 000 M.
    """
    dar_venta(sesion, "402", "RES", 5, "100000000")
    dar_venta(sesion, "402", "CERDO", 5, "900000000")

    filas = (
        ReportesService(sesion)
        .clientes(
            FiltrosReporte(periodo=PERIODO, hasta=date(2026, 8, 15), categoria="RES"),
            AgrupacionClientes.CLIENTE,
        )
        .filas
    )
    total = sum(Decimal(f.venta) for f in filas)

    print()
    print(f"  venta devuelta con categoria=RES : {total}")
    print("  venta real de RES                : 100000000.00")

    assert total == Decimal("100000000.00")


def test_participacion_se_calcula_sobre_el_top_n_no_sobre_el_total(
    sesion: Session, estructura: None
) -> None:
    """`participacion` se divide entre la venta de las filas **ya truncadas**.

    Escenario: seis clientes, tope de 2 filas. La primera fila representa el
    45 % de la venta real de la compañía y el reporte la publica como 60 %.
    """
    periodo_id = id_periodo(sesion)
    punto_id = id_punto_venta(sesion, "402")
    categoria_id = id_categoria(sesion, "RES")
    for indice, importe in enumerate(["900", "600", "300", "100", "100", "100"]):
        cliente = Cliente(nit=f"NIT{indice}", razon_social=f"CLIENTE {indice}")
        sesion.add(cliente)
        sesion.flush()
        sesion.add(
            VentaLinea(
                periodo_id=periodo_id,
                fecha=date(2026, 8, 5),
                punto_venta_id=punto_id,
                categoria_id=categoria_id,
                cliente_id=cliente.id,
                nit_cliente=f"NIT{indice}",
                valor_subtotal=Decimal(importe) * 1000000,
                costo_promedio=Decimal(0),
                cantidad_inv=Decimal(0),
            )
        )
    sesion.commit()

    servicio = ReportesService(sesion)
    servicio._settings = servicio._settings.model_copy(update={"max_filas_reporte_clientes": 2})
    respuesta = servicio.clientes(
        FiltrosReporte(periodo=PERIODO, hasta=date(2026, 8, 15)), AgrupacionClientes.CLIENTE
    )

    print()
    for fila in respuesta.filas:
        print(f"  {fila.nombre}: venta={fila.venta} participacion={fila.participacion}")
    print("  venta real de la compañía: 2100000000  →  la primera fila es el 0.4286")

    assert Decimal(respuesta.filas[0].participacion) == Decimal("0.4286")


def test_el_consolidado_no_cuadra_con_la_suma_de_los_grupos(
    sesion: Session, estructura: None
) -> None:
    """Un grupo desactivado desaparece del comparativo pero sigue en el consolidado.

    Escenario: gerencia desactiva GRUPO 4 en catálogos (una operación de
    catálogo, no de reporte). El tablero sigue sumando sus 4 puntos de venta en
    el consolidado, pero ya no publica su fila. La suma de las cuatro filas
    visibles deja de cuadrar con el total y nadie ve por qué.
    """
    dar_presupuesto(sesion, "402", "RES", "1000000000")
    dar_presupuesto(sesion, "407", "RES", "1000000000")
    dar_venta(sesion, "402", "RES", 5, "400000000")
    dar_venta(sesion, "407", "RES", 5, "600000000")

    grupo4 = sesion.scalars(select(Grupo).where(Grupo.codigo == "004")).one()
    grupo4.activo = False
    sesion.commit()

    tablero = ReportesService(sesion).tablero(
        FiltrosReporte(periodo=PERIODO, hasta=date(2026, 8, 15))
    )
    suma_grupos = sum(Decimal(g.venta) for g in tablero.grupos)

    print()
    print(f"  venta consolidada     : {tablero.consolidado.venta}")
    print(f"  suma de los grupos    : {suma_grupos}")
    print(f"  grupos publicados     : {[g.codigo for g in tablero.grupos]}")

    assert suma_grupos == Decimal(tablero.consolidado.venta)


def test_la_venta_de_un_pdv_desactivado_desaparece_del_reporte(
    sesion: Session, estructura: None
) -> None:
    """§7: «La venta de un PDV sin presupuesto se reporta aparte; nunca se descarta».

    Escenario: se desactiva CONCORDE (603) en catálogos —cierre de local a mitad
    de mes— pero sus ventas del mes ya están ingeridas. `_puntos_visibles` exige
    `activo = True`, y `_agregar_venta_sin_presupuesto` exige
    `presupuestado = False`. CONCORDE no cumple ninguna de las dos: sus
    500 millones se evaporan del consolidado y del bloque `sin_presupuesto`.
    """
    dar_presupuesto(sesion, "402", "RES", "1000000000")
    dar_venta(sesion, "402", "RES", 5, "400000000")
    dar_venta(sesion, "603", "RES", 5, "500000000")

    punto = sesion.scalars(select(PuntoVenta).where(PuntoVenta.codigo_co == "603")).one()
    punto.activo = False
    sesion.commit()

    tablero = ReportesService(sesion).tablero(
        FiltrosReporte(periodo=PERIODO, hasta=date(2026, 8, 15))
    )
    total_venta_real = sesion.scalar(select(func.sum(VentaLinea.valor_subtotal)))

    print()
    print(f"  venta consolidada         : {tablero.consolidado.venta}")
    print(f"  bloque sin_presupuesto    : {tablero.sin_presupuesto}")
    print("  venta ingerida en la base : 900000000.00")

    assert Decimal(tablero.consolidado.venta) + sum(
        Decimal(f.venta) for f in tablero.sin_presupuesto
    ) == Decimal("900000000.00"), "la venta de 603 no aparece por ningún lado"
    assert total_venta_real == Decimal("900000000.00")
