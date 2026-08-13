"""Fijaciones comunes de las pruebas.

Las variables de entorno se fijan **antes** de importar nada de `app`: el motor
de base de datos se construye al importar `app.core.db`, así que un import
adelantado dejaría las pruebas apuntando a la base real.
"""

from __future__ import annotations

import os
from collections.abc import Iterator, Sequence
from datetime import date
from decimal import Decimal

os.environ.setdefault("SIGREP_SECRET_KEY", "clave-de-pruebas-suficientemente-larga-1234567890")
os.environ.setdefault("SIGREP_DB_URL_OVERRIDE", "sqlite://")
os.environ.setdefault("SIGREP_ENTORNO", "pruebas")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import Base, SessionLocal, engine
from app.core.security import hashear_password
from app.domain.enums import Rol
from app.infrastructure.models.catalogo import Categoria
from app.infrastructure.models.organizacion import PuntoVenta
from app.infrastructure.models.periodo import Periodo
from app.infrastructure.models.presupuesto import Presupuesto
from app.infrastructure.models.usuario import Usuario, UsuarioPuntoVenta
from app.infrastructure.models.venta import VentaLinea
from app.infrastructure.semilla import sembrar_calendario, sembrar_estructura
from app.main import app

PERIODO = "2026-08"
CLAVE = "Clave-De-Pruebas-2026"


@pytest.fixture(autouse=True)
def base_limpia() -> Iterator[None]:
    """Esquema nuevo por prueba. Aísla: ninguna prueba hereda datos de otra."""
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def sesion() -> Iterator[Session]:
    with SessionLocal() as s:
        yield s


@pytest.fixture
def estructura(sesion: Session) -> None:
    """Los datos reales de §3: grupos, puntos de venta, categorías y zonas."""
    sembrar_estructura(sesion)
    sembrar_calendario(sesion, PERIODO)
    sesion.commit()


def _crear_usuario(
    sesion: Session, usuario: str, rol: Rol, codigos_punto_venta: Sequence[str] = ()
) -> Usuario:
    registro = Usuario(
        usuario=usuario,
        nombre=usuario.title(),
        email=f"{usuario}@pruebas.local",
        password_hash=hashear_password(CLAVE),
        rol=rol.value,
        activo=True,
        debe_cambiar_password=False,
    )
    sesion.add(registro)
    sesion.flush()
    for codigo in codigos_punto_venta:
        sesion.add(
            UsuarioPuntoVenta(usuario_id=registro.id, punto_venta_id=id_punto_venta(sesion, codigo))
        )
    sesion.commit()
    return registro


@pytest.fixture
def cliente_http(estructura: None) -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


def autenticar(cliente: TestClient, usuario: str) -> dict[str, str]:
    """Devuelve la cabecera `Authorization` de un usuario ya creado."""
    respuesta = cliente.post("/api/v1/auth/acceso", json={"usuario": usuario, "clave": CLAVE})
    assert respuesta.status_code == 200, respuesta.text
    return {"Authorization": f"Bearer {respuesta.json()['token_acceso']}"}


@pytest.fixture
def gerente(sesion: Session, cliente_http: TestClient) -> dict[str, str]:
    _crear_usuario(sesion, "gerente", Rol.GERENTE)
    return autenticar(cliente_http, "gerente")


@pytest.fixture
def analista(sesion: Session, cliente_http: TestClient) -> dict[str, str]:
    _crear_usuario(sesion, "analista", Rol.ANALISTA)
    return autenticar(cliente_http, "analista")


@pytest.fixture
def consulta(sesion: Session, cliente_http: TestClient) -> dict[str, str]:
    _crear_usuario(sesion, "consulta", Rol.CONSULTA)
    return autenticar(cliente_http, "consulta")


#: Punto de venta del jefe de las pruebas y punto de un compañero suyo. Se
#: nombran para que las aserciones digan «el jefe de PUNTO_PROPIO no ve
#: PUNTO_AJENO» en lugar de «402 no ve 413».
PUNTO_PROPIO = "402"  # MALAMBO, zona MALAMBO
PUNTO_AJENO = "413"  # LA93, zona LA 93


@pytest.fixture
def jefe_pdv(sesion: Session, cliente_http: TestClient) -> dict[str, str]:
    """JEFE_PDV con alcance sobre MALAMBO (402) y **solo** sobre él (§8.4)."""
    _crear_usuario(sesion, "jefe", Rol.JEFE_PDV, [PUNTO_PROPIO])
    return autenticar(cliente_http, "jefe")


@pytest.fixture
def jefe_sin_alcance(sesion: Session, cliente_http: TestClient) -> dict[str, str]:
    """JEFE_PDV al que nadie le configuró puntos: no ve nada, no ve todo."""
    _crear_usuario(sesion, "jefe_huerfano", Rol.JEFE_PDV)
    return autenticar(cliente_http, "jefe_huerfano")


@pytest.fixture
def analista_con_alcance(sesion: Session, cliente_http: TestClient) -> dict[str, str]:
    """ANALISTA con puntos asignados: escribe solo sobre ellos.

    Asignarle puntos a alguien es afirmar cuál es su ámbito. En lectura el
    analista sigue viendo la compañía entera —parametriza el reporte de todos—;
    en escritura, la asignación manda.
    """
    _crear_usuario(sesion, "analista_zonal", Rol.ANALISTA, [PUNTO_PROPIO])
    return autenticar(cliente_http, "analista_zonal")


# ── Ayudas para montar un escenario de reporte ────────────────────────────────


def id_punto_venta(sesion: Session, codigo_co: str) -> int:
    return sesion.scalars(select(PuntoVenta).where(PuntoVenta.codigo_co == codigo_co)).one().id


def id_categoria(sesion: Session, codigo: str) -> int:
    return sesion.scalars(select(Categoria).where(Categoria.codigo == codigo)).one().id


def id_periodo(sesion: Session, codigo: str = PERIODO) -> int:
    anio, mes = (int(p) for p in codigo.split("-"))
    return sesion.scalars(select(Periodo).where(Periodo.anio == anio, Periodo.mes == mes)).one().id


def dar_presupuesto(
    sesion: Session,
    codigo_co: str,
    codigo_categoria: str,
    monto: str,
    kilos: str = "0",
) -> None:
    sesion.add(
        Presupuesto(
            periodo_id=id_periodo(sesion),
            punto_venta_id=id_punto_venta(sesion, codigo_co),
            categoria_id=id_categoria(sesion, codigo_categoria),
            monto=Decimal(monto),
            kilos=Decimal(kilos),
        )
    )
    sesion.commit()


def dar_venta(
    sesion: Session,
    codigo_co: str,
    codigo_categoria: str,
    dia: int,
    valor: str,
    costo: str | None = "0",
    kilos: str = "0",
) -> None:
    """Una línea de venta del período de pruebas.

    `costo=None` es el caso de PEREIRA: la fuente **no entrega el costo** y la
    línea se persiste con `costo_promedio` nulo. No es lo mismo que `costo="0"`
    —eso afirma que vender no costó nada— y §4.4 los trata distinto: el conjunto
    que contiene una línea sin costo no tiene margen calculable.
    """
    sesion.add(
        VentaLinea(
            periodo_id=id_periodo(sesion),
            fecha=date(2026, 8, dia),
            punto_venta_id=id_punto_venta(sesion, codigo_co),
            categoria_id=id_categoria(sesion, codigo_categoria),
            valor_subtotal=Decimal(valor),
            costo_promedio=Decimal(costo) if costo is not None else None,
            cantidad_inv=Decimal(kilos),
        )
    )
    sesion.commit()
