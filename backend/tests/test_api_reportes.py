"""Ciclo completo por HTTP: presupuesto → venta → reporte.

Comprueba lo que ninguna prueba de dominio puede comprobar: que el contrato de
`docs/API.md` se cumple, que los importes viajan como texto y que el alcance por
rol se aplica en la frontera.
"""

from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import PERMISO_CONSULTAR_TABLERO, PERMISO_VENTA_DIARIA_ASADERO
from app.infrastructure.models.organizacion import PuntoVenta
from app.infrastructure.models.periodo import CalendarioZona
from app.infrastructure.models.usuario import Usuario, UsuarioPermiso
from tests.conftest import (
    PERIODO,
    dar_presupuesto,
    dar_venta,
    id_categoria,
    id_punto_venta,
)

D = Decimal


def test_permiso_asadero_consulta_solo_endpoint_forzado(
    sesion: Session, cliente_http: TestClient, consulta: dict[str, str]
) -> None:
    usuario = sesion.scalars(select(Usuario).where(Usuario.usuario == "consulta")).one()
    sesion.add(UsuarioPermiso(usuario_id=usuario.id, codigo=PERMISO_VENTA_DIARIA_ASADERO))
    sesion.commit()
    dar_venta(sesion, "402", "ASADERO", 1, "10")
    dar_venta(sesion, "402", "RES", 1, "90")

    respuesta = cliente_http.get(
        "/api/v1/reportes/venta-diaria-asadero",
        params={"periodo": PERIODO, "categoria": "OTRA"},
        headers=consulta,
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["totales"]["total"] == "10.00"


def test_sin_permiso_asadero_no_puede_consultar_endpoint_especializado(
    consulta: dict[str, str], cliente_http: TestClient
) -> None:
    respuesta = cliente_http.get(
        "/api/v1/reportes/venta-diaria-asadero",
        params={"periodo": PERIODO},
        headers=consulta,
    )
    assert respuesta.status_code == 403


def test_permiso_de_tablero_no_habilita_otros_reportes(
    sesion: Session, cliente_http: TestClient, consulta: dict[str, str]
) -> None:
    usuario = sesion.scalars(select(Usuario).where(Usuario.usuario == "consulta")).one()
    sesion.add(UsuarioPermiso(usuario_id=usuario.id, codigo=PERMISO_CONSULTAR_TABLERO))
    sesion.commit()

    assert (
        cliente_http.get(
            "/api/v1/reportes/tablero", params={"periodo": PERIODO}, headers=consulta
        ).status_code
        == 200
    )
    assert (
        cliente_http.get(
            "/api/v1/reportes/costos", params={"periodo": PERIODO}, headers=consulta
        ).status_code
        == 403
    )


def test_permiso_de_tablero_no_habilita_filtro_ni_descarga(
    sesion: Session, cliente_http: TestClient, consulta: dict[str, str]
) -> None:
    usuario = sesion.scalars(select(Usuario).where(Usuario.usuario == "consulta")).one()
    sesion.add(UsuarioPermiso(usuario_id=usuario.id, codigo=PERMISO_CONSULTAR_TABLERO))
    sesion.commit()

    assert (
        cliente_http.get(
            "/api/v1/reportes/tablero",
            params={"periodo": PERIODO, "grupo": "001"},
            headers=consulta,
        ).status_code
        == 403
    )
    assert (
        cliente_http.get(
            "/api/v1/reportes/tablero/exportar",
            params={"periodo": PERIODO},
            headers=consulta,
        ).status_code
        == 403
    )


def _fijar_calendario(sesion: Session, dias_habiles: str, dias_trabajados: str) -> None:
    """Fija el mismo calendario en todas las zonas: hace predecible el ideal."""
    for calendario in sesion.scalars(select(CalendarioZona)).all():
        calendario.dias_habiles = D(dias_habiles)
        calendario.dias_trabajados = D(dias_trabajados)
    sesion.commit()


# ── Catálogos: la estructura real de §3 ───────────────────────────────────────


def test_la_semilla_carga_la_estructura_real_del_negocio(
    cliente_http: TestClient, gerente: dict[str, str]
) -> None:
    grupos = cliente_http.get("/api/v1/catalogos/grupos", headers=gerente).json()
    puntos = cliente_http.get("/api/v1/catalogos/puntos-venta", headers=gerente).json()
    categorias = cliente_http.get("/api/v1/catalogos/categorias", headers=gerente).json()

    assert [g["codigo"] for g in grupos] == ["001", "002", "003", "004"]
    assert len(puntos) == 16
    # Las once categorías reales de SIESA. `OTROS` ya no existe: las cuatro que
    # antes plegaba —QUESO Y LACTEOS, HUEVOS, VIVERES y DOMICILIOS— son ahora
    # categorías de pleno derecho.
    assert {c["nombre"] for c in categorias} == {
        "RES",
        "CERDO",
        "POLLO",
        "PESCADO",
        "EMBUTIDOS",
        "VISCERAS",
        "ASADERO",
        "QUESO Y LACTEOS",
        "HUEVOS",
        "VIVERES",
        "DOMICILIOS",
    }


def test_las_dos_variantes_ortograficas_de_0006_estan_mapeadas(
    cliente_http: TestClient, gerente: dict[str, str]
) -> None:
    """`QUESO Y LACTEOS` y `QUESOS Y LACTEOS` conviven en el archivo de SIESA.

    Si faltara una, 140 filas caerían a `OTROS` por accidente en vez de por
    decisión, y nadie se enteraría.
    """
    mapeo = cliente_http.get("/api/v1/catalogos/mapeo-categorias", headers=gerente).json()
    textos = {m["texto_siesa"] for m in mapeo}
    assert "0006 - QUESO Y LACTEOS" in textos
    assert "0006 - QUESOS Y LACTEOS" in textos


def test_eventos_bucaramanga_existe_y_no_esta_presupuestado(
    cliente_http: TestClient, gerente: dict[str, str]
) -> None:
    puntos = cliente_http.get("/api/v1/catalogos/puntos-venta", headers=gerente).json()
    eventos = next(p for p in puntos if p["codigo_co"] == "432")
    assert eventos["presupuestado"] is False


# ── El reporte ────────────────────────────────────────────────────────────────


def test_tablero_calcula_cumplimiento_contra_el_ideal(
    cliente_http: TestClient, gerente: dict[str, str], sesion: Session
) -> None:
    _fijar_calendario(sesion, "27.5", "7.5")
    dar_presupuesto(sesion, "402", "RES", "1000000")
    dar_venta(sesion, "402", "RES", 5, "300000", costo="200000")

    cuerpo = cliente_http.get(f"/api/v1/reportes/tablero?periodo={PERIODO}", headers=gerente).json()
    consolidado = cuerpo["consolidado"]

    # Los importes viajan como texto: un `float` de JavaScript corrompe montos
    # de miles de millones (`docs/API.md`).
    assert isinstance(consolidado["venta"], str)
    assert isinstance(consolidado["cumplimiento"], str)

    assert consolidado["presupuesto"] == "1000000.00"
    assert consolidado["venta"] == "300000.00"
    assert consolidado["cumplimiento"] == "0.3000"
    assert consolidado["ideal"] == "0.2727"
    assert consolidado["semaforo"] == "VERDE"
    assert consolidado["margen_porcentaje"] == "0.3333"


def test_el_tablero_publica_los_parametros_del_calculo(
    cliente_http: TestClient, gerente: dict[str, str], sesion: Session
) -> None:
    """Un número sin origen no es verificable (§4.2)."""
    _fijar_calendario(sesion, "27.5", "7.5")
    dar_presupuesto(sesion, "402", "RES", "1000000")

    cuerpo = cliente_http.get(f"/api/v1/reportes/tablero?periodo={PERIODO}", headers=gerente).json()

    assert cuerpo["fecha_corte"]
    assert "parametros_calculo" in cuerpo
    assert cuerpo["parametros_calculo"]["umbrales"]["factor_amarillo"] == "0.90"


def test_la_venta_sin_presupuesto_se_reporta_aparte_y_no_descuadra(
    cliente_http: TestClient, gerente: dict[str, str], sesion: Session
) -> None:
    """La regla de §7: nunca se descarta en silencio."""
    _fijar_calendario(sesion, "28", "9")
    dar_presupuesto(sesion, "402", "RES", "1000000")
    dar_venta(sesion, "402", "RES", 5, "300000")
    dar_venta(sesion, "432", "RES", 5, "77000")  # EVENTOS BUCARAMANGA

    cuerpo = cliente_http.get(f"/api/v1/reportes/tablero?periodo={PERIODO}", headers=gerente).json()

    # El consolidado presupuestado no se contamina...
    assert cuerpo["consolidado"]["venta"] == "300000.00"
    # ...y la venta sin presupuesto sigue siendo visible.
    sin_presupuesto = cuerpo["sin_presupuesto"]
    assert len(sin_presupuesto) == 1
    assert sin_presupuesto[0]["codigo_co"] == "432"
    assert sin_presupuesto[0]["venta"] == "77000.00"


def test_cumplimiento_desglosa_por_categoria(
    cliente_http: TestClient, gerente: dict[str, str], sesion: Session
) -> None:
    _fijar_calendario(sesion, "28", "7")
    dar_presupuesto(sesion, "402", "RES", "600000")
    dar_presupuesto(sesion, "402", "CERDO", "400000")
    dar_venta(sesion, "402", "RES", 3, "180000")
    dar_venta(sesion, "402", "CERDO", 3, "50000")

    cuerpo = cliente_http.get(
        f"/api/v1/reportes/cumplimiento?periodo={PERIODO}", headers=gerente
    ).json()
    fila = next(f for f in cuerpo["filas"] if f["punto_venta"] == "402")

    assert fila["venta"] == "230000.00"
    # El presupuesto del punto es la suma de sus categorías: se calcula, no se
    # captura dos veces (§3.3).
    assert fila["presupuesto"] == "1000000.00"

    res = next(c for c in fila["categorias"] if c["categoria"] == "RES")
    cerdo = next(c for c in fila["categorias"] if c["categoria"] == "CERDO")
    assert res["cumplimiento"] == "0.3000"  # 180/600 va bien
    assert cerdo["cumplimiento"] == "0.1250"  # 50/400 va mal
    assert res["semaforo"] == "VERDE"
    assert cerdo["semaforo"] == "ROJO"


def test_venta_diaria_trae_el_presupuesto_diario_derivado(
    cliente_http: TestClient, gerente: dict[str, str], sesion: Session
) -> None:
    """El diario se deriva del calendario; no se guarda (§3.3)."""
    _fijar_calendario(sesion, "25", "9")
    dar_presupuesto(sesion, "402", "RES", "1000000")
    dar_venta(sesion, "402", "RES", 1, "40000")
    dar_venta(sesion, "402", "RES", 2, "60000")

    cuerpo = cliente_http.get(
        f"/api/v1/reportes/venta-diaria?periodo={PERIODO}", headers=gerente
    ).json()

    assert cuerpo["presupuesto_diario_por_pdv"]["402"] == "40000.00"  # 1 000 000 / 25
    fila = next(f for f in cuerpo["filas"] if f["punto_venta"] == "402")
    assert fila["valores"][0] == "40000.00"
    assert fila["valores"][1] == "60000.00"
    assert fila["total"] == "100000.00"


def test_reporte_en_kilos_usa_la_medida_de_kilos(
    cliente_http: TestClient, gerente: dict[str, str], sesion: Session
) -> None:
    """§4.5: un mes puede cumplir en pesos y fallar en kilos."""
    _fijar_calendario(sesion, "28", "7")
    dar_presupuesto(sesion, "402", "RES", "1000000", kilos="500")
    dar_venta(sesion, "402", "RES", 3, "300000", kilos="100")

    cuerpo = cliente_http.get(
        f"/api/v1/reportes/tablero?periodo={PERIODO}&medida=kilos", headers=gerente
    ).json()

    assert cuerpo["medida"] == "kilos"
    assert cuerpo["consolidado"]["venta"] == "100.000"
    assert cuerpo["consolidado"]["cumplimiento"] == "0.2000"  # peor que en pesos


# ── Presupuesto: versionado y cierre de período ───────────────────────────────


def test_guardar_presupuesto_deja_rastro_en_el_historial(
    cliente_http: TestClient, analista: dict[str, str], sesion: Session
) -> None:
    """«Un presupuesto que cambia sin rastro no sirve para evaluar a nadie»."""
    cuerpo = {
        "periodo": PERIODO,
        "punto_venta_id": id_punto_venta(sesion, "402"),
        "categoria_id": id_categoria(sesion, "RES"),
        "monto": "1000000.00",
        "kilos": "500.000",
        "motivo": "Presupuesto inicial de agosto",
    }
    assert cliente_http.put("/api/v1/presupuesto", json=cuerpo, headers=analista).status_code == 200

    cuerpo["monto"] = "1200000.00"
    cuerpo["motivo"] = "Ajuste por apertura de nueva línea"
    assert cliente_http.put("/api/v1/presupuesto", json=cuerpo, headers=analista).status_code == 200

    historial = cliente_http.get(
        f"/api/v1/presupuesto/historial?periodo={PERIODO}", headers=analista
    ).json()
    cambio = next(h for h in historial if h["campo"] == "monto" and h["valor_anterior"])
    assert cambio["valor_anterior"] == "1000000.000"
    assert cambio["valor_nuevo"] == "1200000.000"
    assert cambio["motivo"] == "Ajuste por apertura de nueva línea"
    assert cambio["quien"] == "analista"


def test_un_periodo_cerrado_no_admite_cambios_de_presupuesto(
    cliente_http: TestClient,
    gerente: dict[str, str],
    analista: dict[str, str],
    sesion: Session,
) -> None:
    """Regla de §7."""
    assert (
        cliente_http.post(f"/api/v1/periodos/{PERIODO}/cerrar", headers=gerente).status_code == 200
    )

    respuesta = cliente_http.put(
        "/api/v1/presupuesto",
        json={
            "periodo": PERIODO,
            "punto_venta_id": id_punto_venta(sesion, "402"),
            "categoria_id": id_categoria(sesion, "RES"),
            "monto": "1000000.00",
            "kilos": "500.000",
            "motivo": "Intento sobre período cerrado",
        },
        headers=analista,
    )
    assert respuesta.status_code == 409
    assert "cerrado" in respuesta.text.lower()


# ── Autorización ──────────────────────────────────────────────────────────────


def test_sin_token_no_se_ve_ningun_reporte(cliente_http: TestClient) -> None:
    assert cliente_http.get(f"/api/v1/reportes/tablero?periodo={PERIODO}").status_code == 401


def test_el_rol_de_consulta_no_puede_parametrizar_presupuesto(
    cliente_http: TestClient, consulta: dict[str, str], sesion: Session
) -> None:
    respuesta = cliente_http.put(
        "/api/v1/presupuesto",
        json={
            "periodo": PERIODO,
            "punto_venta_id": id_punto_venta(sesion, "402"),
            "categoria_id": id_categoria(sesion, "RES"),
            "monto": "1000000.00",
            "kilos": "500.000",
            "motivo": "No debería poder",
        },
        headers=consulta,
    )
    assert respuesta.status_code == 403


def test_solo_gerencia_cierra_un_periodo(
    cliente_http: TestClient, analista: dict[str, str]
) -> None:
    respuesta = cliente_http.post(f"/api/v1/periodos/{PERIODO}/cerrar", headers=analista)
    assert respuesta.status_code == 403


def test_periodo_mal_formado_se_rechaza(cliente_http: TestClient, gerente: dict[str, str]) -> None:
    respuesta = cliente_http.get("/api/v1/reportes/tablero?periodo=agosto", headers=gerente)
    assert respuesta.status_code == 422


# ── Salud ─────────────────────────────────────────────────────────────────────


def test_salud_responde_sin_autenticacion(cliente_http: TestClient) -> None:
    cuerpo = cliente_http.get("/api/v1/salud").json()
    assert cuerpo["estado"] == "operativo"
    assert cuerpo["base_datos"] == "disponible"


def test_todos_los_puntos_de_venta_tienen_zona_con_calendario(
    estructura: None,
    sesion: Session,
) -> None:
    """Sin zona no hay días hábiles, y sin días hábiles no hay ideal ni semáforo."""
    puntos = sesion.scalars(select(PuntoVenta)).all()
    assert puntos
    assert all(p.zona_id is not None for p in puntos)
