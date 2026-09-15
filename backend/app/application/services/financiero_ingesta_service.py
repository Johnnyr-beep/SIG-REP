"""Carga del libro mayor de SIESA (`Consolidado.json`, NDJSON) en
`movimientos_contables` (§ tablero financiero de Grupo Santacruz).

Carga **por reemplazo de período**: antes de insertar las filas nuevas de una
(cia, período), se borran las que ya existieran para esa combinación. Es lo
correcto para una carga manual que se repite cuando el negocio exporta un
archivo nuevo — reintentar la misma carga, o cargar un archivo corregido, no
debe duplicar filas ni obligar a truncar la tabla entera.

Streaming línea a línea: el archivo de origen pesa cientos de megabytes y
`json.loads` fila a fila —nunca `json.load` del archivo completo— es lo que
permite cargarlo sin agotar memoria.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.infrastructure.models.financiero import MovimientoContable

#: Filas por lote de `INSERT`. Bajo para no agotar memoria del lado del
#: cliente, alto para no pagar un viaje de red por fila en 1.27 millones de
#: registros.
TAMANO_LOTE = 5000

_CAMPOS_TEXTO_OBLIGATORIOS = ("CO", "AUXILIAR", "MAYOR_III")
_CAMPOS_NUMERICOS = ("SALDOS_INICIAL", "DEBITOS", "CREDITOS", "FINAL")


@dataclass
class RechazoCargaLibroMayor:
    fila: int
    motivo: str
    contenido: str


@dataclass
class ResumenCargaLibroMayor:
    origen: str
    filas_leidas: int = 0
    aceptadas: int = 0
    rechazadas: int = 0
    cias: set[int] = field(default_factory=set)
    periodos: set[int] = field(default_factory=set)
    rechazos: list[RechazoCargaLibroMayor] = field(default_factory=list)

    #: Cuántos rechazos detallados se conservan. El resto solo cuenta: guardar
    #: el millón de filas rechazadas de un archivo mal formado no ayuda a
    #: diagnosticar, y sí agota memoria.
    _LIMITE_RECHAZOS_DETALLADOS = 200

    def registrar_rechazo(self, fila: int, motivo: str, contenido: str) -> None:
        self.rechazadas += 1
        if len(self.rechazos) < self._LIMITE_RECHAZOS_DETALLADOS:
            self.rechazos.append(RechazoCargaLibroMayor(fila, motivo, contenido[:300]))


def _texto(valor: Any) -> str | None:
    if valor is None:
        return None
    texto = str(valor).strip()
    return texto or None


def _decimal(valor: Any) -> Decimal:
    """`Decimal` con dos cifras. Pasa por `str()` para no heredar el error
    binario de un `float` de `json.loads` (§ ver `app.domain.normalizacion`).
    """
    return Decimal(str(valor)).quantize(Decimal("0.01"))


def _fila_a_movimiento(dato: dict[str, Any], origen: str) -> MovimientoContable:
    for campo in _CAMPOS_TEXTO_OBLIGATORIOS:
        if not _texto(dato.get(campo)):
            raise ValueError(f"falta '{campo}'")
    for campo in _CAMPOS_NUMERICOS:
        if dato.get(campo) is None:
            raise ValueError(f"falta '{campo}'")

    cia = dato.get("CIA")
    periodo = dato.get("PERIODO")
    if not isinstance(cia, int):
        raise ValueError("'CIA' no es un entero")
    if not isinstance(periodo, int) or not (200001 <= periodo <= 209912):
        raise ValueError("'PERIODO' no tiene forma AAAAMM")

    try:
        saldo_inicial = _decimal(dato["SALDOS_INICIAL"])
        debitos = _decimal(dato["DEBITOS"])
        creditos = _decimal(dato["CREDITOS"])
        final = _decimal(dato["FINAL"])
    except (InvalidOperation, TypeError) as exc:
        raise ValueError(f"campo numérico inválido: {exc}") from None

    return MovimientoContable(
        cia=cia,
        co=_texto(dato.get("CO")) or "",
        periodo=periodo,
        auxiliar=_texto(dato.get("AUXILIAR")) or "",
        descripcion=_texto(dato.get("DESCRIPCION")),
        id_tercero=_texto(dato.get("ID_TERCERO")),
        razon_social=_texto(dato.get("RAZON_SOCIAL")),
        id_centro_costo=_texto(dato.get("ID_CENTRO_COSTO")),
        centro_costo=_texto(dato.get("CENTRO_COSTO")),
        mayor=_texto(dato.get("MAYOR")),
        mayor_iv=_texto(dato.get("MAYOR_IV")),
        mayor_iii=_texto(dato.get("MAYOR_III")) or "",
        saldo_inicial=saldo_inicial,
        debitos=debitos,
        creditos=creditos,
        final=final,
        origen=origen,
    )


def _leer_lineas(ruta: Path) -> Iterator[str]:
    with ruta.open(encoding="utf-8") as archivo:
        yield from archivo


def cargar_libro_mayor(sesion: Session, ruta: Path) -> ResumenCargaLibroMayor:
    """Carga un archivo NDJSON completo, reemplazando sus (cia, período).

    No hace `commit`: es responsabilidad de quien llama (`sesion_ambito` en el
    script de línea de comandos, la prueba en sus propias pruebas), igual que
    el resto de servicios del repositorio.
    """
    origen = ruta.name
    resumen = ResumenCargaLibroMayor(origen=origen)
    lote: list[MovimientoContable] = []
    combinaciones_vistas: set[tuple[int, int]] = set()

    for numero_fila, linea in enumerate(_leer_lineas(ruta), start=1):
        texto = linea.strip()
        if not texto:
            continue
        resumen.filas_leidas += 1
        try:
            dato = json.loads(texto)
            movimiento = _fila_a_movimiento(dato, origen)
        except (json.JSONDecodeError, ValueError) as exc:
            resumen.registrar_rechazo(numero_fila, str(exc), texto)
            continue

        combinacion = (movimiento.cia, movimiento.periodo)
        if combinacion not in combinaciones_vistas:
            combinaciones_vistas.add(combinacion)
            resumen.cias.add(movimiento.cia)
            resumen.periodos.add(movimiento.periodo)
            sesion.execute(
                delete(MovimientoContable).where(
                    MovimientoContable.cia == movimiento.cia,
                    MovimientoContable.periodo == movimiento.periodo,
                )
            )

        lote.append(movimiento)
        resumen.aceptadas += 1
        if len(lote) >= TAMANO_LOTE:
            sesion.add_all(lote)
            sesion.flush()
            lote.clear()

    if lote:
        sesion.add_all(lote)
        sesion.flush()

    return resumen
