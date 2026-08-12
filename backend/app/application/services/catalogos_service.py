"""Catálogos: grupos, puntos de venta, categorías, zonas y mapeo de categorías."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import ErrorNoEncontrado
from app.infrastructure.models.catalogo import Categoria, MapeoCategoria
from app.infrastructure.models.organizacion import Grupo, PuntoVenta, Zona
from app.schemas.catalogos import (
    CategoriaSalida,
    GrupoSalida,
    MapeoCategoriaSalida,
    PuntoVentaSalida,
    ZonaSalida,
)


class CatalogosService:
    """Lectura de los catálogos y mantenimiento del mapeo de categorías."""

    def __init__(self, sesion: Session) -> None:
        self._sesion = sesion

    def listar_grupos(self) -> list[GrupoSalida]:
        grupos = self._sesion.execute(
            select(Grupo).where(Grupo.activo.is_(True)).order_by(Grupo.orden, Grupo.codigo)
        ).scalars()
        return [GrupoSalida(id=g.id, codigo=g.codigo, nombre=g.nombre) for g in grupos]

    def listar_puntos_venta(self, *, incluir_inactivos: bool = False) -> list[PuntoVentaSalida]:
        consulta = select(PuntoVenta).order_by(PuntoVenta.codigo_co)
        if not incluir_inactivos:
            consulta = consulta.where(PuntoVenta.activo.is_(True))
        return [
            PuntoVentaSalida(
                id=p.id,
                codigo_co=p.codigo_co,
                nombre=p.nombre,
                grupo=p.grupo.nombre if p.grupo else None,
                zona=p.zona.nombre if p.zona else None,
                activo=p.activo,
                presupuestado=p.presupuestado,
            )
            for p in self._sesion.execute(consulta).scalars()
        ]

    def listar_categorias(self) -> list[CategoriaSalida]:
        categorias = self._sesion.execute(
            select(Categoria).where(Categoria.activa.is_(True)).order_by(Categoria.orden)
        ).scalars()
        return [
            CategoriaSalida(id=c.id, codigo=c.codigo, nombre=c.nombre, orden=c.orden)
            for c in categorias
        ]

    def listar_zonas(self) -> list[ZonaSalida]:
        zonas = self._sesion.execute(
            select(Zona)
            .options(selectinload(Zona.puntos_venta))
            .where(Zona.activa.is_(True))
            .order_by(Zona.nombre)
        ).scalars()
        return [
            ZonaSalida(
                id=z.id,
                nombre=z.nombre,
                puntos_venta=[p.codigo_co for p in z.puntos_venta],
            )
            for z in zonas
        ]

    def listar_mapeo_categorias(self) -> list[MapeoCategoriaSalida]:
        mapeos = self._sesion.execute(
            select(MapeoCategoria).order_by(MapeoCategoria.texto_siesa)
        ).scalars()
        return [
            MapeoCategoriaSalida(texto_siesa=m.texto_siesa, categoria=m.categoria.nombre)
            for m in mapeos
        ]

    def guardar_mapeo(self, texto_siesa: str, nombre_categoria: str) -> MapeoCategoriaSalida:
        """Crea o reclasifica un mapeo.

        El texto se compara exacto y sin normalizar: las dos variantes de
        `0006 - QUESO(S) Y LACTEOS` son dos entradas distintas porque así llegan
        de SIESA, y unificarlas aquí escondería un problema de origen que el
        negocio necesita ver (§3.1).
        """
        categoria = self._sesion.execute(
            select(Categoria).where(Categoria.nombre == nombre_categoria)
        ).scalar_one_or_none()
        if categoria is None:
            raise ErrorNoEncontrado(f"No existe la categoría {nombre_categoria!r}.")

        mapeo = self._sesion.execute(
            select(MapeoCategoria).where(MapeoCategoria.texto_siesa == texto_siesa)
        ).scalar_one_or_none()

        if mapeo is None:
            mapeo = MapeoCategoria(texto_siesa=texto_siesa, categoria_id=categoria.id)
            self._sesion.add(mapeo)
        else:
            mapeo.categoria_id = categoria.id
        self._sesion.flush()

        return MapeoCategoriaSalida(texto_siesa=texto_siesa, categoria=categoria.nombre)

    # ── Resolución de claves de negocio ───────────────────────────────────────

    def punto_venta_por_codigo(self, codigo_co: str) -> PuntoVenta:
        punto = self._sesion.execute(
            select(PuntoVenta).where(PuntoVenta.codigo_co == codigo_co.strip())
        ).scalar_one_or_none()
        if punto is None:
            raise ErrorNoEncontrado(f"No existe el punto de venta {codigo_co!r}.")
        return punto

    def categoria_por_nombre(self, nombre: str) -> Categoria:
        categoria = self._sesion.execute(
            select(Categoria).where(Categoria.nombre == nombre.strip().upper())
        ).scalar_one_or_none()
        if categoria is None:
            raise ErrorNoEncontrado(f"No existe la categoría {nombre!r}.")
        return categoria
