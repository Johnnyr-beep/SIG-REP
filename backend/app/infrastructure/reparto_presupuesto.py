"""Reparto del presupuesto de una categoría retirada, por línea de órdenes.

Es una **operación de mantenimiento que se corre una vez**, igual que la semilla
y con la misma forma (`python -m ...`), no un endpoint. Deliberadamente:

- Mueve 616 000 000 de presupuesto de una sola vez. Eso no se dispara desde un
  botón que alguien pueda pulsar dos veces mientras mira otra cosa; se ejecuta a
  conciencia, con `--simular` delante y mirando la salida.
- Es el paso previo obligatorio de la migración `0005`, que se niega a borrar la
  categoría mientras le quede presupuesto. Un comando y una migración se
  encadenan en un procedimiento de despliegue; un endpoint no.

Uso:

    # 1. Ver el reparto sin tocar nada
    python -m app.infrastructure.reparto_presupuesto --periodo 2026-08 --simular

    # 2. Aplicarlo
    python -m app.infrastructure.reparto_presupuesto --periodo 2026-08 --usuario gerente

    # 3. Ya se puede borrar la categoría
    alembic upgrade head

`--usuario` es obligatorio al aplicar: §3.3 exige autor en cada cambio de
presupuesto y un reparto sin firma es exactamente lo que no se quiere encontrar
dentro de seis meses. En simulación no se pide porque no se escribe nada.
"""

from __future__ import annotations

import argparse
import sys
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.services.presupuesto_service import PresupuestoService, ResultadoReparto
from app.core.config import obtener_settings
from app.core.db import sesion_ambito
from app.core.errors import ErrorSigrep
from app.core.logging import configurar_logging, obtener_logger
from app.domain.normalizacion import CATEGORIAS_RETIRADAS, SUFIJO_RETIRADA
from app.infrastructure.models.usuario import Usuario

logger = obtener_logger(__name__)

#: La categoría que hay que repartir hoy: `OTROS`, tal como la dejó marcada la
#: migración `0004` al retirarla sin borrarla.
CATEGORIA_POR_DEFECTO = next(iter(CATEGORIAS_RETIRADAS)) + SUFIJO_RETIRADA


def _usuario_por_nombre(sesion: Session, nombre: str) -> Usuario:
    usuario = sesion.execute(select(Usuario).where(Usuario.usuario == nombre)).scalar_one_or_none()
    if usuario is None:
        raise SystemExit(
            f"No existe el usuario {nombre!r}. El reparto tiene que quedar firmado (§3.3); "
            "indique una cuenta real con --usuario."
        )
    return usuario


def _miles(valor: Decimal) -> str:
    """`19551895.23` → `'19.551.895,23'`. Formato colombiano, como el negocio."""
    entero, _, decimales = f"{valor:.2f}".partition(".")
    negativo, entero = (entero.startswith("-"), entero.lstrip("-"))
    agrupado = f"{int(entero):,}".replace(",", ".")
    return f"{'-' if negativo else ''}{agrupado},{decimales}"


def imprimir(resultado: ResultadoReparto) -> None:
    """Vuelca el reparto en la salida estándar, punto por punto y con el total.

    Se imprime **siempre**, también al aplicar: es el comprobante de la
    operación y lo que alguien pega en el registro del despliegue.
    """
    cabecera = "SIMULACIÓN — no se ha escrito nada" if resultado.simulacion else "APLICADO"
    print(f"\n  Reparto de «{resultado.categoria_retirada}» · período {resultado.periodo}")
    print(f"  {cabecera}")
    print(f"  Destinos: {', '.join(resultado.destinos)}\n")

    if not resultado.puntos:
        print("  No hay presupuesto que repartir en esa categoría. Nada que hacer.\n")
        return

    ancho = max(len(nombre) for nombre in resultado.destinos)
    for punto in resultado.puntos:
        print(f"  {punto.punto_venta}  origen {_miles(punto.monto_origen):>18}")
        for parte in punto.partes:
            print(
                f"      {parte.categoria:<{ancho}}  {_miles(parte.monto):>18}  {parte.kilos:>12} kg"
            )
        if punto.nivel_monto != "punto" or punto.nivel_kilos != "punto":
            print(f"      (base: monto={punto.nivel_monto}, kilos={punto.nivel_kilos})")

    print(f"\n  Total origen   : {_miles(resultado.monto_origen):>18}  {resultado.kilos_origen} kg")
    print(
        f"  Total repartido: {_miles(resultado.monto_repartido):>18}  "
        f"{resultado.kilos_repartidos} kg"
    )
    print(f"  ¿Cuadra?       : {'sí' if resultado.cuadra else 'NO'}\n")


def main() -> None:  # pragma: no cover - utilidad de línea de comandos
    parser = argparse.ArgumentParser(
        description=(
            "Reparte el presupuesto de una categoría retirada entre las categorías que la "
            "sustituyen, a prorrata de la venta ya cargada del período, punto de venta a "
            "punto de venta."
        )
    )
    parser.add_argument(
        "--periodo", required=True, help="período YYYY-MM cuyo presupuesto se reparte"
    )
    parser.add_argument(
        "--categoria",
        default=CATEGORIA_POR_DEFECTO,
        help=f"categoría retirada a vaciar (por omisión «{CATEGORIA_POR_DEFECTO}»)",
    )
    parser.add_argument(
        "--destinos",
        nargs="+",
        help="categorías destino (por omisión, las de CATEGORIAS_RETIRADAS)",
    )
    parser.add_argument("--usuario", help="cuenta que firma el cambio; obligatoria al aplicar")
    parser.add_argument(
        "--simular",
        action="store_true",
        help="calcula e imprime el reparto sin escribir nada",
    )
    argumentos = parser.parse_args()

    configurar_logging(obtener_settings().entorno)

    if not argumentos.simular and not argumentos.usuario:
        raise SystemExit(
            "Falta --usuario. Todo cambio de presupuesto queda con autor (§3.3); "
            "use --simular si solo quiere ver los números."
        )

    with sesion_ambito() as sesion:
        servicio = PresupuestoService(sesion)
        usuario = _usuario_por_nombre(sesion, argumentos.usuario) if argumentos.usuario else None
        try:
            resultado = servicio.repartir_categoria_retirada(
                codigo_periodo=argumentos.periodo,
                nombre_categoria=argumentos.categoria,
                destinos=argumentos.destinos,
                usuario=usuario,
                simulacion=argumentos.simular,
            )
        except ErrorSigrep as exc:
            print(f"\n  El reparto no se aplicó: {exc.mensaje}\n", file=sys.stderr)
            raise SystemExit(1) from exc
        imprimir(resultado)


if __name__ == "__main__":  # pragma: no cover
    main()
