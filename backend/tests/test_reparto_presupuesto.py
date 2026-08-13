"""El reparto del presupuesto de una categoría retirada (§3.3, §7).

Lo que se prueba aquí no es «que el reparto funcione»: es que **no se pierda ni
se invente un peso** y que cada punto de venta reciba su propio perfil de
consumo y no el de otro. Son 616 000 000 sobre un presupuesto de 20 000 000 000,
y un céntimo que se escape aquí reaparece tres pantallas más abajo como un
consolidado que no cuadra y que nadie sabe explicar.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.services.presupuesto_service import (
    PresupuestoService,
    ResultadoReparto,
    motivo_reparto,
)
from app.core.errors import ErrorPeriodoCerrado, ErrorValidacion
from app.core.security import hashear_password
from app.domain.enums import Rol
from app.domain.normalizacion import (
    ESCALA_DINERO,
    SUFIJO_RETIRADA,
    destinos_de_categoria_retirada,
)
from app.domain.reparto import (
    NIVEL_GLOBAL,
    NIVEL_IGUALES,
    NIVEL_PUNTO,
    elegir_pesos,
    indice_de_mayor_peso,
    repartir_proporcional,
)
from app.infrastructure.models.catalogo import Categoria
from app.infrastructure.models.periodo import Periodo
from app.infrastructure.models.presupuesto import Presupuesto, PresupuestoHistorial
from app.infrastructure.models.usuario import Usuario
from tests.conftest import (
    CLAVE,
    PERIODO,
    dar_presupuesto,
    dar_venta,
    id_categoria,
    id_periodo,
    id_punto_venta,
)

#: El nombre que la migración `0004` le dejó a `OTROS` al retirarla.
CAJON = "OTROS" + SUFIJO_RETIRADA

#: Las cuatro categorías reales entre las que se reparte, en el orden en que las
#: declara `CATEGORIAS_RETIRADAS`.
DESTINOS = destinos_de_categoria_retirada("OTROS")
assert DESTINOS is not None


# ── Montaje ───────────────────────────────────────────────────────────────────


def crear_cajon(sesion: Session) -> Categoria:
    """La categoría retirada, tal como la dejó la migración `0004`.

    La semilla ya no la siembra —siembra las once reales—, así que las pruebas
    la reconstruyen con el mismo nombre, orden y estado desactivado con los que
    la marcó la migración.
    """
    categoria = Categoria(codigo="OTROS", nombre=CAJON, orden=99, activa=False)
    sesion.add(categoria)
    sesion.commit()
    return categoria


def servicio(sesion: Session) -> PresupuestoService:
    return PresupuestoService(sesion)


def crear_autor(sesion: Session) -> Usuario:
    usuario = Usuario(
        usuario="operacion",
        nombre="Operación",
        password_hash=hashear_password(CLAVE),
        rol=Rol.ANALISTA.value,
        activo=True,
        debe_cambiar_password=False,
    )
    sesion.add(usuario)
    sesion.commit()
    return usuario


def presupuesto_de(sesion: Session, codigo_co: str, nombre_categoria: str) -> Presupuesto | None:
    return sesion.execute(
        select(Presupuesto).where(
            Presupuesto.periodo_id == id_periodo(sesion),
            Presupuesto.punto_venta_id == id_punto_venta(sesion, codigo_co),
            Presupuesto.categoria_id == id_categoria(sesion, nombre_categoria),
        )
    ).scalar_one_or_none()


def montos(resultado: ResultadoReparto, codigo_co: str) -> dict[str, Decimal]:
    punto = next(p for p in resultado.puntos if p.punto_venta == codigo_co)
    return {parte.categoria: parte.monto for parte in punto.partes}


def repartir(sesion: Session, **extra: object) -> ResultadoReparto:
    return servicio(sesion).repartir_categoria_retirada(
        codigo_periodo=PERIODO,
        nombre_categoria=CAJON,
        **extra,  # type: ignore[arg-type]
    )


# ── La función pura: donde se escapan los céntimos ────────────────────────────


def test_la_suma_de_las_partes_es_exactamente_el_total() -> None:
    """Tres partes iguales de una cifra que no se divide entre tres.

    1 000 000,01 / 3 = 333 333,336666…, que redondeado a dos decimales da
    333 333,34 tres veces: 1 000 000,02. Dos céntimos de más. El reparto tiene
    que devolver 1 000 000,01 clavado.
    """
    partes = repartir_proporcional(
        Decimal("1000000.01"), [Decimal(1), Decimal(1), Decimal(1)], ESCALA_DINERO
    )
    assert sum(partes) == Decimal("1000000.01")
    assert all(parte >= 0 for parte in partes)


@pytest.mark.parametrize(
    "total",
    ["0.01", "0.02", "0.07", "133335.00", "616000000.00", "19551895.23", "83598999.43"],
)
@pytest.mark.parametrize(
    "pesos",
    [
        [1, 1, 1, 1],
        [3, 1, 1, 1],
        [1000000, 3, 7, 11],
        [1, 0, 0, 0],
        [7, 7, 7, 1],
        [999983, 999979, 999961, 999959],
    ],
)
def test_ninguna_combinacion_de_total_y_pesos_pierde_ni_inventa(
    total: str, pesos: list[int]
) -> None:
    """La garantía, sobre una malla de casos incómodos a propósito.

    Incluye totales de uno y dos céntimos porque son los que producen residuo
    **negativo**: cuatro partes redondeadas hacia arriba suman más que el total,
    y sumar ese residuo a secas dejaría un presupuesto negativo que la tabla
    rechaza por `ck_presupuesto_monto_no_negativo`.
    """
    decimales = [Decimal(p) for p in pesos]
    partes = repartir_proporcional(Decimal(total), decimales, ESCALA_DINERO)

    assert sum(partes) == Decimal(total), f"el reparto de {total} entre {pesos} no cuadra"
    assert all(parte >= 0 for parte in partes), f"parte negativa repartiendo {total} entre {pesos}"


def test_el_residuo_va_a_la_categoria_de_mayor_venta() -> None:
    """Los dos signos del residuo, y en los dos lo absorbe la que más vende.

    **Residuo positivo.** 10,00 entre pesos 1, 1 y 1: cada parte es 3,3333… →
    3,33, y las tres suman 9,99. Falta un céntimo. Con pesos empatados manda el
    primero, que es el desempate declarado.

    **Residuo negativo.** 10,00 entre pesos 1, 1 y 4: 1,6666… → 1,67 dos veces y
    6,6666… → 6,67, que suman 10,01. Sobra un céntimo y sale del destino de peso
    4 —el tercero, no el primero—, que es el único sitio del que puede salir sin
    distorsionar en términos relativos.
    """
    positivo = repartir_proporcional(
        Decimal("10.00"), [Decimal(1), Decimal(1), Decimal(1)], ESCALA_DINERO
    )
    assert positivo == [Decimal("3.34"), Decimal("3.33"), Decimal("3.33")]
    assert sum(positivo) == Decimal("10.00")

    negativo = repartir_proporcional(
        Decimal("10.00"), [Decimal(1), Decimal(1), Decimal(4)], ESCALA_DINERO
    )
    assert indice_de_mayor_peso([Decimal(1), Decimal(1), Decimal(4)]) == 2
    assert negativo == [Decimal("1.67"), Decimal("1.67"), Decimal("6.66")]
    assert sum(negativo) == Decimal("10.00")


def test_la_cascada_baja_un_escalon_solo_cuando_hace_falta() -> None:
    cero = [Decimal(0), Decimal(0)]
    pesos, nivel = elegir_pesos([Decimal(3), Decimal(1)], cero)
    assert (pesos, nivel) == ([Decimal(3), Decimal(1)], NIVEL_PUNTO)

    pesos, nivel = elegir_pesos(cero, [Decimal(2), Decimal(8)])
    assert (pesos, nivel) == ([Decimal(2), Decimal(8)], NIVEL_GLOBAL)

    pesos, nivel = elegir_pesos(cero, cero)
    assert (pesos, nivel) == ([Decimal(1), Decimal(1)], NIVEL_IGUALES)


def test_el_motivo_cabe_en_la_columna() -> None:
    """`presupuesto_historial.motivo` es `String(400)` y no se puede desbordar."""
    for nivel_monto in (NIVEL_PUNTO, NIVEL_GLOBAL, NIVEL_IGUALES):
        for nivel_kilos in (NIVEL_PUNTO, NIVEL_GLOBAL, NIVEL_IGUALES):
            motivo = motivo_reparto(PERIODO, CAJON, nivel_monto, nivel_kilos)
            assert len(motivo) <= 400, f"{len(motivo)} caracteres: {motivo}"
            assert CAJON in motivo
            assert "confirmarla" in motivo


# ── El reparto contra la base ─────────────────────────────────────────────────


def test_el_reparto_usa_la_venta_de_ese_punto_y_no_la_global(
    sesion: Session, estructura: None
) -> None:
    """Dos puntos con perfiles opuestos y el mismo presupuesto en el cajón.

    402 vende huevos y casi nada de víveres; 413 exactamente al revés. Si el
    reparto usara la proporción global —que entre los dos queda 50/50— ambos
    recibirían la mitad y la mitad, y a cada uno se le habría puesto el consumo
    del otro. Es el defecto que esta prueba existe para impedir.
    """
    crear_cajon(sesion)
    dar_venta(sesion, "402", "HUEVOS", 3, "9000000", kilos="900")
    dar_venta(sesion, "402", "VIVERES", 3, "1000000", kilos="100")
    dar_venta(sesion, "413", "HUEVOS", 3, "1000000", kilos="100")
    dar_venta(sesion, "413", "VIVERES", 3, "9000000", kilos="900")
    dar_presupuesto(sesion, "402", "OTROS", "1000000", kilos="100")
    dar_presupuesto(sesion, "413", "OTROS", "1000000", kilos="100")

    resultado = repartir(sesion)
    sesion.commit()

    en_402, en_413 = montos(resultado, "402"), montos(resultado, "413")
    print()
    print(f"  402 (vende huevos)  → {en_402}")
    print(f"  413 (vende víveres) → {en_413}")

    assert en_402["HUEVOS"] == Decimal("900000.00")
    assert en_402["VIVERES"] == Decimal("100000.00")
    assert en_413["HUEVOS"] == Decimal("100000.00")
    assert en_413["VIVERES"] == Decimal("900000.00")
    assert all(punto.nivel_monto == NIVEL_PUNTO for punto in resultado.puntos)

    # Y quedó escrito en la base, no solo en el objeto devuelto.
    fila = presupuesto_de(sesion, "402", "HUEVOS")
    assert fila is not None and fila.monto == Decimal("900000.00")


def test_los_kilos_siguen_a_los_kilos_y_no_al_dinero(sesion: Session, estructura: None) -> None:
    """DOMICILIOS pesa poco en pesos y mucho en kilos; cada magnitud va por su lado.

    Es el caso real: en el período cargado DOMICILIOS es el 6 % de la venta en
    dinero de las cuatro categorías y el 19 % en kilos. Repartir los kilos con la
    proporción del dinero le daría un presupuesto en kilos que no tiene nada que
    ver con lo que mueve.
    """
    crear_cajon(sesion)
    dar_venta(sesion, "402", "HUEVOS", 3, "9000000", kilos="100")
    dar_venta(sesion, "402", "DOMICILIOS", 3, "1000000", kilos="900")
    dar_presupuesto(sesion, "402", "OTROS", "1000000", kilos="1000")

    resultado = repartir(sesion)
    sesion.commit()

    punto = resultado.puntos[0]
    por_categoria = {parte.categoria: parte for parte in punto.partes}
    print()
    print(f"  HUEVOS     → {por_categoria['HUEVOS'].monto} y {por_categoria['HUEVOS'].kilos} kg")
    print(
        f"  DOMICILIOS → {por_categoria['DOMICILIOS'].monto} "
        f"y {por_categoria['DOMICILIOS'].kilos} kg"
    )

    assert por_categoria["HUEVOS"].monto == Decimal("900000.00")
    assert por_categoria["HUEVOS"].kilos == Decimal("100.000")
    assert por_categoria["DOMICILIOS"].monto == Decimal("100000.00")
    assert por_categoria["DOMICILIOS"].kilos == Decimal("900.000")


def test_sin_venta_en_el_punto_se_usa_la_proporcion_global(
    sesion: Session, estructura: None
) -> None:
    """Segundo escalón de la cascada, y queda dicho en el motivo."""
    crear_cajon(sesion)
    # 413 vende; 402 no vende nada en las cuatro categorías destino.
    dar_venta(sesion, "413", "HUEVOS", 3, "7500000", kilos="750")
    dar_venta(sesion, "413", "VIVERES", 3, "2500000", kilos="250")
    dar_presupuesto(sesion, "402", "OTROS", "1000000", kilos="100")

    resultado = repartir(sesion)
    sesion.commit()

    punto = resultado.puntos[0]
    print()
    print(f"  402 sin venta propia → {montos(resultado, '402')} (nivel {punto.nivel_monto})")

    assert punto.nivel_monto == NIVEL_GLOBAL
    assert montos(resultado, "402")["HUEVOS"] == Decimal("750000.00")
    assert montos(resultado, "402")["VIVERES"] == Decimal("250000.00")

    motivos = sesion.execute(select(PresupuestoHistorial.motivo)).scalars().all()
    assert any("proporción global" in motivo for motivo in motivos), motivos


def test_sin_venta_ninguna_se_reparte_a_partes_iguales(sesion: Session, estructura: None) -> None:
    """Tercer escalón: no se estima, se declara que no se sabe nada."""
    crear_cajon(sesion)
    dar_presupuesto(sesion, "402", "OTROS", "1000000", kilos="100")

    resultado = repartir(sesion)
    sesion.commit()

    punto = resultado.puntos[0]
    print()
    print(f"  402 sin venta alguna → {montos(resultado, '402')} (nivel {punto.nivel_monto})")

    assert punto.nivel_monto == NIVEL_IGUALES
    assert punto.nivel_kilos == NIVEL_IGUALES
    assert set(montos(resultado, "402").values()) == {Decimal("250000.00")}
    assert punto.monto_repartido == Decimal("1000000.00")

    motivos = sesion.execute(select(PresupuestoHistorial.motivo)).scalars().all()
    assert any("partes iguales" in motivo for motivo in motivos), motivos


def test_el_total_del_presupuesto_no_cambia_ni_en_un_peso(
    sesion: Session, estructura: None
) -> None:
    """La prueba que importa: mover 616 millones sin alterar el total.

    Se monta con cifras que no se dividen bien a propósito —las reales del
    negocio para tres puntos— y se comprueba el total antes y después.
    """
    crear_cajon(sesion)
    for codigo, huevos, viveres, quesos, domicilios in (
        ("402", "2776320", "979503", "1588032", "356000"),
        ("412", "2574958", "3257221", "10405096", "1229000"),
        ("606", "5089293.50", "4112276.15", "2081293.69", "495692"),
    ):
        dar_venta(sesion, codigo, "HUEVOS", 3, huevos, kilos="11.111")
        dar_venta(sesion, codigo, "VIVERES", 3, viveres, kilos="7.777")
        dar_venta(sesion, codigo, "QUESO Y LACTEOS", 3, quesos, kilos="3.333")
        dar_venta(sesion, codigo, "DOMICILIOS", 3, domicilios, kilos="1.001")

    dar_presupuesto(sesion, "402", "RES", "8505422046.46", kilos="523518.137")
    dar_presupuesto(sesion, "402", "OTROS", "19551895.23", kilos="1260.002")
    dar_presupuesto(sesion, "412", "OTROS", "83598999.43", kilos="5040.010")
    dar_presupuesto(sesion, "606", "OTROS", "21887543.53", kilos="1356.926")

    antes_monto = sum(sesion.execute(select(Presupuesto.monto)).scalars(), Decimal("0.00"))
    antes_kilos = sum(sesion.execute(select(Presupuesto.kilos)).scalars(), Decimal("0.000"))

    resultado = repartir(sesion)
    sesion.commit()
    sesion.expire_all()

    despues_monto = sum(sesion.execute(select(Presupuesto.monto)).scalars(), Decimal("0.00"))
    despues_kilos = sum(sesion.execute(select(Presupuesto.kilos)).scalars(), Decimal("0.000"))

    print()
    print(f"  Presupuesto antes  : {antes_monto} · {antes_kilos} kg")
    print(f"  Presupuesto después: {despues_monto} · {despues_kilos} kg")

    assert despues_monto == antes_monto, "el reparto movió el total del presupuesto"
    assert despues_kilos == antes_kilos, "el reparto movió el total de kilos"
    assert resultado.cuadra
    assert resultado.monto_origen == Decimal("125038438.19")

    # Y la categoría retirada se quedó sin una sola fila: es lo que permite que
    # la migración 0005 la borre.
    quedan = (
        sesion.execute(
            select(Presupuesto).where(Presupuesto.categoria_id == id_categoria(sesion, "OTROS"))
        )
        .scalars()
        .all()
    )
    assert quedan == []


def test_el_reparto_suma_sobre_el_presupuesto_que_la_categoria_ya_tenia(
    sesion: Session, estructura: None
) -> None:
    """Reemplazar destruiría lo que alguien capturó antes en QUESO Y LACTEOS."""
    crear_cajon(sesion)
    dar_venta(sesion, "402", "QUESO Y LACTEOS", 3, "1000000", kilos="100")
    dar_presupuesto(sesion, "402", "QUESO Y LACTEOS", "500000", kilos="50")
    dar_presupuesto(sesion, "402", "OTROS", "1000000", kilos="100")

    repartir(sesion)
    sesion.commit()
    sesion.expire_all()

    fila = presupuesto_de(sesion, "402", "QUESO Y LACTEOS")
    assert fila is not None
    print()
    print(f"  QUESO Y LACTEOS: 500 000 capturados + 1 000 000 repartidos = {fila.monto}")
    assert fila.monto == Decimal("1500000.00")
    assert fila.kilos == Decimal("150.000")


def test_el_historial_queda_con_autor_y_con_el_motivo_del_reparto(
    sesion: Session, estructura: None
) -> None:
    """§3.3: un presupuesto que cambia sin rastro no sirve para evaluar a nadie."""
    crear_cajon(sesion)
    autor = crear_autor(sesion)
    dar_venta(sesion, "402", "HUEVOS", 3, "1000000", kilos="100")
    dar_presupuesto(sesion, "402", "OTROS", "1000000", kilos="100")

    repartir(sesion, usuario=autor)
    sesion.commit()

    entradas = sesion.execute(select(PresupuestoHistorial)).scalars().all()
    del_reparto = [e for e in entradas if "Reparto proporcional" in e.motivo]
    print()
    print(f"  {len(del_reparto)} entradas de historial escritas por el reparto")
    for entrada in del_reparto[:3]:
        print(f"    {entrada.campo}: {entrada.valor_anterior} → {entrada.valor_nuevo}")

    assert del_reparto, "el reparto no dejó rastro en presupuesto_historial"
    assert all(entrada.usuario_id == autor.id for entrada in del_reparto)
    assert all(PERIODO in entrada.motivo for entrada in del_reparto)
    assert all("confirmarla" in entrada.motivo for entrada in del_reparto)

    # La contrapartida: la baja del cajón está historiada, no solo las altas.
    bajas = [e for e in del_reparto if e.categoria_id == id_categoria(sesion, "OTROS")]
    assert bajas, "se historiaron las altas pero no el vaciado de la categoría retirada"
    assert {e.campo for e in bajas} == {"monto", "kilos"}
    assert [e.valor_nuevo for e in bajas] == [Decimal(0), Decimal(0)]

    # Y el historial sobrevivió al borrado de la fila de presupuesto: la fila ya
    # no existe, pero el renglón que cuenta lo que le pasó sí.
    assert all(entrada.presupuesto_id is None for entrada in bajas)


def test_un_periodo_cerrado_rechaza_el_reparto(sesion: Session, estructura: None) -> None:
    """§7: sobre un período cerrado no se toca el presupuesto, ni siquiera aquí."""
    crear_cajon(sesion)
    dar_presupuesto(sesion, "402", "OTROS", "1000000")
    periodo = sesion.get(Periodo, id_periodo(sesion))
    assert periodo is not None
    periodo.cerrado = True
    sesion.commit()

    with pytest.raises(ErrorPeriodoCerrado) as excepcion:
        repartir(sesion)
    print()
    print(f"  {excepcion.value.mensaje}")

    sesion.rollback()
    quedan = (
        sesion.execute(
            select(Presupuesto).where(Presupuesto.categoria_id == id_categoria(sesion, "OTROS"))
        )
        .scalars()
        .all()
    )
    assert len(quedan) == 1, "el período cerrado no impidió el reparto"


def test_repetir_el_reparto_no_cambia_nada(sesion: Session, estructura: None) -> None:
    """Idempotente: la segunda pasada no encuentra nada que repartir."""
    crear_cajon(sesion)
    dar_venta(sesion, "402", "HUEVOS", 3, "1000000", kilos="100")
    dar_presupuesto(sesion, "402", "OTROS", "1000000", kilos="100")

    repartir(sesion)
    sesion.commit()
    total_tras_la_primera = sum(
        sesion.execute(select(Presupuesto.monto)).scalars(), Decimal("0.00")
    )

    segunda = repartir(sesion)
    sesion.commit()
    sesion.expire_all()

    print()
    print(f"  Segunda pasada: {len(segunda.puntos)} puntos, {segunda.monto_origen} repartidos")
    assert segunda.puntos == ()
    assert sum(sesion.execute(select(Presupuesto.monto)).scalars(), Decimal("0.00")) == (
        total_tras_la_primera
    )


def test_la_simulacion_no_escribe_nada(sesion: Session, estructura: None) -> None:
    crear_cajon(sesion)
    dar_venta(sesion, "402", "HUEVOS", 3, "1000000", kilos="100")
    dar_presupuesto(sesion, "402", "OTROS", "1000000", kilos="100")

    resultado = repartir(sesion, simulacion=True)
    sesion.commit()
    sesion.expire_all()

    print()
    print(f"  Simulado: {montos(resultado, '402')}")
    assert resultado.simulacion is True
    assert resultado.cuadra
    assert presupuesto_de(sesion, "402", "HUEVOS") is None
    fila = presupuesto_de(sesion, "402", "OTROS")
    assert fila is not None and fila.monto == Decimal("1000000.00")
    assert sesion.execute(select(PresupuestoHistorial)).scalars().all() == []


def test_una_categoria_no_puede_ser_destino_de_su_propio_reparto(
    sesion: Session, estructura: None
) -> None:
    crear_cajon(sesion)
    with pytest.raises(ErrorValidacion):
        repartir(sesion, destinos=["HUEVOS", CAJON])
