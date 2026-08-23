"""Alertas y oportunidades explicables para Agropecuaria."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.application.services.periodos import buscar_periodo, parsear_periodo
from app.infrastructure.models.agro_dimensiones import AgroDimension
from app.infrastructure.models.agro_venta import AgroVentaLinea
from app.schemas.inteligencia import (
    AlertaComercial,
    OportunidadComercial,
    RecomendacionComercial,
    RespuestaInteligencia,
)

CERO = Decimal("0")
UMBRAL_DISMINUCION = Decimal("0.80")
LIMITE = 100


def _mes_anterior(codigo: str) -> str:
    anio, mes = parsear_periodo(codigo)
    return f"{anio - 1:04d}-12" if mes == 1 else f"{anio:04d}-{mes - 1:02d}"


class InteligenciaComercialService:
    """Compara meses cargados y devuelve señales accionables."""

    def __init__(self, sesion: Session) -> None:
        self._sesion = sesion

    def analizar(self, codigo_periodo: str) -> RespuestaInteligencia:
        anterior = _mes_anterior(codigo_periodo)
        actual = buscar_periodo(self._sesion, codigo_periodo)
        previo = buscar_periodo(self._sesion, anterior)
        if actual is None or previo is None:
            return RespuestaInteligencia(
                periodo=codigo_periodo,
                periodo_anterior=anterior,
                disponible=False,
                mensaje=(f"No hay datos cargados para comparar {codigo_periodo} con {anterior}."),
                alertas=[],
                productos_no_solicitados=[],
                oportunidades=[],
                recomendaciones=[
                    RecomendacionComercial(
                        prioridad="alta",
                        titulo="Cargar dos meses de venta",
                        detalle=(
                            "La comparación mensual se activa cuando existen ventas "
                            "del período actual y del anterior."
                        ),
                    )
                ],
            )

        catalogo = {
            fila.id: fila.nombre for fila in self._sesion.execute(select(AgroDimension)).scalars()
        }
        actual_data = self._agregados(actual.id)
        previo_data = self._agregados(previo.id)
        clientes_actual = self._totales(actual_data)
        clientes_previos = self._totales(previo_data)
        alertas: list[AlertaComercial] = []
        for cliente_id, venta_anterior in clientes_previos.items():
            venta_actual = clientes_actual.get(cliente_id, CERO)
            if venta_actual == 0:
                tipo, detalle = "suspendio", "No registra compras en el período actual."
            elif venta_actual < venta_anterior * UMBRAL_DISMINUCION:
                tipo, detalle = (
                    "disminuyo",
                    "La compra actual está por debajo del 80 % del período anterior.",
                )
            else:
                continue
            variacion = (venta_actual / venta_anterior) - 1 if venta_anterior else None
            alertas.append(
                AlertaComercial(
                    tipo=tipo,
                    cliente=catalogo.get(cliente_id, str(cliente_id)),
                    venta_anterior=venta_anterior,
                    venta_actual=venta_actual,
                    variacion=variacion,
                    detalle=detalle,
                )
            )
        alertas.sort(key=lambda f: f.venta_anterior, reverse=True)

        productos: list[AlertaComercial] = []
        for (cliente_id, producto_id), venta_anterior in previo_data.items():
            venta_actual = actual_data.get((cliente_id, producto_id), CERO)
            if venta_actual != 0:
                continue
            productos.append(
                AlertaComercial(
                    tipo="producto_no_solicitado",
                    cliente=catalogo.get(cliente_id, str(cliente_id)),
                    producto=catalogo.get(producto_id, str(producto_id)),
                    venta_anterior=venta_anterior,
                    venta_actual=venta_actual,
                    detalle="El cliente lo compró el mes anterior y no lo ha solicitado este mes.",
                )
            )
        productos.sort(key=lambda f: f.venta_anterior, reverse=True)

        demanda_productos: defaultdict[int, Decimal] = defaultdict(Decimal)
        for (_cliente_id, producto_id), venta in actual_data.items():
            demanda_productos[producto_id] += venta
        clientes_con_venta = set(clientes_actual)
        oportunidades: list[OportunidadComercial] = []
        for producto_id, venta_producto in sorted(
            demanda_productos.items(), key=lambda item: item[1], reverse=True
        )[:20]:
            for cliente_id in sorted(clientes_con_venta):
                if (cliente_id, producto_id) in actual_data:
                    continue
                oportunidades.append(
                    OportunidadComercial(
                        cliente=catalogo.get(cliente_id, str(cliente_id)),
                        producto=catalogo.get(producto_id, str(producto_id)),
                        venta_producto=venta_producto,
                        detalle=(
                            "Producto con demanda en otros clientes; sugerirlo "
                            "en la próxima gestión."
                        ),
                    )
                )
                if len(oportunidades) >= LIMITE:
                    break
            if len(oportunidades) >= LIMITE:
                break

        recomendaciones = [
            RecomendacionComercial(
                prioridad="alta",
                titulo="Contactar clientes suspendidos",
                detalle=(
                    f"Priorizar {sum(1 for a in alertas if a.tipo == 'suspendio')} "
                    "clientes que dejaron de comprar."
                ),
            ),
            RecomendacionComercial(
                prioridad="media",
                titulo="Recuperar productos no solicitados",
                detalle=(
                    f"Revisar {len(productos)} combinaciones cliente-producto en la próxima visita."
                ),
            ),
        ]
        return RespuestaInteligencia(
            periodo=codigo_periodo,
            periodo_anterior=anterior,
            disponible=True,
            mensaje=None,
            alertas=alertas[:LIMITE],
            productos_no_solicitados=productos[:LIMITE],
            oportunidades=oportunidades,
            recomendaciones=recomendaciones,
        )

    def _agregados(self, periodo_id: int) -> dict[tuple[int, int], Decimal]:
        consulta = (
            select(
                AgroVentaLinea.cliente_id,
                AgroVentaLinea.item_id,
                func.sum(AgroVentaLinea.total_neto),
            )
            .where(AgroVentaLinea.periodo_id == periodo_id, ~AgroVentaLinea.es_impuesto)
            .group_by(AgroVentaLinea.cliente_id, AgroVentaLinea.item_id)
        )
        return {
            (cliente, producto): Decimal(total or 0)
            for cliente, producto, total in self._sesion.execute(consulta)
        }

    @staticmethod
    def _totales(
        datos: dict[tuple[int, int], Decimal],
    ) -> dict[int, Decimal]:
        totales: defaultdict[int, Decimal] = defaultdict(Decimal)
        for (cliente, _producto), venta in datos.items():
            totales[cliente] += venta
        return dict(totales)
