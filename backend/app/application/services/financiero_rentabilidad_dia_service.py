"""Agregados diarios para Rentabilidad Día de Grupo Santacruz."""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass, replace
from datetime import date, timedelta
from decimal import Decimal

from app.core.config import obtener_settings
from app.core.errors import ErrorValidacion
from app.infrastructure.fuentes.agro_vendedores_clases import (
    CLASES_RENTABILIDAD,
    obtener_vendedores_clases,
)
from app.infrastructure.fuentes.agropecuaria import (
    COMPANIA_AGROPECUARIA,
    ConfiguracionAgro,
    FuenteVentaAgro,
    FuenteVentaAgropecuaria,
    LineaAgro,
)
from app.infrastructure.models.agro_vocabulario import es_impuesto
from app.schemas.financiero import (
    FilaComercialRentabilidadDia,
    FilaGrupoRentabilidadDia,
    FilaMatrizRentabilidadDia,
    FilaRentabilidadVendedorDia,
    FilaVendedorClaseRentabilidadDia,
    FilaVendedorRentabilidadDia,
    PuntoRentabilidadMes,
    RespuestaRentabilidadDia,
)


@dataclass(slots=True)
class _Acumulado:
    venta: Decimal = Decimal(0)
    costo: Decimal = Decimal(0)
    kilos: Decimal = Decimal(0)
    cantidad: Decimal = Decimal(0)
    lineas: int = 0
    costo_completo: bool = True

    def agregar(self, fila: LineaAgro) -> None:
        self.venta += fila.total_neto
        self.kilos += fila.kilos_total
        self.cantidad += fila.cantidad_inv
        self.lineas += fila.lineas_facturadas
        if fila.total_costo is None:
            self.costo_completo = False
        else:
            self.costo += fila.total_costo

    @property
    def costo_conocido(self) -> Decimal | None:
        return self.costo if self.costo_completo else None

    @property
    def rentabilidad(self) -> Decimal | None:
        if not self.costo_completo or self.venta == 0:
            return None
        return (self.venta - self.costo) / self.venta

    @property
    def costo_por_kilo(self) -> Decimal | None:
        if not self.costo_completo or self.kilos == 0:
            return None
        return self.costo / self.kilos


def _es_especie(etiqueta: str | None, nombre: str) -> bool:
    return nombre in (etiqueta or "").upper().replace("-", " ").split()


def _matriz(
    etiqueta: str,
    acumulado: _Acumulado,
    diario: dict[date, _Acumulado],
    fechas: list[date],
) -> FilaMatrizRentabilidadDia:
    return FilaMatrizRentabilidadDia(
        etiqueta=etiqueta,
        venta=acumulado.venta,
        valores=[diario[fecha].venta for fecha in fechas],
    )


def _matriz_vendedor(
    etiqueta: str,
    acumulado: _Acumulado,
    diario: dict[date, _Acumulado],
    fechas: list[date],
) -> FilaRentabilidadVendedorDia:
    return FilaRentabilidadVendedorDia(
        **_matriz(etiqueta, acumulado, diario, fechas).model_dump(),
        rentabilidad=acumulado.rentabilidad,
    )


def calcular_rentabilidad_dia(
    periodo: str,
    fuente: FuenteVentaAgro | None = None,
    mapa_vendedores: dict[str, str] | None = None,
) -> RespuestaRentabilidadDia:
    """Consulta cia 3 y agrega venta, costos y clases por día del mes."""
    try:
        anio, mes = int(periodo[:4]), int(periodo[4:])
        desde = date(anio, mes, 1)
    except (ValueError, TypeError) as exc:
        raise ErrorValidacion("El período debe tener formato AAAAMM válido.") from exc
    hasta = date(anio, mes, monthrange(anio, mes)[1])
    fechas = [desde + timedelta(days=dia) for dia in range((hasta - desde).days + 1)]

    configuracion = None
    if fuente is None or mapa_vendedores is None:
        configuracion = replace(
            ConfiguracionAgro.desde_settings(obtener_settings()),
            compania=COMPANIA_AGROPECUARIA,
        )
    fuente_creada: FuenteVentaAgropecuaria | None = None
    if fuente is None:
        assert configuracion is not None
        fuente_creada = FuenteVentaAgropecuaria(configuracion=configuracion)
        origen: FuenteVentaAgro = fuente_creada
    else:
        origen = fuente
    if mapa_vendedores is None:
        assert configuracion is not None
        clases = obtener_vendedores_clases(configuracion)
    else:
        clases = mapa_vendedores

    total = _Acumulado()
    diario = {fecha: _Acumulado() for fecha in fechas}
    especies: dict[str, _Acumulado] = {}
    especies_diarias: dict[str, dict[date, _Acumulado]] = {}
    comerciales: dict[tuple[str, str], _Acumulado] = {}
    comerciales_diarias: dict[tuple[str, str], dict[date, _Acumulado]] = {}
    productos: dict[tuple[str, str, str], _Acumulado] = {}
    productos_diarios: dict[tuple[str, str, str], dict[date, _Acumulado]] = {}
    clases_diarias = {
        clase: {fecha: _Acumulado() for fecha in fechas} for clase in CLASES_RENTABILIDAD
    }
    clases_totales = {clase: _Acumulado() for clase in CLASES_RENTABILIDAD}
    vendedores_totales: dict[tuple[str, str], _Acumulado] = {}
    vendedores_diarios: dict[tuple[str, str], dict[date, _Acumulado]] = {}
    nombres_vendedores: dict[tuple[str, str], str] = {}
    productos_por_vendedor: dict[tuple[str, str, str], _Acumulado] = {}
    productos_vendedor_diarios: dict[tuple[str, str, str], dict[date, _Acumulado]] = {}
    canal_cerdo = Decimal(0)
    canal_res = Decimal(0)

    try:
        for fila in origen.obtener_ventas(desde, hasta):
            if es_impuesto(fila.tipo_item):
                continue
            acumulado_dia = diario.get(fila.fecha)
            if acumulado_dia is None:
                continue
            total.agregar(fila)
            acumulado_dia.agregar(fila)

            if "BIENES" not in (fila.tipo_item or "").upper():
                continue
            especie = fila.especie or "SIN ESPECIE"
            especies.setdefault(especie, _Acumulado()).agregar(fila)
            especies_diarias.setdefault(especie, {fecha: _Acumulado() for fecha in fechas})[
                fila.fecha
            ].agregar(fila)
            clave_comercial = (especie, fila.tipo_comercial or "SIN TIPO COMERCIAL")
            comerciales.setdefault(clave_comercial, _Acumulado()).agregar(fila)
            comerciales_diarias.setdefault(
                clave_comercial, {fecha: _Acumulado() for fecha in fechas}
            )[fila.fecha].agregar(fila)
            etiqueta_producto = (
                f"{fila.item_ref} · {fila.item_desc}"
                if fila.item_ref and fila.item_desc
                else fila.item_ref or fila.item_desc or "SIN PRODUCTO"
            )
            clave_producto = (*clave_comercial, etiqueta_producto)
            productos.setdefault(clave_producto, _Acumulado()).agregar(fila)
            productos_diarios.setdefault(clave_producto, {fecha: _Acumulado() for fecha in fechas})[
                fila.fecha
            ].agregar(fila)

            tipo_comercial = (fila.tipo_comercial or "").upper()
            if "CANAL" in tipo_comercial:
                if _es_especie(especie, "CERDO"):
                    canal_cerdo += fila.cantidad_inv
                if _es_especie(especie, "RES"):
                    canal_res += fila.cantidad_inv

            clase = clases.get(fila.codigo_vendedor or "")
            if clase in clases_diarias:
                clases_diarias[clase][fila.fecha].agregar(fila)
                clases_totales[clase].agregar(fila)
                codigo_vendedor = fila.codigo_vendedor or "SIN CODIGO"
                nombre_vendedor = fila.nombre_vendedor or "SIN NOMBRE"
                clave_vendedor = (clase, codigo_vendedor)
                nombres_vendedores.setdefault(clave_vendedor, nombre_vendedor)
                vendedores_totales.setdefault(clave_vendedor, _Acumulado()).agregar(fila)
                vendedores_diarios.setdefault(
                    clave_vendedor, {fecha: _Acumulado() for fecha in fechas}
                )[fila.fecha].agregar(fila)
                clave_producto_vendedor = (*clave_vendedor, etiqueta_producto)
                productos_por_vendedor.setdefault(clave_producto_vendedor, _Acumulado()).agregar(
                    fila
                )
                productos_vendedor_diarios.setdefault(
                    clave_producto_vendedor, {fecha: _Acumulado() for fecha in fechas}
                )[fila.fecha].agregar(fila)
    finally:
        if fuente_creada is not None:
            fuente_creada.cerrar()

    grupos_especie = []
    for etiqueta, acumulado in sorted(especies.items(), key=lambda par: par[1].venta, reverse=True):
        detalle = []
        for (nombre_especie, tipo), valor in comerciales.items():
            if nombre_especie != etiqueta:
                continue
            clave_comercial = (nombre_especie, tipo)
            productos_comerciales = [
                _matriz(
                    nombre_producto,
                    acumulado_producto,
                    productos_diarios[(nombre_especie, tipo, nombre_producto)],
                    fechas,
                )
                for (
                    especie_producto,
                    tipo_producto,
                    nombre_producto,
                ), acumulado_producto in productos.items()
                if especie_producto == nombre_especie and tipo_producto == tipo
            ]
            productos_comerciales.sort(key=lambda fila: fila.venta, reverse=True)
            detalle.append(
                FilaComercialRentabilidadDia(
                    **_matriz(
                        tipo, valor, comerciales_diarias[clave_comercial], fechas
                    ).model_dump(),
                    productos=productos_comerciales,
                )
            )
        detalle.sort(key=lambda fila: fila.venta, reverse=True)
        serie_especie = _matriz(etiqueta, acumulado, especies_diarias[etiqueta], fechas)
        grupos_especie.append(
            FilaGrupoRentabilidadDia(
                **serie_especie.model_dump(),
                detalle=detalle,
            )
        )

    return RespuestaRentabilidadDia(
        periodo=periodo,
        cia=COMPANIA_AGROPECUARIA,
        fecha_inicio=desde,
        fecha_fin=hasta,
        venta=total.venta,
        rentabilidad=total.rentabilidad,
        lineas_facturadas=total.lineas,
        canal_cerdo=canal_cerdo,
        canal_res=canal_res,
        costo_kg_cerdo=next(
            (
                valor.costo_por_kilo
                for etiqueta, valor in especies.items()
                if _es_especie(etiqueta, "CERDO")
            ),
            None,
        ),
        costo_kg_res=next(
            (
                valor.costo_por_kilo
                for etiqueta, valor in especies.items()
                if _es_especie(etiqueta, "RES")
            ),
            None,
        ),
        diario=[
            PuntoRentabilidadMes(
                fecha=fecha,
                venta=diario[fecha].venta,
                rentabilidad=diario[fecha].rentabilidad,
            )
            for fecha in fechas
        ],
        especies_bienes=grupos_especie,
        vendedores_clases=[
            FilaVendedorClaseRentabilidadDia(
                **_matriz_vendedor(
                    clase, clases_totales[clase], clases_diarias[clase], fechas
                ).model_dump(),
                vendedores=[
                    FilaVendedorRentabilidadDia(
                        **_matriz_vendedor(
                            (
                                f"{codigo_vendedor} · "
                                f"{nombres_vendedores[(nombre_clase, codigo_vendedor)]}"
                                if nombres_vendedores[(nombre_clase, codigo_vendedor)]
                                != "SIN NOMBRE"
                                else codigo_vendedor
                            ),
                            acumulado_vendedor,
                            vendedores_diarios[(nombre_clase, codigo_vendedor)],
                            fechas,
                        ).model_dump(),
                        productos=[
                            _matriz_vendedor(
                                nombre_producto,
                                acumulado_producto,
                                productos_vendedor_diarios[
                                    (nombre_clase, codigo_vendedor, nombre_producto)
                                ],
                                fechas,
                            )
                            for (
                                clase_producto,
                                vendedor_producto,
                                nombre_producto,
                            ), acumulado_producto in productos_por_vendedor.items()
                            if clase_producto == nombre_clase
                            and vendedor_producto == codigo_vendedor
                        ],
                    )
                    for (nombre_clase, codigo_vendedor), acumulado_vendedor in sorted(
                        vendedores_totales.items(),
                        key=lambda elemento: elemento[1].venta,
                        reverse=True,
                    )
                    if nombre_clase == clase
                ],
            )
            for clase in CLASES_RENTABILIDAD
        ],
    )
