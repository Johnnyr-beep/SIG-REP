"""Sincroniza `numero_documentos_diarios` desde la API de SIESA (§4.4).

Idempotente por rango: antes de insertar, se borran los conteos existentes de
los puntos de venta y fechas que la respuesta trae. Reintentar la misma
sincronización, o repetirla tras corregir algo del lado de la API, reemplaza
en vez de duplicar — el mismo criterio que la ingesta de venta (§5).

Deliberadamente **no** vive dentro de `ejecutar_ingesta`: es un dato
complementario y de solo lectura para el reporte, no parte de la venta
transaccional. Se sincroniza aparte, a mano o desde un job propio, sin arrastrar
al éxito o fracaso de la carga de venta.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.infrastructure.fuentes.facturas_siesa import FuenteFacturasSiesa
from app.infrastructure.models.documentos import NumeroDocumentosDiarios
from app.infrastructure.models.organizacion import PuntoVenta


@dataclass
class ResumenDocumentos:
    desde: date
    hasta: date
    puntos_reconocidos: int = 0
    puntos_desconocidos: set[str] = field(default_factory=set)
    filas_guardadas: int = 0


def sincronizar_documentos_diarios(
    sesion: Session, fuente: FuenteFacturasSiesa, desde: date, hasta: date
) -> ResumenDocumentos:
    """Descarga, resuelve el punto de venta por `codigo_co` y reemplaza el rango.

    Un `codigo_co` que no está en `puntos_venta` no aborta la sincronización:
    se cuenta en `puntos_desconocidos` para que quien la corra sepa que faltó
    sembrar o mapear ese punto, igual que un rechazo de la ingesta de venta.
    """
    conteos = fuente.contar_documentos(desde, hasta)
    resumen = ResumenDocumentos(desde=desde, hasta=hasta)

    codigos = {codigo for codigo, _ in conteos}
    puntos_por_codigo = {
        p.codigo_co: p.id
        for p in sesion.execute(
            select(PuntoVenta).where(PuntoVenta.codigo_co.in_(codigos))
        ).scalars()
    }
    resumen.puntos_desconocidos = codigos - puntos_por_codigo.keys()
    resumen.puntos_reconocidos = len(puntos_por_codigo)

    sesion.execute(
        delete(NumeroDocumentosDiarios).where(
            NumeroDocumentosDiarios.punto_venta_id.in_(puntos_por_codigo.values()),
            NumeroDocumentosDiarios.fecha >= desde,
            NumeroDocumentosDiarios.fecha <= hasta,
        )
    )

    filas = [
        NumeroDocumentosDiarios(
            punto_venta_id=puntos_por_codigo[codigo],
            fecha=fecha,
            cantidad=cantidad,
            origen="siesa",
        )
        for (codigo, fecha), cantidad in conteos.items()
        if codigo in puntos_por_codigo
    ]
    sesion.add_all(filas)
    sesion.flush()
    resumen.filas_guardadas = len(filas)
    return resumen
