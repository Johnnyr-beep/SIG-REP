"""Presupuesto: parametrización, versionado, carga masiva y cierre (§3.3, §7).

Dos reglas mandan aquí y las dos están hechas cumplir en el servicio, no en la
capa HTTP, para que sigan valiendo cuando el presupuesto se cargue desde un
script o desde un job:

1. Un período cerrado no admite cambios de presupuesto.
2. Todo cambio queda con autor, fecha y motivo.

Y una tercera, que llegó después de una auditoría: el **alcance** viaja hasta
aquí. La cifra de presupuesto de un punto de venta es información sensible
entre responsables (§8.4), así que tanto la consulta como la escritura reciben
la lista de puntos permitidos —`None` = todos— y la aplican en la consulta SQL,
no filtrando la respuesta después.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.services.periodos import obtener_o_crear_periodo, obtener_periodo
from app.core.errors import (
    ErrorAutorizacion,
    ErrorNoEncontrado,
    ErrorPeriodoCerrado,
    ErrorValidacion,
)
from app.core.logging import obtener_logger
from app.domain.normalizacion import clave_columna, normalizar_texto
from app.infrastructure.models.catalogo import Categoria
from app.infrastructure.models.mixins import ahora_utc
from app.infrastructure.models.organizacion import PuntoVenta
from app.infrastructure.models.periodo import Periodo
from app.infrastructure.models.presupuesto import Presupuesto, PresupuestoHistorial
from app.infrastructure.models.usuario import Usuario
from app.schemas.presupuesto import (
    ErrorFila,
    HistorialSalida,
    PeriodoSalida,
    PresupuestoSalida,
    ResultadoCargaMasiva,
)

logger = obtener_logger(__name__)

#: Hoja del libro vigente de la que sale el presupuesto por PDV y categoría
#: (§3.1 y §3.3). Se compara con el nombre saneado: en este libro las hojas
#: llegan con espacios de más («CLIENTES ») más veces de las que uno esperaría.
HOJA_CUMPLIMIENTO = "CUMPLIMIENTO PPTO"

#: Encabezados admitidos en la carga masiva. Se aceptan varias grafías porque
#: el archivo lo arma el negocio a mano y exigirle una plantilla exacta es
#: garantizar que la primera carga falle.
_ALIAS_COLUMNAS: dict[str, str] = {
    "punto_venta": "punto_venta",
    "punto de venta": "punto_venta",
    "pdv": "punto_venta",
    "c.o.": "punto_venta",
    "co": "punto_venta",
    "codigo_co": "punto_venta",
    "categoria": "categoria",
    "categoría": "categoria",
    "nueva categoria": "categoria",
    "monto": "monto",
    "ppto": "monto",
    "presupuesto": "monto",
    "kilos": "kilos",
    "ppto en kilo": "kilos",
    "ppto kilos": "kilos",
}


@dataclass(frozen=True, slots=True)
class FilaCarga:
    """Una fila ya normalizada del archivo de carga masiva."""

    numero: int
    codigo_punto_venta: str
    nombre_categoria: str
    monto: Decimal
    kilos: Decimal


class PresupuestoService:
    """Casos de uso del presupuesto."""

    def __init__(self, sesion: Session) -> None:
        self._sesion = sesion

    # ── Consulta ──────────────────────────────────────────────────────────────

    def listar(
        self,
        codigo_periodo: str,
        codigo_punto_venta: str | None = None,
        alcance: list[int] | None = None,
    ) -> list[PresupuestoSalida]:
        """Presupuesto del período dentro del alcance del usuario.

        `alcance=None` significa «todos los puntos». Una lista vacía significa
        «ninguno» y devuelve vacío: un JEFE_PDV al que nadie le configuró sus
        puntos no ve el presupuesto de la compañía por omisión.
        """
        periodo = obtener_periodo(self._sesion, codigo_periodo)
        consulta = (
            select(Presupuesto)
            .join(PuntoVenta, Presupuesto.punto_venta_id == PuntoVenta.id)
            .join(Categoria, Presupuesto.categoria_id == Categoria.id)
            .where(Presupuesto.periodo_id == periodo.id)
            .order_by(PuntoVenta.codigo_co, Categoria.orden)
        )
        if codigo_punto_venta:
            consulta = consulta.where(PuntoVenta.codigo_co == codigo_punto_venta.strip())
        if alcance is not None:
            # `or [-1]` mantiene la consulta válida con alcance vacío y devuelve
            # cero filas, igual que en `reportes_service`.
            consulta = consulta.where(PuntoVenta.id.in_(alcance or [-1]))

        autores = self._autores()
        return [
            PresupuestoSalida(
                punto_venta=p.punto_venta.codigo_co,
                categoria=p.categoria.nombre,
                monto=p.monto,
                kilos=p.kilos,
                actualizado_en=p.actualizado_en,
                actualizado_por=autores.get(p.actualizado_por_id),
            )
            for p in self._sesion.execute(consulta).scalars()
        ]

    def historial(
        self,
        codigo_periodo: str | None = None,
        codigo_punto_venta: str | None = None,
        alcance: list[int] | None = None,
    ) -> list[HistorialSalida]:
        """Rastro de cambios dentro del alcance del usuario.

        El historial lleva los mismos importes que el presupuesto —de hecho
        lleva el anterior *y* el nuevo—, así que se filtra exactamente igual.
        """
        consulta = select(PresupuestoHistorial).order_by(PresupuestoHistorial.cuando.desc())
        if codigo_periodo:
            periodo = obtener_periodo(self._sesion, codigo_periodo)
            consulta = consulta.where(PresupuestoHistorial.periodo_id == periodo.id)
        if codigo_punto_venta:
            punto = self._punto_por_codigo(codigo_punto_venta)
            consulta = consulta.where(PresupuestoHistorial.punto_venta_id == punto.id)
        if alcance is not None:
            consulta = consulta.where(PresupuestoHistorial.punto_venta_id.in_(alcance or [-1]))

        autores = self._autores()
        return [
            HistorialSalida(
                cuando=h.cuando,
                quien=autores.get(h.usuario_id),
                campo=h.campo,
                valor_anterior=h.valor_anterior,
                valor_nuevo=h.valor_nuevo,
                motivo=h.motivo,
            )
            for h in self._sesion.execute(consulta).scalars()
        ]

    # ── Parametrización ───────────────────────────────────────────────────────

    def guardar(
        self,
        *,
        codigo_periodo: str,
        punto_venta_id: int,
        categoria_id: int,
        monto: Decimal,
        kilos: Decimal,
        motivo: str,
        usuario: Usuario | None = None,
        alcance: list[int] | None = None,
    ) -> PresupuestoSalida:
        """Fija el presupuesto de una celda y deja el rastro del cambio.

        Solo se historian los campos que **cambiaron de valor**: guardar sin
        modificar nada no ensucia el historial, que es lo que hace que el
        historial siga siendo legible al cabo de un año.

        `alcance` es la lista de puntos que quien escribe tiene asignados
        (`None` = todos). Se comprueba aquí y no solo en el router porque la
        carga masiva entra por este mismo método fila a fila.
        """
        periodo = obtener_o_crear_periodo(self._sesion, codigo_periodo)
        self._exigir_periodo_abierto(periodo)

        punto = self._sesion.get(PuntoVenta, punto_venta_id)
        if punto is None:
            raise ErrorNoEncontrado(f"No existe el punto de venta {punto_venta_id}.")
        self._exigir_alcance(punto, alcance)
        categoria = self._sesion.get(Categoria, categoria_id)
        if categoria is None:
            raise ErrorNoEncontrado(f"No existe la categoría {categoria_id}.")

        if not punto.presupuestado:
            raise ErrorValidacion(
                f"El punto de venta {punto.codigo_co} {punto.nombre} no se presupuesta. "
                "Su venta se reporta aparte."
            )

        fila = self._sesion.execute(
            select(Presupuesto).where(
                Presupuesto.periodo_id == periodo.id,
                Presupuesto.punto_venta_id == punto_venta_id,
                Presupuesto.categoria_id == categoria_id,
            )
        ).scalar_one_or_none()

        anterior_monto = fila.monto if fila is not None else None
        anterior_kilos = fila.kilos if fila is not None else None

        if fila is None:
            fila = Presupuesto(
                periodo_id=periodo.id,
                punto_venta_id=punto_venta_id,
                categoria_id=categoria_id,
                monto=monto,
                kilos=kilos,
            )
            self._sesion.add(fila)
        else:
            fila.monto = monto
            fila.kilos = kilos

        fila.actualizado_por_id = usuario.id if usuario else None
        self._sesion.flush()

        self._historiar(fila, "monto", anterior_monto, monto, motivo, usuario)
        self._historiar(fila, "kilos", anterior_kilos, kilos, motivo, usuario)
        self._sesion.flush()

        logger.info(
            "presupuesto_guardado",
            periodo=periodo.codigo,
            punto_venta=punto.codigo_co,
            categoria=categoria.nombre,
        )
        return PresupuestoSalida(
            punto_venta=punto.codigo_co,
            categoria=categoria.nombre,
            monto=fila.monto,
            kilos=fila.kilos,
            actualizado_en=fila.actualizado_en,
            actualizado_por=usuario.usuario if usuario else None,
        )

    # ── Carga masiva ──────────────────────────────────────────────────────────

    def cargar_masivo(
        self,
        contenido: bytes,
        nombre_archivo: str,
        *,
        codigo_periodo: str,
        motivo: str,
        usuario: Usuario | None = None,
        alcance: list[int] | None = None,
    ) -> ResultadoCargaMasiva:
        """Carga un `.xlsx` o `.csv` con el presupuesto del período.

        Hoy el presupuesto se arma en Excel, así que la carga masiva no es una
        comodidad: es la forma en que este dato va a entrar al sistema.

        Una fila mala **no aborta la carga**. Se acepta lo que se pueda y se
        devuelve el detalle de lo rechazado con su número de fila; abortar
        entero por un typo en la fila 90 obligaría a repetir 89 filas buenas.

        El archivo lo trae el usuario, así que sus filas no son más de fiar que
        cualquier otra entrada: una fila de un punto fuera de su alcance se
        rechaza **con su motivo**, como cualquier otro error de fila. Rechazarla
        en silencio dejaría a quien carga creyendo que ese presupuesto quedó
        puesto.
        """
        periodo = obtener_o_crear_periodo(self._sesion, codigo_periodo)
        self._exigir_periodo_abierto(periodo)

        filas, errores = self._leer_archivo(contenido, nombre_archivo)

        aceptadas = 0
        for fila in filas:
            try:
                punto = self._punto_por_codigo(fila.codigo_punto_venta)
                categoria = self._categoria_por_nombre(fila.nombre_categoria)
                self.guardar(
                    codigo_periodo=codigo_periodo,
                    punto_venta_id=punto.id,
                    categoria_id=categoria.id,
                    monto=fila.monto,
                    kilos=fila.kilos,
                    motivo=motivo,
                    usuario=usuario,
                    alcance=alcance,
                )
            except (ErrorAutorizacion, ErrorNoEncontrado, ErrorValidacion) as exc:
                errores.append(ErrorFila(fila=fila.numero, motivo=exc.mensaje))
            else:
                aceptadas += 1

        logger.info(
            "carga_masiva_presupuesto",
            periodo=codigo_periodo,
            aceptadas=aceptadas,
            rechazadas=len(errores),
        )
        return ResultadoCargaMasiva(aceptadas=aceptadas, rechazadas=len(errores), errores=errores)

    def _leer_archivo(
        self, contenido: bytes, nombre_archivo: str
    ) -> tuple[list[FilaCarga], list[ErrorFila]]:
        nombre = nombre_archivo.lower()
        if nombre.endswith(".csv"):
            crudas = self._filas_csv(contenido)
        elif nombre.endswith((".xlsx", ".xlsm")):
            crudas = self._filas_excel(contenido)
        else:
            raise ErrorValidacion("Formato no admitido. Use .xlsx o .csv.")

        filas: list[FilaCarga] = []
        errores: list[ErrorFila] = []
        for numero, cruda in crudas:
            try:
                filas.append(self._normalizar_fila(numero, cruda))
            except ErrorValidacion as exc:
                errores.append(ErrorFila(fila=numero, motivo=exc.mensaje))
        return filas, errores

    @staticmethod
    def _filas_csv(contenido: bytes) -> list[tuple[int, dict[str, object]]]:
        texto = contenido.decode("utf-8-sig", errors="replace")
        lector = csv.DictReader(io.StringIO(texto))
        # `numero` cuenta desde 2 porque la 1 es el encabezado: así el número
        # que se le devuelve al usuario coincide con el que ve en su editor.
        return [
            (numero, {k: v for k, v in fila.items() if k is not None})
            for numero, fila in enumerate(lector, start=2)
        ]

    def _filas_excel(self, contenido: bytes) -> list[tuple[int, dict[str, object]]]:
        """Filas crudas de un `.xlsx`, por el camino que corresponda.

        Hay dos formatos y los dos son legítimos: la plantilla plana —una fila
        por celda de presupuesto, con encabezado— y **la hoja
        `CUMPLIMIENTO PPTO` del libro que el negocio ya tiene**, que es de donde
        va a salir la primera carga real. Se detecta la segunda y se lee con su
        propio parser; pedirle al usuario que reordene su Excel a mano antes de
        cargarlo es la forma más segura de que la carga masiva no se use nunca.
        """
        from openpyxl import load_workbook

        libro = load_workbook(io.BytesIO(contenido), read_only=True, data_only=True)
        try:
            hoja_presupuesto = next(
                (
                    libro[nombre]
                    for nombre in libro.sheetnames
                    if str(nombre).strip().upper() == HOJA_CUMPLIMIENTO
                ),
                None,
            )
            if hoja_presupuesto is not None:
                return self._filas_hoja_cumplimiento(hoja_presupuesto)

            hoja = libro.active
            if hoja is None:  # pragma: no cover - un libro siempre trae una hoja
                raise ErrorValidacion("El archivo no tiene ninguna hoja legible.")

            iterador = hoja.iter_rows(values_only=True)
            try:
                encabezados = [str(c).strip() if c is not None else "" for c in next(iterador)]
            except StopIteration as exc:
                raise ErrorValidacion("El archivo está vacío.") from exc

            filas: list[tuple[int, dict[str, object]]] = []
            for numero, valores in enumerate(iterador, start=2):
                if all(v is None for v in valores):
                    continue
                filas.append((numero, dict(zip(encabezados, valores, strict=False))))
            return filas
        finally:
            libro.close()

    def _filas_hoja_cumplimiento(self, hoja: Any) -> list[tuple[int, dict[str, object]]]:
        """Lee la hoja `CUMPLIMIENTO PPTO` del libro vigente (§3.1, §3.3).

        La hoja no empieza por el encabezado: arriba lleva el bloque de días
        hábiles por zona, y la tabla arranca en la fila cuyo primer título es
        `CODIGO`. De ahí para abajo vienen tres clases de fila mezcladas:

            001  GRUPO 1      ← total del grupo
            402  MALAMBO      ← total del punto de venta
            402  RES          ← presupuesto de (punto de venta, categoría)  ✔
            402  CERDO        ← ídem                                        ✔

        **Solo la tercera clase se carga.** Las otras dos son sumas y el
        presupuesto del PDV y del grupo se calculan, no se capturan por
        duplicado (§3.3): cargarlas multiplicaría por dos el presupuesto de la
        compañía. La regla para distinguirlas es doble —la etiqueta es una
        categoría conocida, o al menos no es la primera fila de su bloque de
        código—, y así una categoría nueva que el negocio añada mañana no se
        pierde en silencio: llega hasta el validador y sale como error de fila
        con su motivo.
        """
        categorias = {
            nombre.upper() for nombre in self._sesion.execute(select(Categoria.nombre)).scalars()
        }

        columnas: dict[str, int] = {}
        filas: list[tuple[int, dict[str, object]]] = []
        codigo_bloque: str | None = None

        for numero, valores in enumerate(hoja.iter_rows(values_only=True), start=1):
            if not valores:
                continue
            if not columnas:
                if _clave(valores[0]) == "codigo":
                    columnas = {}
                    for indice, titulo in enumerate(valores):
                        clave = _clave(titulo)
                        # Los encabezados `%` se repiten cuatro veces en la hoja;
                        # manda la primera aparición de cada nombre.
                        if clave and clave not in columnas:
                            columnas[clave] = indice
                    for obligatoria in ("codigo", "pdv", "ppto"):
                        if obligatoria not in columnas:
                            raise ErrorValidacion(
                                f"La hoja {HOJA_CUMPLIMIENTO} no trae la columna "
                                f"«{obligatoria.upper()}»."
                            )
                continue

            codigo = _celda(valores, columnas, "codigo")
            etiqueta = _texto_celda(_celda(valores, columnas, "pdv"))
            if codigo is None or etiqueta is None:
                continue

            codigo_normalizado = _texto_celda(codigo) or ""
            es_primera_del_bloque = codigo_normalizado != codigo_bloque
            codigo_bloque = codigo_normalizado
            if es_primera_del_bloque and etiqueta.upper() not in categorias:
                continue  # total del grupo o del punto de venta

            filas.append(
                (
                    numero,
                    {
                        "punto_venta": codigo,
                        "categoria": etiqueta,
                        "monto": _celda(valores, columnas, "ppto"),
                        "kilos": _celda(valores, columnas, "ppto en kilo"),
                    },
                )
            )
        if not columnas:
            raise ErrorValidacion(
                f"La hoja {HOJA_CUMPLIMIENTO} no tiene la fila de encabezado que empieza "
                "por «CODIGO»."
            )
        return filas

    @staticmethod
    def _normalizar_fila(numero: int, cruda: dict[str, object]) -> FilaCarga:
        normalizada: dict[str, object] = {}
        for clave, valor in cruda.items():
            destino = _ALIAS_COLUMNAS.get(str(clave).strip().lower())
            if destino is not None:
                normalizada[destino] = valor

        faltantes = {"punto_venta", "categoria"} - normalizada.keys()
        if faltantes:
            raise ErrorValidacion(
                "Faltan columnas obligatorias: " + ", ".join(sorted(faltantes)) + "."
            )

        codigo = str(normalizada["punto_venta"] or "").strip()
        # El C.O. llega tanto como '606' como 606; se normaliza a tres
        # posiciones con ceros a la izquierda, igual que en la ingesta (§3.4).
        if codigo.endswith(".0"):
            codigo = codigo[:-2]
        codigo = codigo.zfill(3)
        if not codigo.strip("0"):
            raise ErrorValidacion("La fila no indica punto de venta.")

        categoria = str(normalizada["categoria"] or "").strip()
        if not categoria:
            raise ErrorValidacion("La fila no indica categoría.")

        return FilaCarga(
            numero=numero,
            codigo_punto_venta=codigo,
            nombre_categoria=categoria,
            monto=_a_decimal(normalizada.get("monto"), "monto"),
            kilos=_a_decimal(normalizada.get("kilos"), "kilos"),
        )

    # ── Períodos ──────────────────────────────────────────────────────────────

    def listar_periodos(self) -> list[PeriodoSalida]:
        periodos = self._sesion.execute(
            select(Periodo).order_by(Periodo.anio.desc(), Periodo.mes.desc())
        ).scalars()
        autores = self._autores()
        return [
            PeriodoSalida(
                periodo=p.codigo,
                cerrado=p.cerrado,
                cerrado_por=autores.get(p.cerrado_por_id),
                cerrado_en=p.cerrado_en,
            )
            for p in periodos
        ]

    def cerrar_periodo(self, codigo_periodo: str, usuario: Usuario) -> PeriodoSalida:
        """Cierra el período. A partir de aquí el presupuesto es inmutable."""
        periodo = obtener_periodo(self._sesion, codigo_periodo)
        if periodo.cerrado:
            raise ErrorPeriodoCerrado(f"El período {periodo.codigo} ya estaba cerrado.")

        periodo.cerrado = True
        periodo.cerrado_por_id = usuario.id
        periodo.cerrado_en = ahora_utc()
        self._sesion.flush()

        logger.info("periodo_cerrado", periodo=periodo.codigo, usuario=usuario.usuario)
        return PeriodoSalida(
            periodo=periodo.codigo,
            cerrado=True,
            cerrado_por=usuario.usuario,
            cerrado_en=periodo.cerrado_en,
        )

    # ── Interno ───────────────────────────────────────────────────────────────

    @staticmethod
    def _exigir_alcance(punto: PuntoVenta, alcance: list[int] | None) -> None:
        """Corta la escritura sobre un punto que no es del usuario."""
        if alcance is not None and punto.id not in alcance:
            raise ErrorAutorizacion(
                f"No tiene alcance sobre el punto de venta {punto.codigo_co} {punto.nombre}."
            )

    @staticmethod
    def _exigir_periodo_abierto(periodo: Periodo) -> None:
        if periodo.cerrado:
            raise ErrorPeriodoCerrado(
                f"El período {periodo.codigo} está cerrado y no admite cambios de presupuesto."
            )

    def _historiar(
        self,
        fila: Presupuesto,
        campo: str,
        anterior: Decimal | None,
        nuevo: Decimal,
        motivo: str,
        usuario: Usuario | None,
    ) -> None:
        if anterior is not None and anterior == nuevo:
            return
        self._sesion.add(
            PresupuestoHistorial(
                presupuesto_id=fila.id,
                periodo_id=fila.periodo_id,
                punto_venta_id=fila.punto_venta_id,
                categoria_id=fila.categoria_id,
                campo=campo,
                valor_anterior=anterior,
                valor_nuevo=nuevo,
                motivo=motivo,
                usuario_id=usuario.id if usuario else None,
                cuando=self._instante(),
            )
        )

    @staticmethod
    def _instante() -> datetime:
        return ahora_utc()

    def _autores(self) -> dict[int | None, str]:
        """Mapa `id → usuario` para resolver los nombres de una sola consulta."""
        filas = self._sesion.execute(select(Usuario.id, Usuario.usuario)).all()
        return {fila[0]: fila[1] for fila in filas}

    def _punto_por_codigo(self, codigo: str) -> PuntoVenta:
        punto = self._sesion.execute(
            select(PuntoVenta).where(PuntoVenta.codigo_co == codigo.strip())
        ).scalar_one_or_none()
        if punto is None:
            raise ErrorNoEncontrado(f"No existe el punto de venta {codigo!r}.")
        return punto

    def _categoria_por_nombre(self, nombre: str) -> Categoria:
        categoria = self._sesion.execute(
            select(Categoria).where(Categoria.nombre == nombre.strip().upper())
        ).scalar_one_or_none()
        if categoria is None:
            raise ErrorNoEncontrado(f"No existe la categoría {nombre!r}.")
        return categoria


def _clave(titulo: object) -> str:
    """Encabezado reducido a llave comparable: `'PPTO EN KILO'` → `'ppto en kilo'`."""
    return clave_columna(titulo)


def _celda(valores: Sequence[object], columnas: dict[str, int], nombre: str) -> object:
    indice = columnas.get(nombre)
    if indice is None or indice >= len(valores):
        return None
    return valores[indice]


def _texto_celda(valor: object) -> str | None:
    """Texto saneado de una celda. `402` (número) y `'402'` dan lo mismo."""
    return normalizar_texto(valor)


def _a_decimal(valor: object, campo: str) -> Decimal:
    """Convierte a `Decimal` sin pasar por `float`.

    Se convierte desde `str` a propósito: `Decimal(0.1)` arrastra el error
    binario del `float` y en un presupuesto eso es un defecto, no un detalle.
    """
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return Decimal("0")
    texto = str(valor).strip().replace("$", "").replace(" ", "")
    # Formato colombiano: 1.234.567,89 → 1234567.89
    if "," in texto and "." in texto:
        texto = texto.replace(".", "").replace(",", ".")
    elif "," in texto:
        texto = texto.replace(",", ".")
    try:
        numero = Decimal(texto)
    except (InvalidOperation, ValueError) as exc:
        raise ErrorValidacion(f"El campo {campo} no es un número: {valor!r}.") from exc
    if numero < 0:
        raise ErrorValidacion(f"El campo {campo} no puede ser negativo.")
    return numero
