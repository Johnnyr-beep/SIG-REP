"""Consulta de inventario por punto de venta, en vivo desde SIESA."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.core.deps import (
    PERMISO_CONSULTAR_INVENTARIO,
    SesionDep,
    alcance_puntos_venta,
    exigir_permiso_consulta,
)
from app.infrastructure.fuentes.siesa import ErrorFuenteSiesa, clave_descripcion
from app.infrastructure.models.organizacion import PuntoVenta
from app.infrastructure.models.usuario import Usuario
from app.infrastructure.precalentador_inventario import obtener_inventario_pdv
from app.schemas.inventario import FilaInventarioPdv, RespuestaInventarioPdv

router = APIRouter(prefix="/inventario", tags=["Inventario"])

_ALIAS_CANTIDADES = {
    "existencia": (
        "existencia",
        "existencias",
        "cantidadinv",
        "cantidadinventario",
        "cantexistencia",
    ),
    "disponible": ("disponible", "disponibles"),
    "comprometida": (
        "comprometida",
        "comprometido",
        "cantidadcomprometida",
        "cantidadcomprometido",
        "cantcomprometida",
    ),
    "pendiente_entrada": (
        "pendienteentrada",
        "pendientesentrada",
        "pendientesdeentrada",
        "cantidadpendienteentrada",
        "cantpendienteentrada",
        "cantpendientesentrada",
        "cantpendentrar",
        "cantpendienteentrar",
        "cantidadpendentrar",
    ),
    "pendiente_salida": (
        "pendientesalida",
        "pendientessalida",
        "pendientesdesalida",
        "cantidadpendientesalida",
        "cantpendientesalida",
        "cantpendsalir",
        "cantpendientesalir",
        "cantidadpendsalir",
    ),
}


@dataclass(slots=True)
class _AcumuladoProducto:
    compania: int | None
    punto_venta: str | None
    codigo_producto: str | None
    referencia: str | None
    producto: str | None
    unidad: str | None
    cantidades: dict[str, Decimal] = field(default_factory=dict)
    cantidades_con_dato: set[str] = field(default_factory=set)
    atributos: dict[str, str | None] = field(default_factory=dict)
    atributos_conflictivos: set[str] = field(default_factory=set)


def _clave_columna(valor: str) -> str:
    return "".join(caracter for caracter in clave_descripcion(valor) if caracter.isalnum())


def _buscar_columna(columnas: tuple[str, ...], *alias: str) -> str | None:
    buscadas = {_clave_columna(nombre) for nombre in alias}
    return next((columna for columna in columnas if _clave_columna(columna) in buscadas), None)


def _codigo_pdv(valor: str | None) -> str | None:
    if valor is None or not valor.strip():
        return None
    limpio = valor.strip()
    if limpio.upper().startswith("TPV"):
        digitos = "".join(caracter for caracter in limpio[3:] if caracter.isdigit())
        if len(digitos) >= 3:
            return digitos[:3]
    if limpio.isdecimal():
        if len(limpio) == 5:
            limpio = limpio[:3]
        return str(int(limpio)).zfill(3)
    return limpio.upper()


def _compania(valor: str | None) -> int | None:
    try:
        return int(valor.strip()) if valor else None
    except ValueError:
        return None


def _decimal_siesa(valor: str | None) -> Decimal | None:
    if valor is None or not valor.strip():
        return None
    limpio = valor.strip().replace(" ", "")
    if "," in limpio and "." in limpio:
        if limpio.rfind(",") > limpio.rfind("."):
            limpio = limpio.replace(".", "").replace(",", ".")
        else:
            limpio = limpio.replace(",", "")
    elif "," in limpio:
        limpio = limpio.replace(",", ".")
    try:
        return Decimal(limpio)
    except InvalidOperation:
        return None


def _es_columna_tpv(columna: str) -> bool:
    clave = _clave_columna(columna).lower()
    return (
        clave.startswith("tpv")
        or clave.startswith("terminal")
        or clave
        in {
            "tpv",
            "idtpv",
            "codtpv",
            "codigotpv",
            "puntotpv",
            "terminal",
            "idterminal",
            "codterminal",
            "codigoterminal",
        }
    )


def _es_columna_ubicacion(columna: str) -> bool:
    clave = _clave_columna(columna).lower()
    return clave.startswith(("pdv", "puntoventa", "bodega", "almacen")) or clave.endswith(
        "rowidbodega"
    )


@router.get(
    "/pdv",
    response_model=RespuestaInventarioPdv,
    summary="Inventario actual por punto de venta",
)
def inventario_pdv(
    usuario: Annotated[Usuario, Depends(exigir_permiso_consulta(PERMISO_CONSULTAR_INVENTARIO))],
    sesion: SesionDep,
) -> RespuestaInventarioPdv:
    inventario = obtener_inventario_pdv()

    puntos = list(sesion.scalars(select(PuntoVenta)).all())
    por_codigo = {punto.codigo_co: punto for punto in puntos}
    por_descripcion = {
        clave_descripcion(punto.descripcion_siesa): punto
        for punto in puntos
        if punto.descripcion_siesa
    }
    por_nombre = {clave_descripcion(punto.nombre): punto for punto in puntos}

    columna_compania = _buscar_columna(
        inventario.columnas, "cia", "id_cia", "compania", "id_compania"
    )
    columna_codigo = _buscar_columna(
        inventario.columnas,
        "id_co",
        "codigo_co",
        "co_codigo",
        "co",
        "codigo_pdv",
        "cod_pdv",
        "id_pdv",
        "pdvcodigo",
        "bodega",
        "codigo_bodega",
    )
    columna_descripcion = _buscar_columna(
        inventario.columnas,
        "desc_co",
        "descripcion_co",
        "co_descripcion",
        "desc_pdv",
        "descripcion_pdv",
        "nombre_pdv",
        "pdvdescripcion",
        "descripcion_bod",
    )
    columna_punto_venta = _buscar_columna(
        inventario.columnas,
        "punto_de_venta",
        "punto_venta",
        "nombre_punto_venta",
    )
    columna_codigo_producto = _buscar_columna(
        inventario.columnas,
        "itemcodigo",
        "item",
        "item_ext",
        "itemext",
        "codigo_item",
        "cod_item",
        "item_id",
        "id_item",
    )
    columna_referencia = _buscar_columna(
        inventario.columnas,
        "itemreferencia",
        "referencia",
        "referencia_item",
        "codigo_producto",
    )
    columna_descripcion_producto = _buscar_columna(
        inventario.columnas,
        "itemdescripcion",
        "f120_descripcion",
        "f120descripcion",
        "descitem",
        "descripcion_item",
        "descripcion_producto",
        "nombre_producto",
        "producto",
    )
    columna_unidad = _buscar_columna(
        inventario.columnas,
        "um",
        "unidad",
        "unidad_medida",
        "unidad_inventario",
        "unidadinv",
    )
    columnas_cantidad = {
        nombre: _buscar_columna(inventario.columnas, *alias)
        for nombre, alias in _ALIAS_CANTIDADES.items()
    }
    if columnas_cantidad["existencia"] is None and columnas_cantidad["disponible"] is None:
        raise ErrorFuenteSiesa(
            "SIESA no incluyó una columna de existencia o disponible reconocible; "
            "el inventario por punto de venta no se puede resumir."
        )
    columnas_metadata = {
        columna
        for columna in (
            columna_compania,
            columna_codigo,
            columna_descripcion,
            columna_punto_venta,
            columna_codigo_producto,
            columna_referencia,
            columna_descripcion_producto,
            columna_unidad,
            *columnas_cantidad.values(),
        )
        if columna
    }
    columnas_adicionales = [
        columna
        for columna in inventario.columnas
        if columna not in columnas_metadata
        and not _es_columna_tpv(columna)
        and not _es_columna_ubicacion(columna)
    ]

    alcance = alcance_puntos_venta(usuario)
    puntos_permitidos = set(alcance) if alcance is not None else None
    if (
        puntos_permitidos is not None
        and columna_codigo is None
        and columna_descripcion is None
        and columna_punto_venta is None
    ):
        raise ErrorFuenteSiesa(
            "SIESA no incluyó un identificador de punto de venta; no se puede aplicar "
            "el alcance de esta cuenta."
        )

    if columna_codigo is None and columna_descripcion is None and columna_punto_venta is None:
        raise ErrorFuenteSiesa(
            "SIESA no incluyó un nombre o identificador de punto de venta para agrupar "
            "el inventario."
        )

    acumulados: dict[tuple[int | None, str, str], _AcumuladoProducto] = {}
    for datos in inventario.filas:
        codigo = _codigo_pdv(datos.get(columna_codigo)) if columna_codigo else None
        punto = por_codigo.get(codigo) if codigo else None
        descripcion = datos.get(columna_descripcion) if columna_descripcion else None
        punto_crudo = datos.get(columna_punto_venta) if columna_punto_venta else None
        if punto is None and punto_crudo:
            punto = por_nombre.get(clave_descripcion(punto_crudo))
        if punto is None and columna_descripcion and descripcion:
            punto = por_descripcion.get(clave_descripcion(descripcion))
        if puntos_permitidos is not None and (punto is None or punto.id not in puntos_permitidos):
            continue

        compania = _compania(datos.get(columna_compania)) if columna_compania else None
        codigo_resuelto = punto.codigo_co if punto else codigo
        nombre_pdv = (
            punto_crudo.strip()
            if punto_crudo and punto_crudo.strip()
            else punto.nombre
            if punto
            else descripcion.strip()
            if descripcion
            else codigo
        )
        clave_pdv = codigo_resuelto or clave_descripcion(nombre_pdv or "")
        if not clave_pdv:
            continue
        codigo_producto_crudo = (
            datos.get(columna_codigo_producto) if columna_codigo_producto else None
        )
        codigo_producto = (
            codigo_producto_crudo.strip()
            if codigo_producto_crudo and codigo_producto_crudo.strip()
            else None
        )
        referencia_cruda = datos.get(columna_referencia) if columna_referencia else None
        referencia = (
            referencia_cruda.strip() if referencia_cruda and referencia_cruda.strip() else None
        )
        producto_crudo = (
            datos.get(columna_descripcion_producto) if columna_descripcion_producto else None
        )
        producto = producto_crudo.strip() if producto_crudo and producto_crudo.strip() else None
        unidad_cruda = datos.get(columna_unidad) if columna_unidad else None
        unidad = unidad_cruda.strip() if unidad_cruda and unidad_cruda.strip() else None
        identidad = referencia or codigo_producto or producto
        if identidad is None:
            raise ErrorFuenteSiesa(
                "SIESA devolvió una fila de inventario sin código, referencia ni descripción "
                "de producto; no se puede consolidar sin duplicados."
            )
        clave = (compania, clave_pdv, clave_descripcion(identidad))
        acumulado = acumulados.setdefault(
            clave,
            _AcumuladoProducto(
                compania=compania,
                punto_venta=nombre_pdv,
                codigo_producto=codigo_producto,
                referencia=referencia,
                producto=producto,
                unidad=unidad,
            ),
        )
        for nombre, columna in columnas_cantidad.items():
            cantidad = _decimal_siesa(datos.get(columna)) if columna else None
            if cantidad is None:
                continue
            acumulado.cantidades[nombre] = acumulado.cantidades.get(nombre, Decimal(0)) + cantidad
            acumulado.cantidades_con_dato.add(nombre)
        for columna in columnas_adicionales:
            atributo = datos.get(columna)
            if columna not in acumulado.atributos:
                acumulado.atributos[columna] = atributo
            elif acumulado.atributos[columna] != atributo:
                acumulado.atributos[columna] = None
                acumulado.atributos_conflictivos.add(columna)

    columnas_resumen = [nombre for nombre, columna in columnas_cantidad.items() if columna]
    salida = [
        FilaInventarioPdv(
            compania=acumulado.compania,
            punto_venta=acumulado.punto_venta,
            codigo_producto=acumulado.codigo_producto,
            referencia=acumulado.referencia,
            producto=acumulado.producto,
            unidad=acumulado.unidad,
            **{
                nombre: acumulado.cantidades.get(nombre)
                if nombre in acumulado.cantidades_con_dato
                else None
                for nombre in _ALIAS_CANTIDADES
            },
            datos={
                columna: None
                if columna in acumulado.atributos_conflictivos
                else acumulado.atributos.get(columna)
                for columna in columnas_adicionales
            },
        )
        for acumulado in sorted(
            acumulados.values(),
            key=lambda fila: (
                fila.compania or 0,
                fila.punto_venta or "",
                fila.referencia or fila.codigo_producto or fila.producto or "",
            ),
        )
    ]

    columnas_producto = [
        nombre
        for nombre, columna in (
            ("punto_venta", columna_punto_venta),
            ("codigo_producto", columna_codigo_producto),
            ("referencia", columna_referencia),
            ("producto", columna_descripcion_producto),
            ("unidad", columna_unidad),
        )
        if columna is not None
    ]
    return RespuestaInventarioPdv(
        columnas=columnas_producto + columnas_resumen + columnas_adicionales,
        filas=salida,
        total=len(salida),
    )
