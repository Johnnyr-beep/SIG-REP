"""Datos semilla: la estructura de §3 de la especificación.

Es **idempotente**: se puede correr sobre una base ya inicializada sin duplicar
nada. Los datos que siembra no son de ejemplo, son los reales del negocio: los
4 grupos, los 16 puntos de venta con su C.O. de SIESA, las 8 categorías, el
mapeo de categorías —con las dos variantes ortográficas de `0006`— y las zonas
de calendario.

Uso:

    python -m app.infrastructure.semilla                    # estructura
    python -m app.infrastructure.semilla --admin            # + usuario gerente
    python -m app.infrastructure.semilla --periodo 2026-08  # + calendario del mes
"""

from __future__ import annotations

import argparse
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.services.auth_service import AuthService
from app.application.services.periodos import obtener_o_crear_periodo
from app.core.config import obtener_settings
from app.core.db import sesion_ambito
from app.core.logging import configurar_logging, obtener_logger
from app.core.security import generar_password_temporal, hashear_password
from app.domain.enums import Rol
from app.infrastructure.models.catalogo import Categoria, MapeoCategoria
from app.infrastructure.models.organizacion import Grupo, PuntoVenta, Zona
from app.infrastructure.models.periodo import CalendarioZona
from app.infrastructure.models.usuario import Usuario

logger = obtener_logger(__name__)

# ── §3.1 Grupos comerciales ───────────────────────────────────────────────────

GRUPOS: list[tuple[str, str, int]] = [
    ("001", "GRUPO 1", 1),
    ("002", "GRUPO 2", 2),
    ("003", "GRUPO 3", 3),
    ("004", "GRUPO 4", 4),
]

# ── §3.1 Puntos de venta: (C.O., nombre SIGREP, descripción SIESA, grupo) ─────
#
# El C.O. es la llave de integración y viene de SIESA; no se inventa. La
# descripción se guarda tal cual la entrega el ERP, con sus erratas incluidas
# (`PDV BUCARMANGA`), porque es lo que permite conciliar a ojo con el origen.

PUNTOS_VENTA: list[tuple[str, str, str, str]] = [
    ("402", "MALAMBO", "PDV MALAMBO", "001"),
    ("603", "CONCORDE", "CONCORD", "001"),
    ("403", "LAGRANJA", "PDV LA GRANJA", "001"),
    ("406", "SIMON", "PDV SIMON", "001"),
    ("412", "BUCARAMANGA", "PDV BUCARMANGA", "002"),
    ("409", "PEREIRA", "PDV PEREIRA", "002"),
    ("415", "CARTAGENA", "PDV CARTAGENA", "002"),
    ("414", "CENTRO", "PDV CENTRO", "003"),
    ("701", "SANFELIPE", "SAN FELIPE", "003"),
    ("702", "OLAYA", "OLAYA", "003"),
    ("405", "LA43", "PDV LA 43", "003"),
    ("407", "LA70", "PDV LA 70", "004"),
    ("413", "LA93", "PDV LA 93", "004"),
    ("605", "ALAMEDA", "ALAMEDA 1", "004"),
    ("606", "ALAMEDA2", "ALAMEDA 2", "004"),
]

#: 432 EVENTOS BUCARAMANGA vende pero **no está presupuestado**. Se siembra
#: aparte y con `presupuestado=False` para que el sistema lo muestre sin
#: descuadrar el consolidado (§3.1).
PUNTO_SIN_PRESUPUESTO: tuple[str, str, str] = (
    "432",
    "EVENTOS BUCARAMANGA",
    "EVENTOS BUCARMANGA",
)

# ── §3.1 Categorías de negocio ────────────────────────────────────────────────

CATEGORIAS: list[tuple[str, str, int]] = [
    ("RES", "RES", 1),
    ("CERDO", "CERDO", 2),
    ("POLLO", "POLLO", 3),
    ("PESCADO", "PESCADO", 4),
    ("EMBUTIDOS", "EMBUTIDOS", 5),
    ("VISCERAS", "VISCERAS", 6),
    ("ASADERO", "ASADERO", 7),
    ("OTROS", "OTROS", 8),
]

# ── §3.1 Mapeo de categorías crudas de SIESA ──────────────────────────────────
#
# El mapeo es por **texto exacto**. Nótese que hay dos códigos `0006` con
# distinta ortografía y ambos deben estar sembrados: si faltara uno, esa venta
# caería en «desconocido» y el reporte de quesos y lácteos saldría a la mitad
# sin que nadie sepa por qué.

MAPEO_CATEGORIAS: list[tuple[str, str]] = [
    ("0001 - RES", "RES"),
    ("0002 - CERDO", "CERDO"),
    ("0003 - POLLO", "POLLO"),
    ("0004 - PESCADO", "PESCADO"),
    ("0005 - EMBUTIDOS", "EMBUTIDOS"),
    ("0009 - VISCERAS", "VISCERAS"),
    ("0010 - RESTAURANTE", "ASADERO"),
    ("0006 - QUESO Y LACTEOS", "OTROS"),
    ("0006 - QUESOS Y LACTEOS", "OTROS"),  # variante con typo, así viene de SIESA
    ("0007 - HUEVOS", "OTROS"),
    ("0008 - VIVERES", "OTROS"),
    ("0014 - DOMICILIOS", "OTROS"),
]

# ── §3.2 Zonas de calendario ──────────────────────────────────────────────────
#
# Días hábiles de agosto de 2026 tomados del Excel vigente. Las zonas marcadas
# con `None` **no tienen días hábiles confirmados por el usuario** (§8.1): se
# siembra el valor por defecto (28) como SUPUESTO y se parametriza en pantalla.

ZONAS: list[tuple[str, list[str], Decimal | None]] = [
    ("BUCARAMANGA Y CENTRO", ["412", "414"], Decimal("27.5")),
    ("CARTAGENA", ["415"], Decimal("24")),
    ("PEREIRA", ["409"], Decimal("27.5")),
    ("LA 70 / LA 43 / SIMON / LA GRANJA", ["407", "405", "406", "403"], Decimal("28.5")),
    # ── SUPUESTO: días hábiles pendientes de confirmar con el usuario ──────────
    # Se siembran como zonas independientes para que el negocio pueda fijarles
    # calendarios distintos sin migrar datos. Agruparlas «provisionalmente»
    # obligaría después a separarlas con presupuesto ya cargado.
    ("MALAMBO", ["402"], None),
    ("CONCORDE", ["603"], None),
    ("SAN FELIPE", ["701"], None),
    ("OLAYA", ["702"], None),
    ("LA 93", ["413"], None),
    ("ALAMEDA", ["605", "606"], None),
    ("EVENTOS", ["432"], None),
]


def sembrar_estructura(sesion: Session) -> None:
    """Siembra grupos, zonas, puntos de venta, categorías y mapeo."""
    grupos = _sembrar_grupos(sesion)
    zonas = _sembrar_zonas(sesion)
    _sembrar_puntos_venta(sesion, grupos, zonas)
    categorias = _sembrar_categorias(sesion)
    _sembrar_mapeo(sesion, categorias)
    logger.info("semilla_estructura_lista")


def _sembrar_grupos(sesion: Session) -> dict[str, Grupo]:
    existentes = {g.codigo: g for g in sesion.execute(select(Grupo)).scalars()}
    for codigo, nombre, orden in GRUPOS:
        if codigo in existentes:
            continue
        grupo = Grupo(codigo=codigo, nombre=nombre, orden=orden, activo=True)
        sesion.add(grupo)
        existentes[codigo] = grupo
    sesion.flush()
    return existentes


def _sembrar_zonas(sesion: Session) -> dict[str, Zona]:
    existentes = {z.nombre: z for z in sesion.execute(select(Zona)).scalars()}
    for nombre, _puntos, _dias in ZONAS:
        if nombre in existentes:
            continue
        zona = Zona(nombre=nombre, activa=True)
        sesion.add(zona)
        existentes[nombre] = zona
    sesion.flush()
    return existentes


def _sembrar_puntos_venta(
    sesion: Session, grupos: dict[str, Grupo], zonas: dict[str, Zona]
) -> None:
    zona_de_punto: dict[str, str] = {}
    for nombre_zona, codigos, _dias in ZONAS:
        for codigo in codigos:
            zona_de_punto[codigo] = nombre_zona

    existentes = {p.codigo_co for p in sesion.execute(select(PuntoVenta)).scalars()}

    for codigo, nombre, descripcion, codigo_grupo in PUNTOS_VENTA:
        if codigo in existentes:
            continue
        zona = zonas.get(zona_de_punto.get(codigo, ""))
        sesion.add(
            PuntoVenta(
                codigo_co=codigo,
                nombre=nombre,
                descripcion_siesa=descripcion,
                grupo_id=grupos[codigo_grupo].id,
                zona_id=zona.id if zona else None,
                activo=True,
                presupuestado=True,
            )
        )

    codigo, nombre, descripcion = PUNTO_SIN_PRESUPUESTO
    if codigo not in existentes:
        zona = zonas.get(zona_de_punto.get(codigo, ""))
        sesion.add(
            PuntoVenta(
                codigo_co=codigo,
                nombre=nombre,
                descripcion_siesa=descripcion,
                grupo_id=None,
                zona_id=zona.id if zona else None,
                activo=True,
                presupuestado=False,
            )
        )
    sesion.flush()


def _sembrar_categorias(sesion: Session) -> dict[str, Categoria]:
    existentes = {c.nombre: c for c in sesion.execute(select(Categoria)).scalars()}
    for codigo, nombre, orden in CATEGORIAS:
        if nombre in existentes:
            continue
        categoria = Categoria(codigo=codigo, nombre=nombre, orden=orden, activa=True)
        sesion.add(categoria)
        existentes[nombre] = categoria
    sesion.flush()
    return existentes


def _sembrar_mapeo(sesion: Session, categorias: dict[str, Categoria]) -> None:
    existentes = {m.texto_siesa for m in sesion.execute(select(MapeoCategoria)).scalars()}
    for texto, nombre_categoria in MAPEO_CATEGORIAS:
        if texto in existentes:
            continue
        sesion.add(MapeoCategoria(texto_siesa=texto, categoria_id=categorias[nombre_categoria].id))
    sesion.flush()


def sembrar_calendario(sesion: Session, codigo_periodo: str) -> None:
    """Siembra el calendario de todas las zonas para un período.

    Las zonas sin días hábiles confirmados reciben el valor por defecto
    (`SIGREP_DIAS_HABILES_POR_DEFECTO`, 28). Es un SUPUESTO explícito de §8.1 y
    está pensado para que el analista lo corrija en pantalla, no para quedarse.
    """
    periodo = obtener_o_crear_periodo(sesion, codigo_periodo)
    por_defecto = obtener_settings().dias_habiles_por_defecto

    zonas = {z.nombre: z for z in sesion.execute(select(Zona)).scalars()}
    existentes = {
        fila.zona_id
        for fila in sesion.execute(
            select(CalendarioZona).where(CalendarioZona.periodo_id == periodo.id)
        ).scalars()
    }

    for nombre, _puntos, dias in ZONAS:
        zona = zonas.get(nombre)
        if zona is None or zona.id in existentes:
            continue
        sesion.add(
            CalendarioZona(
                periodo_id=periodo.id,
                zona_id=zona.id,
                dias_habiles=dias if dias is not None else por_defecto,
                dias_trabajados=None,  # derivado de la fecha de corte
            )
        )
    sesion.flush()
    logger.info("semilla_calendario_lista", periodo=codigo_periodo)


def crear_gerente(sesion: Session, clave: str | None = None) -> tuple[Usuario, str] | None:
    """Crea la cuenta `gerente` con clave provisional de cambio obligatorio."""
    existente = sesion.execute(
        select(Usuario).where(Usuario.usuario == "gerente")
    ).scalar_one_or_none()
    if existente is not None:
        logger.info("semilla_gerente_existente")
        return None

    if clave is None:
        clave = generar_password_temporal(18)
    else:
        # Una clave provista a mano se somete a la misma política que
        # cualquier otra: la semilla no es una puerta trasera.
        AuthService.validar_fortaleza_clave(clave, usuario_nombre="gerente")

    usuario = Usuario(
        usuario="gerente",
        nombre="Gerencia General",
        email="gerencia@gruposantacruz.co",
        rol=Rol.GERENTE.value,
        password_hash=hashear_password(clave),
        debe_cambiar_password=True,
        activo=True,
    )
    sesion.add(usuario)
    sesion.flush()
    return usuario, clave


def main() -> None:  # pragma: no cover - utilidad de línea de comandos
    parser = argparse.ArgumentParser(description="Siembra los datos base de SIGREP.")
    parser.add_argument("--admin", action="store_true", help="crea el usuario gerente")
    parser.add_argument("--clave", help="clave del usuario gerente (si no, se genera)")
    parser.add_argument("--periodo", help="siembra el calendario de un período YYYY-MM")
    argumentos = parser.parse_args()

    configurar_logging(obtener_settings().entorno)

    with sesion_ambito() as sesion:
        sembrar_estructura(sesion)
        if argumentos.periodo:
            sembrar_calendario(sesion, argumentos.periodo)
        if argumentos.admin:
            creado = crear_gerente(sesion, argumentos.clave)
            if creado is not None:
                _, clave = creado
                print(f"Usuario 'gerente' creado. Clave provisional: {clave}")


if __name__ == "__main__":  # pragma: no cover
    main()
