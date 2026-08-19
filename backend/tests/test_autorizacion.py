"""Matriz de autorización: un caso por endpoint y por rol.

Esta suite es la red que evita que el agujero vuelva a abrirse. Nació de una
fuga confirmada —`GET /presupuesto` devolvía el presupuesto de toda la compañía
a un JEFE_PDV— y cubre las tres preguntas que hay que hacerle a cada endpoint:

1. ¿Entra quien debe entrar? Cerrar de más rompe el trabajo de alguien y se
   «arregla» abriendo de par en par, así que se comprueba en las dos
   direcciones.
2. ¿Recibe 403 quien no debe entrar?
3. ¿Lo que devuelve está filtrado por el alcance de quien pregunta?

Los roles son `ADMIN`, `GERENTE`, `ANALISTA`, `JEFE_PDV` y `CONSULTA` (§8.4).
El jefe de las pruebas tiene alcance sobre MALAMBO (402) y ninguno sobre LA93
(413).

`ADMIN` entró con el módulo de administración de usuarios y es **superusuario**:
puede todo lo que puede GERENTE. Por eso se suma a las tres listas de abajo allí
donde ya estaba `gerente`, y no se le abre un carril propio. La única separación
va en el otro sentido y vive en `tests/test_usuarios.py`: administrar cuentas es
solo de ADMIN, y ni GERENTE entra ahí.

La parte de esta suite que hay que leer con más cuidado tras añadir un rol no es
la que comprueba los 403 nuevos: es la que comprueba que los cuatro roles de
negocio **siguen entrando donde ya entraban**. Tocar `deps.py` para dejar pasar a
uno más es exactamente cómo se cierra sin querer la puerta de otro.
"""

from __future__ import annotations

import io
import zipfile
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.models.organizacion import Zona
from tests.conftest import (
    PERIODO,
    PUNTO_AJENO,
    PUNTO_PROPIO,
    dar_presupuesto,
    id_categoria,
    id_punto_venta,
)

#: Todo rol autenticado consulta; el alcance —no el rol— es lo que limita a un
#: JEFE_PDV a sus puntos. `admin` incluido: es superusuario del negocio.
ROLES_LECTURA = ("admin", "gerente", "analista", "consulta", "jefe_pdv")
#: Parametrizan: presupuesto, calendario, mapeo de categorías, ingesta.
ROLES_ESCRITURA = ("admin", "analista", "gerente")
#: Los que **no** parametrizan. Un rol de solo lectura no escribe.
ROLES_SOLO_LECTURA = ("consulta", "jefe_pdv")

_TIPO_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def cabeceras(request: pytest.FixtureRequest, rol: str) -> dict[str, str]:
    """Cabecera `Authorization` del rol pedido, resolviendo su fixture."""
    valor: dict[str, str] = request.getfixturevalue(rol)
    return valor


def _zona_id(sesion: Session, nombre: str) -> int:
    return sesion.scalars(select(Zona).where(Zona.nombre == nombre)).one().id


def _celda(sesion: Session, codigo_co: str, motivo: str) -> dict[str, Any]:
    return {
        "periodo": PERIODO,
        "punto_venta_id": id_punto_venta(sesion, codigo_co),
        "categoria_id": id_categoria(sesion, "RES"),
        "monto": "1000000.00",
        "kilos": "500.000",
        "motivo": motivo,
    }


def _csv(*filas: tuple[str, str, str]) -> bytes:
    """Archivo de carga masiva mínimo: `(C.O., categoría, monto)` por fila."""
    lineas = ["punto_venta,categoria,monto,kilos"]
    lineas += [f"{codigo},{categoria},{monto},0" for codigo, categoria, monto in filas]
    return ("\n".join(lineas) + "\n").encode()


def _bomba_zip(megas: int = 30) -> bytes:
    """Un ZIP con la extensión de un libro y 30 MB de ceros dentro.

    Comprime a unas decenas de kilobytes: la proporción entre lo que declara y
    lo que ocupa es la firma de una bomba de descompresión, y es lo que el
    validador de subida mira antes de dejar que `openpyxl` lo abra.
    """
    memoria = io.BytesIO()
    with zipfile.ZipFile(memoria, "w", zipfile.ZIP_DEFLATED) as libro:
        libro.writestr("xl/worksheets/hoja1.xml", b"\0" * (megas * 1024 * 1024))
    return memoria.getvalue()


# ── Sin token no se entra a ninguna parte ─────────────────────────────────────

RUTAS_PROTEGIDAS: list[tuple[str, str]] = [
    ("GET", "/api/v1/auth/yo"),
    ("GET", "/api/v1/catalogos/grupos"),
    ("GET", "/api/v1/catalogos/puntos-venta"),
    ("GET", "/api/v1/catalogos/categorias"),
    ("GET", "/api/v1/catalogos/zonas"),
    ("GET", "/api/v1/catalogos/mapeo-categorias"),
    ("POST", "/api/v1/catalogos/mapeo-categorias"),
    ("GET", f"/api/v1/calendario?periodo={PERIODO}"),
    ("PUT", f"/api/v1/calendario/1?periodo={PERIODO}"),
    ("GET", f"/api/v1/presupuesto?periodo={PERIODO}"),
    ("PUT", "/api/v1/presupuesto"),
    ("POST", "/api/v1/presupuesto/carga-masiva"),
    ("GET", "/api/v1/presupuesto/historial"),
    ("GET", "/api/v1/periodos"),
    ("POST", f"/api/v1/periodos/{PERIODO}/cerrar"),
    ("POST", "/api/v1/ingesta/ejecutar"),
    ("POST", "/api/v1/ingesta/archivo"),
    ("GET", "/api/v1/ingesta/corridas"),
    ("GET", "/api/v1/ingesta/corridas/1/rechazos"),
    ("GET", f"/api/v1/reportes/tablero?periodo={PERIODO}"),
    ("GET", "/api/v1/usuarios"),
    ("POST", "/api/v1/usuarios"),
    ("GET", "/api/v1/usuarios/auditoria"),
    ("PATCH", "/api/v1/usuarios/1"),
    ("PUT", "/api/v1/usuarios/1/puntos-venta"),
    ("POST", "/api/v1/usuarios/1/activar"),
    ("POST", "/api/v1/usuarios/1/desactivar"),
    ("POST", "/api/v1/usuarios/1/restablecer-clave"),
]


@pytest.mark.parametrize(("metodo", "ruta"), RUTAS_PROTEGIDAS)
def test_sin_token_ningun_endpoint_responde(
    cliente_http: TestClient, metodo: str, ruta: str
) -> None:
    """401 antes de mirar el cuerpo: la autenticación es la primera puerta."""
    respuesta = cliente_http.request(metodo, ruta)
    assert respuesta.status_code == 401, f"{metodo} {ruta} respondió {respuesta.status_code}"


def test_un_token_inventado_no_vale(cliente_http: TestClient) -> None:
    respuesta = cliente_http.get(
        f"/api/v1/presupuesto?periodo={PERIODO}",
        headers={"Authorization": "Bearer esto.no.es-un-token"},
    )
    assert respuesta.status_code == 401


# ── /auth ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("rol", ROLES_LECTURA)
def test_cualquier_rol_consulta_su_propio_perfil(
    cliente_http: TestClient, request: pytest.FixtureRequest, rol: str
) -> None:
    respuesta = cliente_http.get("/api/v1/auth/yo", headers=cabeceras(request, rol))
    assert respuesta.status_code == 200


def test_el_perfil_del_jefe_declara_su_alcance(
    cliente_http: TestClient, jefe_pdv: dict[str, str]
) -> None:
    """`/auth/yo` es lo que el frontend usa para saber qué puede pedir."""
    cuerpo = cliente_http.get("/api/v1/auth/yo", headers=jefe_pdv).json()
    assert cuerpo["rol"] == "JEFE_PDV"
    assert cuerpo["puntos_venta"] == [PUNTO_PROPIO]


def test_el_perfil_de_gerencia_no_declara_alcance(
    cliente_http: TestClient, gerente: dict[str, str]
) -> None:
    cuerpo = cliente_http.get("/api/v1/auth/yo", headers=gerente).json()
    assert cuerpo["puntos_venta"] == []


def test_el_acceso_no_distingue_usuario_inexistente_de_clave_mala(
    cliente_http: TestClient, gerente: dict[str, str]
) -> None:
    """Mismo mensaje en los dos casos: enumerar usuarios es el paso previo."""
    inexistente = cliente_http.post(
        "/api/v1/auth/acceso", json={"usuario": "nadie", "clave": "Lo-Que-Sea-2026"}
    )
    clave_mala = cliente_http.post(
        "/api/v1/auth/acceso", json={"usuario": "gerente", "clave": "Lo-Que-Sea-2026"}
    )
    assert inexistente.status_code == clave_mala.status_code == 401
    assert inexistente.json()["detalle"] == clave_mala.json()["detalle"]


# ── /catalogos ────────────────────────────────────────────────────────────────

CATALOGOS_DE_LECTURA = (
    "/api/v1/catalogos/grupos",
    "/api/v1/catalogos/puntos-venta",
    "/api/v1/catalogos/categorias",
    "/api/v1/catalogos/zonas",
    "/api/v1/catalogos/mapeo-categorias",
)


@pytest.mark.parametrize("ruta", CATALOGOS_DE_LECTURA)
@pytest.mark.parametrize("rol", ROLES_LECTURA)
def test_los_catalogos_los_lee_cualquier_rol(
    cliente_http: TestClient, request: pytest.FixtureRequest, rol: str, ruta: str
) -> None:
    assert cliente_http.get(ruta, headers=cabeceras(request, rol)).status_code == 200


def test_el_catalogo_de_puntos_de_venta_se_devuelve_entero_al_jefe(
    cliente_http: TestClient, jefe_pdv: dict[str, str]
) -> None:
    """Decisión explícita, no descuido: el catálogo no lleva cifras.

    Son códigos, nombres, grupo y zona —el organigrama comercial, que un jefe
    de punto conoce por el rótulo de la calle— y el frontend los necesita para
    etiquetar. Lo que se protege es la **cifra**, y esa vive en `/presupuesto`
    y `/reportes`, que sí filtran. La prueba fija la decisión para que el día
    que este esquema crezca con un dato de negocio, falle y haya que revisarla.
    """
    puntos = cliente_http.get("/api/v1/catalogos/puntos-venta", headers=jefe_pdv).json()
    assert {p["codigo_co"] for p in puntos} >= {PUNTO_PROPIO, PUNTO_AJENO}
    campos = set(puntos[0])
    assert campos == {"id", "codigo_co", "nombre", "grupo", "zona", "activo", "presupuestado"}


@pytest.mark.parametrize("rol", ROLES_ESCRITURA)
def test_el_mapeo_de_categorias_lo_reclasifica_quien_parametriza(
    cliente_http: TestClient, request: pytest.FixtureRequest, rol: str
) -> None:
    respuesta = cliente_http.post(
        "/api/v1/catalogos/mapeo-categorias",
        json={"texto_siesa": f"0099 - PRUEBA {rol}", "categoria": "VIVERES"},
        headers=cabeceras(request, rol),
    )
    assert respuesta.status_code == 200, respuesta.text


@pytest.mark.parametrize("rol", ROLES_SOLO_LECTURA)
def test_un_rol_de_lectura_no_reclasifica_el_mapeo(
    cliente_http: TestClient, request: pytest.FixtureRequest, rol: str
) -> None:
    respuesta = cliente_http.post(
        "/api/v1/catalogos/mapeo-categorias",
        json={"texto_siesa": "0099 - PRUEBA", "categoria": "OTROS"},
        headers=cabeceras(request, rol),
    )
    assert respuesta.status_code == 403


# ── /calendario ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize("rol", ROLES_LECTURA)
def test_el_calendario_lo_consulta_cualquier_rol(
    cliente_http: TestClient, request: pytest.FixtureRequest, rol: str
) -> None:
    respuesta = cliente_http.get(
        f"/api/v1/calendario?periodo={PERIODO}", headers=cabeceras(request, rol)
    )
    assert respuesta.status_code == 200
    assert respuesta.json()


def test_el_jefe_solo_ve_el_calendario_de_las_zonas_de_sus_puntos(
    cliente_http: TestClient, gerente: dict[str, str], jefe_pdv: dict[str, str]
) -> None:
    """Los días hábiles de una zona ajena son la vara con la que se mide a otro."""
    todas = cliente_http.get(f"/api/v1/calendario?periodo={PERIODO}", headers=gerente).json()
    suyas = cliente_http.get(f"/api/v1/calendario?periodo={PERIODO}", headers=jefe_pdv).json()

    assert len(todas) > 1
    assert [z["zona"] for z in suyas] == ["MALAMBO"]


def test_el_jefe_sin_alcance_no_ve_ninguna_zona(
    cliente_http: TestClient, jefe_sin_alcance: dict[str, str]
) -> None:
    """Sin alcance configurado se ve **nada**, no todo."""
    respuesta = cliente_http.get(f"/api/v1/calendario?periodo={PERIODO}", headers=jefe_sin_alcance)
    assert respuesta.status_code == 200
    assert respuesta.json() == []


@pytest.mark.parametrize("rol", ROLES_ESCRITURA)
def test_el_calendario_lo_parametriza_quien_tiene_la_compania_entera(
    cliente_http: TestClient, sesion: Session, request: pytest.FixtureRequest, rol: str
) -> None:
    respuesta = cliente_http.put(
        f"/api/v1/calendario/{_zona_id(sesion, 'MALAMBO')}?periodo={PERIODO}",
        json={"dias_habiles": "27.5", "dias_trabajados": "7.5"},
        headers=cabeceras(request, rol),
    )
    assert respuesta.status_code == 200, respuesta.text


@pytest.mark.parametrize("rol", ROLES_SOLO_LECTURA)
def test_un_rol_de_lectura_no_parametriza_el_calendario(
    cliente_http: TestClient, sesion: Session, request: pytest.FixtureRequest, rol: str
) -> None:
    respuesta = cliente_http.put(
        f"/api/v1/calendario/{_zona_id(sesion, 'MALAMBO')}?periodo={PERIODO}",
        json={"dias_habiles": "27.5"},
        headers=cabeceras(request, rol),
    )
    assert respuesta.status_code == 403


def test_un_analista_con_alcance_limitado_no_toca_el_calendario_de_una_zona(
    cliente_http: TestClient, sesion: Session, analista_con_alcance: dict[str, str]
) -> None:
    """Una zona agrupa puntos de varios responsables: o se tiene todo, o nada.

    La zona MALAMBO contiene justo el punto que este analista tiene asignado, y
    aun así se le niega: no existe «la parte propia» de un calendario de zona,
    y admitirla para las zonas de un solo punto dejaría la regla dependiendo de
    cómo esté agrupada la zona ese mes.
    """
    respuesta = cliente_http.put(
        f"/api/v1/calendario/{_zona_id(sesion, 'MALAMBO')}?periodo={PERIODO}",
        json={"dias_habiles": "27.5"},
        headers=analista_con_alcance,
    )
    assert respuesta.status_code == 403


# ── /presupuesto — la fuga confirmada ─────────────────────────────────────────


@pytest.mark.parametrize("rol", ROLES_LECTURA)
def test_el_presupuesto_lo_consulta_cualquier_rol(
    cliente_http: TestClient, sesion: Session, request: pytest.FixtureRequest, rol: str
) -> None:
    dar_presupuesto(sesion, PUNTO_PROPIO, "RES", "1000000000")
    respuesta = cliente_http.get(
        f"/api/v1/presupuesto?periodo={PERIODO}", headers=cabeceras(request, rol)
    )
    assert respuesta.status_code == 200
    assert respuesta.json(), f"{rol} no recibió ninguna fila de presupuesto"


def test_el_jefe_no_ve_el_presupuesto_de_un_punto_ajeno(
    cliente_http: TestClient, sesion: Session, jefe_pdv: dict[str, str]
) -> None:
    """La fuga que originó esta suite: el presupuesto es la vara de medir."""
    dar_presupuesto(sesion, PUNTO_PROPIO, "RES", "1000000000")
    dar_presupuesto(sesion, PUNTO_AJENO, "RES", "3500000000")

    filas = cliente_http.get(f"/api/v1/presupuesto?periodo={PERIODO}", headers=jefe_pdv).json()
    assert {f["punto_venta"] for f in filas} == {PUNTO_PROPIO}


def test_el_jefe_no_esquiva_el_alcance_pidiendo_el_punto_ajeno_por_parametro(
    cliente_http: TestClient, sesion: Session, jefe_pdv: dict[str, str]
) -> None:
    """El filtro del usuario no puede ensanchar su alcance, solo estrecharlo."""
    dar_presupuesto(sesion, PUNTO_AJENO, "RES", "3500000000")

    filas = cliente_http.get(
        f"/api/v1/presupuesto?periodo={PERIODO}&punto_venta={PUNTO_AJENO}", headers=jefe_pdv
    ).json()
    assert filas == []


def test_el_jefe_sin_alcance_no_ve_ningun_presupuesto(
    cliente_http: TestClient, sesion: Session, jefe_sin_alcance: dict[str, str]
) -> None:
    dar_presupuesto(sesion, PUNTO_PROPIO, "RES", "1000000000")
    filas = cliente_http.get(
        f"/api/v1/presupuesto?periodo={PERIODO}", headers=jefe_sin_alcance
    ).json()
    assert filas == []


def test_el_historial_tambien_se_filtra_por_alcance(
    cliente_http: TestClient, sesion: Session, gerente: dict[str, str], jefe_pdv: dict[str, str]
) -> None:
    """El historial lleva el importe anterior **y** el nuevo de cada celda."""
    for codigo, motivo in ((PUNTO_PROPIO, "Presupuesto de MALAMBO"), (PUNTO_AJENO, "Ppto de LA93")):
        respuesta = cliente_http.put(
            "/api/v1/presupuesto", json=_celda(sesion, codigo, motivo), headers=gerente
        )
        assert respuesta.status_code == 200, respuesta.text

    del_jefe = cliente_http.get(
        f"/api/v1/presupuesto/historial?periodo={PERIODO}", headers=jefe_pdv
    ).json()
    de_gerencia = cliente_http.get(
        f"/api/v1/presupuesto/historial?periodo={PERIODO}", headers=gerente
    ).json()

    assert len(de_gerencia) == 4  # monto y kilos de cada uno de los dos puntos
    assert len(del_jefe) == 2
    assert all(entrada["motivo"] == "Presupuesto de MALAMBO" for entrada in del_jefe)


@pytest.mark.parametrize("rol", ROLES_ESCRITURA)
def test_el_presupuesto_lo_parametriza_analista_y_gerencia(
    cliente_http: TestClient, sesion: Session, request: pytest.FixtureRequest, rol: str
) -> None:
    respuesta = cliente_http.put(
        "/api/v1/presupuesto",
        json=_celda(sesion, PUNTO_PROPIO, f"Alta por {rol}"),
        headers=cabeceras(request, rol),
    )
    assert respuesta.status_code == 200, respuesta.text


@pytest.mark.parametrize("rol", ROLES_SOLO_LECTURA)
def test_un_rol_de_lectura_no_parametriza_presupuesto(
    cliente_http: TestClient, sesion: Session, request: pytest.FixtureRequest, rol: str
) -> None:
    """Ni siquiera sobre su propio punto: JEFE_PDV consulta, no presupuesta."""
    respuesta = cliente_http.put(
        "/api/v1/presupuesto",
        json=_celda(sesion, PUNTO_PROPIO, "No debería poder"),
        headers=cabeceras(request, rol),
    )
    assert respuesta.status_code == 403


def test_un_analista_con_alcance_escribe_sobre_su_punto(
    cliente_http: TestClient, sesion: Session, analista_con_alcance: dict[str, str]
) -> None:
    respuesta = cliente_http.put(
        "/api/v1/presupuesto",
        json=_celda(sesion, PUNTO_PROPIO, "Presupuesto de su punto"),
        headers=analista_con_alcance,
    )
    assert respuesta.status_code == 200, respuesta.text


def test_un_analista_con_alcance_no_escribe_sobre_un_punto_ajeno(
    cliente_http: TestClient, sesion: Session, analista_con_alcance: dict[str, str]
) -> None:
    """Tener el rol no es tener el ámbito."""
    respuesta = cliente_http.put(
        "/api/v1/presupuesto",
        json=_celda(sesion, PUNTO_AJENO, "Presupuesto de un punto ajeno"),
        headers=analista_con_alcance,
    )
    assert respuesta.status_code == 403
    assert "alcance" in respuesta.json()["detalle"].lower()


# ── /presupuesto/carga-masiva ─────────────────────────────────────────────────


def test_la_carga_masiva_la_hace_quien_parametriza(
    cliente_http: TestClient, analista: dict[str, str]
) -> None:
    respuesta = cliente_http.post(
        "/api/v1/presupuesto/carga-masiva",
        files={"archivo": ("ppto.csv", _csv((PUNTO_PROPIO, "RES", "1000")), "text/csv")},
        data={"periodo": PERIODO, "motivo": "Carga de prueba"},
        headers=analista,
    )
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["aceptadas"] == 1


@pytest.mark.parametrize("rol", ROLES_SOLO_LECTURA)
def test_un_rol_de_lectura_no_carga_presupuesto_masivo(
    cliente_http: TestClient, request: pytest.FixtureRequest, rol: str
) -> None:
    respuesta = cliente_http.post(
        "/api/v1/presupuesto/carga-masiva",
        files={"archivo": ("ppto.csv", _csv((PUNTO_PROPIO, "RES", "1000")), "text/csv")},
        data={"periodo": PERIODO, "motivo": "No debería poder"},
        headers=cabeceras(request, rol),
    )
    assert respuesta.status_code == 403


def test_la_carga_masiva_rechaza_las_filas_fuera_del_alcance_de_quien_carga(
    cliente_http: TestClient,
    gerente: dict[str, str],
    analista_con_alcance: dict[str, str],
) -> None:
    """El archivo lo trae el usuario: sus filas no son más de fiar que un JSON.

    La fila ajena se rechaza **con su motivo** —no en silencio— y no deja ni
    rastro en el presupuesto del punto que no le corresponde.
    """
    respuesta = cliente_http.post(
        "/api/v1/presupuesto/carga-masiva",
        files={
            "archivo": (
                "ppto.csv",
                _csv((PUNTO_PROPIO, "RES", "1000"), (PUNTO_AJENO, "RES", "9999")),
                "text/csv",
            )
        },
        data={"periodo": PERIODO, "motivo": "Carga con una fila ajena"},
        headers=analista_con_alcance,
    )
    assert respuesta.status_code == 200, respuesta.text
    resultado = respuesta.json()
    assert resultado["aceptadas"] == 1
    assert resultado["rechazadas"] == 1
    assert "alcance" in resultado["errores"][0]["motivo"].lower()

    ajeno = cliente_http.get(
        f"/api/v1/presupuesto?periodo={PERIODO}&punto_venta={PUNTO_AJENO}", headers=gerente
    ).json()
    assert ajeno == []


def test_la_carga_masiva_no_admite_cualquier_extension(
    cliente_http: TestClient, analista: dict[str, str]
) -> None:
    respuesta = cliente_http.post(
        "/api/v1/presupuesto/carga-masiva",
        files={"archivo": ("ppto.exe", b"MZ...", "application/octet-stream")},
        data={"periodo": PERIODO, "motivo": "Formato que no es"},
        headers=analista,
    )
    assert respuesta.status_code == 422
    assert "formato" in respuesta.json()["detalle"].lower()


def test_la_carga_masiva_no_abre_una_bomba_de_descompresion(
    cliente_http: TestClient, analista: dict[str, str]
) -> None:
    """Un `.xlsx` es un ZIP y un ZIP de 30 KB puede declarar 30 MB."""
    respuesta = cliente_http.post(
        "/api/v1/presupuesto/carga-masiva",
        files={"archivo": ("ppto.xlsx", _bomba_zip(), _TIPO_XLSX)},
        data={"periodo": PERIODO, "motivo": "Bomba de descompresion"},
        headers=analista,
    )
    assert respuesta.status_code == 422
    assert "descomprime" in respuesta.json()["detalle"].lower()


def test_un_xlsx_que_no_es_un_zip_se_rechaza_antes_de_abrirlo(
    cliente_http: TestClient, analista: dict[str, str]
) -> None:
    respuesta = cliente_http.post(
        "/api/v1/presupuesto/carga-masiva",
        files={"archivo": ("ppto.xlsx", b"esto no es un libro de excel", _TIPO_XLSX)},
        data={"periodo": PERIODO, "motivo": "Extension mentirosa"},
        headers=analista,
    )
    assert respuesta.status_code == 422
    assert "ZIP" in respuesta.json()["detalle"]


# ── /periodos ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("rol", ROLES_LECTURA)
def test_los_periodos_los_consulta_cualquier_rol(
    cliente_http: TestClient, request: pytest.FixtureRequest, rol: str
) -> None:
    respuesta = cliente_http.get("/api/v1/periodos", headers=cabeceras(request, rol))
    assert respuesta.status_code == 200


def test_solo_gerencia_cierra_el_periodo(cliente_http: TestClient, gerente: dict[str, str]) -> None:
    assert (
        cliente_http.post(f"/api/v1/periodos/{PERIODO}/cerrar", headers=gerente).status_code == 200
    )


def test_sistemas_tambien_cierra_el_periodo(
    cliente_http: TestClient, admin: dict[str, str]
) -> None:
    """ADMIN puede lo mismo que GERENTE, cerrar el período incluido.

    Va en su propia prueba y no parametrizada junto a `gerente` porque cerrar
    dos veces el mismo período no es lo que se quiere probar aquí.
    """
    assert cliente_http.post(f"/api/v1/periodos/{PERIODO}/cerrar", headers=admin).status_code == 200


@pytest.mark.parametrize("rol", ("analista", "consulta", "jefe_pdv"))
def test_nadie_mas_cierra_el_periodo(
    cliente_http: TestClient, request: pytest.FixtureRequest, rol: str
) -> None:
    """Cerrar congela el presupuesto del mes: es decisión de gerencia (§7)."""
    respuesta = cliente_http.post(
        f"/api/v1/periodos/{PERIODO}/cerrar", headers=cabeceras(request, rol)
    )
    assert respuesta.status_code == 403


# ── /ingesta ──────────────────────────────────────────────────────────────────


def test_la_ingesta_la_ejecuta_quien_parametriza(
    cliente_http: TestClient, analista: dict[str, str]
) -> None:
    """422 es «pasó el control de acceso y llegó al servicio», que es lo que se prueba.

    Lo que devuelve el servicio da igual aquí —hoy es un 422 pidiendo
    `SIGREP_SIESA_TOKEN`, que el entorno de pruebas no lleva—; lo que importa es
    que **no** es un 403. Contrástese con el caso de los roles de solo lectura,
    justo debajo, que ni siquiera llegan al servicio.
    """
    respuesta = cliente_http.post(
        "/api/v1/ingesta/ejecutar",
        json={"desde": "2026-08-01", "hasta": "2026-08-09", "fuente": "siesa"},
        headers=analista,
    )
    assert respuesta.status_code != 403
    assert respuesta.status_code == 422


@pytest.mark.parametrize("rol", ROLES_SOLO_LECTURA)
def test_un_rol_de_lectura_no_ejecuta_la_ingesta(
    cliente_http: TestClient, request: pytest.FixtureRequest, rol: str
) -> None:
    respuesta = cliente_http.post(
        "/api/v1/ingesta/ejecutar",
        json={"desde": "2026-08-01", "hasta": "2026-08-09", "fuente": "siesa"},
        headers=cabeceras(request, rol),
    )
    assert respuesta.status_code == 403


@pytest.mark.parametrize("rol", ROLES_SOLO_LECTURA)
def test_un_rol_de_lectura_no_sube_un_archivo_de_venta(
    cliente_http: TestClient, request: pytest.FixtureRequest, rol: str
) -> None:
    respuesta = cliente_http.post(
        "/api/v1/ingesta/archivo",
        files={"archivo": ("venta.xlsx", _bomba_zip(1), _TIPO_XLSX)},
        headers=cabeceras(request, rol),
    )
    assert respuesta.status_code == 403


def test_la_subida_de_venta_no_admite_cualquier_extension(
    cliente_http: TestClient, analista: dict[str, str]
) -> None:
    respuesta = cliente_http.post(
        "/api/v1/ingesta/archivo",
        files={"archivo": ("venta.csv", b"fecha,co\n", "text/csv")},
        headers=analista,
    )
    assert respuesta.status_code == 422
    assert "formato" in respuesta.json()["detalle"].lower()


def test_la_subida_de_venta_no_abre_una_bomba_de_descompresion(
    cliente_http: TestClient, analista: dict[str, str]
) -> None:
    respuesta = cliente_http.post(
        "/api/v1/ingesta/archivo",
        files={"archivo": ("venta.xlsx", _bomba_zip(), _TIPO_XLSX)},
        headers=analista,
    )
    assert respuesta.status_code == 422
    assert "descomprime" in respuesta.json()["detalle"].lower()


@pytest.mark.parametrize("rol", ROLES_LECTURA)
def test_las_corridas_las_consulta_cualquier_rol(
    cliente_http: TestClient, request: pytest.FixtureRequest, rol: str
) -> None:
    """Son contadores: ni punto de venta, ni cliente, ni importe."""
    respuesta = cliente_http.get("/api/v1/ingesta/corridas", headers=cabeceras(request, rol))
    assert respuesta.status_code == 200


@pytest.mark.parametrize("rol", ROLES_ESCRITURA)
def test_los_rechazos_los_consulta_quien_opera_la_carga(
    cliente_http: TestClient, request: pytest.FixtureRequest, rol: str
) -> None:
    """404 y no 403: el rol pasó y la corrida es la que no existe."""
    respuesta = cliente_http.get(
        "/api/v1/ingesta/corridas/9999/rechazos", headers=cabeceras(request, rol)
    )
    assert respuesta.status_code == 404


@pytest.mark.parametrize("rol", ROLES_SOLO_LECTURA)
def test_un_rol_de_lectura_no_ve_las_filas_rechazadas(
    cliente_http: TestClient, request: pytest.FixtureRequest, rol: str
) -> None:
    """Los rechazos llevan el valor crudo de la fila: NIT de cliente e importes.

    No se pueden filtrar por alcance —`rechazos_ingesta` no tiene punto de
    venta, y buena parte de los rechazos son filas cuyo C.O. no se reconoció—,
    así que el control que queda es el rol.
    """
    respuesta = cliente_http.get(
        "/api/v1/ingesta/corridas/9999/rechazos", headers=cabeceras(request, rol)
    )
    assert respuesta.status_code == 403


# ── Los errores no cuentan de más ─────────────────────────────────────────────


@pytest.mark.parametrize(
    ("ruta", "esperado"),
    (
        ("/api/v1/ingesta/corridas/9999/rechazos", 404),
        ("/api/v1/presupuesto?periodo=agosto", 422),
        ("/api/v1/reportes/inventado/exportar?periodo=2026-08", 404),
    ),
)
def test_los_errores_no_filtran_traza_ni_interioridades(
    cliente_http: TestClient, gerente: dict[str, str], ruta: str, esperado: int
) -> None:
    """Formato uniforme `{detalle, codigo}` y ni una pista de la implementación."""
    respuesta = cliente_http.get(ruta, headers=gerente)
    assert respuesta.status_code == esperado

    cuerpo = respuesta.json()
    assert set(cuerpo) == {"detalle", "codigo", "detalles"}

    texto = respuesta.text.lower()
    for pista in ("traceback", "sqlalchemy", "select ", ".py", "site-packages"):
        assert pista not in texto, f"la respuesta de {ruta} filtra «{pista}»"


def test_el_403_no_cuenta_que_existe_el_recurso(
    cliente_http: TestClient, jefe_pdv: dict[str, str]
) -> None:
    """El rol se comprueba antes de tocar la base: no hay oráculo de existencia."""
    respuesta = cliente_http.get("/api/v1/ingesta/corridas/1/rechazos", headers=jefe_pdv)
    assert respuesta.status_code == 403
    assert respuesta.json()["codigo"] == "no_autorizado"
