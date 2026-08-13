"""Reparto de una cifra entre varios destinos sin perder ni inventar pesos.

Vive en `domain` y no en el servicio por la misma razón que `normalizacion.py`:
todas las funciones de este módulo son **puras** —no tocan la base, no saben
nada de SQLAlchemy— y el sitio donde se escapan los céntimos es justo este. Una
función pura se prueba con una tabla de casos; la misma lógica incrustada en un
método que además abre transacciones, no.

El problema que resuelve es concreto. `OTROS` se retira y sus 616 000 000 de
presupuesto tienen que acabar en QUESO Y LACTEOS, HUEVOS, VIVERES y DOMICILIOS.
El reparto a prorrata da cuatro cocientes con infinitos decimales; la columna
tiene dos. Redondear cada parte por su cuenta y sumarlas da **casi** el total, y
ese «casi» es lo que descuadra el consolidado de la compañía tres pantallas más
abajo, cuando ya nadie recuerda de dónde salió.

De ahí las dos garantías que este módulo firma:

1. `sum(repartir_proporcional(total, pesos, escala)) == total`, **exactamente**,
   con `Decimal` de extremo a extremo y sin pasar jamás por `float`.
2. El residuo del redondeo se asigna a la **categoría de mayor peso**, es decir
   a la que más vende. Es la que menos distorsiona en términos relativos y, sobre
   todo, es una regla fija: dos ejecuciones sobre los mismos datos dan el mismo
   resultado.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

#: De dónde salió la proporción con la que se repartió. Viaja hasta el motivo
#: que queda escrito en `presupuesto_historial`: quien lea ese renglón dentro de
#: un año tiene derecho a saber si la cifra salió de la venta de su propio punto
#: o de un promedio de la compañía.
Nivel = Literal["punto", "global", "iguales"]

NIVEL_PUNTO: Nivel = "punto"
NIVEL_GLOBAL: Nivel = "global"
NIVEL_IGUALES: Nivel = "iguales"

#: Texto corto de cada nivel, para componer el motivo del historial.
DESCRIPCION_NIVEL: dict[Nivel, str] = {
    NIVEL_PUNTO: "la venta del propio punto de venta",
    NIVEL_GLOBAL: "la proporción global del período (el punto no registró venta)",
    NIVEL_IGUALES: "partes iguales (no hay venta cargada en el período)",
}


def elegir_pesos(
    pesos_punto: Sequence[Decimal],
    pesos_globales: Sequence[Decimal],
) -> tuple[list[Decimal], Nivel]:
    """La cascada del reparto, en un solo sitio y devolviendo de dónde salió.

    Tres escalones, del más específico al más grosero:

    1. **La venta del propio punto de venta.** Es el caso normal y el único que
       no distorsiona: cada PDV tiene su perfil de consumo y repartir el
       presupuesto de MALAMBO con la proporción de BUCARAMANGA le pondría a uno
       el consumo del otro.
    2. **La proporción global del período**, si ese punto no vendió nada en
       ninguna de las categorías destino. No es su perfil, pero es una
       proporción observada en el mismo período y en el mismo negocio.
    3. **Partes iguales**, si tampoco hay venta global. Ocurre cuando se reparte
       antes de la primera ingesta del mes. No es una estimación: es un reparto
       neutro que declara no saber nada, y el motivo que queda en el historial
       lo dice con esas palabras.

    Devolver el nivel junto a los pesos —y no solo los pesos— es lo que impide
    que el escalón 3 se confunda con el 1 al leer el historial.
    """
    if not pesos_punto and not pesos_globales:
        raise ValueError("No hay categorías destino sobre las que repartir.")
    if sum(pesos_punto, Decimal(0)) > 0:
        return list(pesos_punto), NIVEL_PUNTO
    if sum(pesos_globales, Decimal(0)) > 0:
        return list(pesos_globales), NIVEL_GLOBAL
    cuantos = len(pesos_punto) or len(pesos_globales)
    return [Decimal(1)] * cuantos, NIVEL_IGUALES


def repartir_proporcional(
    total: Decimal,
    pesos: Sequence[Decimal],
    escala: Decimal,
) -> list[Decimal]:
    """Reparte `total` a prorrata de `pesos`, con la suma exacta garantizada.

    `escala` es el cuanto de la columna de destino: `Decimal("0.01")` para el
    dinero y `Decimal("0.001")` para los kilos (ver `normalizacion.py`).

    El algoritmo es el evidente —cociente, redondeo, residuo— con el remate que
    lo vuelve exacto:

        parte_i = redondear(total × peso_i / Σpesos)
        residuo = total − Σparte_i
        parte_de_mayor_peso += residuo

    El residuo está acotado por `n × escala / 2` y en la práctica vale uno o dos
    céntimos. Aun así se recorre la lista de mayor a menor peso en vez de tocar
    solo la primera: con un total minúsculo —dos céntimos entre cuatro destinos,
    que es el caso que aparece en las pruebas y no en producción— el residuo es
    negativo y mayor que la parte que le tocaría absorberlo, y sumarlo a secas
    dejaría un presupuesto **negativo**, que la tabla rechaza por
    `ck_presupuesto_monto_no_negativo`. El bucle lo va absorbiendo por orden de
    tamaño y termina siempre con residuo cero: el invariante
    `Σpartes + residuo == total` se conserva en cada vuelta y el residuo solo
    puede quedarse negativo mientras haya partes positivas que reducir.
    """
    if not pesos:
        raise ValueError("No hay destinos sobre los que repartir.")
    if total < 0:
        raise ValueError(f"No se reparte una cifra negativa: {total}.")
    if any(peso < 0 for peso in pesos):
        raise ValueError("Los pesos del reparto no pueden ser negativos.")

    objetivo = total.quantize(escala, rounding=ROUND_HALF_UP)
    suma = sum(pesos, Decimal(0))
    if suma <= 0:
        raise ValueError(
            "Todos los pesos son cero: use `elegir_pesos` para bajar un escalón de la cascada."
        )

    partes = [(objetivo * peso / suma).quantize(escala, rounding=ROUND_HALF_UP) for peso in pesos]

    residuo = objetivo - sum(partes, Decimal(0))
    # De mayor a menor peso; el índice desempata para que el resultado no
    # dependa del orden en que el motor devolvió las filas.
    for indice in sorted(range(len(pesos)), key=lambda i: (-pesos[i], i)):
        if residuo == 0:
            break
        candidato = partes[indice] + residuo
        if candidato >= 0:
            partes[indice] = candidato
            residuo = Decimal(0)
        else:
            residuo = candidato
            partes[indice] = Decimal(0).quantize(escala)

    return partes


def indice_de_mayor_peso(pesos: Sequence[Decimal]) -> int:
    """El destino que se lleva el residuo. Empate: el primero de la lista."""
    if not pesos:
        raise ValueError("No hay destinos sobre los que repartir.")
    return min(range(len(pesos)), key=lambda i: (-pesos[i], i))
