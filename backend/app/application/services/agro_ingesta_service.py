"""Ingesta de venta agropecuaria: carga, idempotencia y bitácora (§5).

Las invariantes son las mismas que las de carnes, aplicadas a otro negocio:

1. **Idempotencia.** Reprocesar un rango reemplaza esas fechas; no duplica. El
   borrado es por `(fecha, centro de operación)` y ocurre **dentro de la misma
   transacción** que la inserción, en un `SAVEPOINT`: si la carga falla a la
   mitad, la base no queda con medio día cargado. Se borra por par y no por
   rango entero por el mismo motivo que allí: una corrida que solo trae Montería
   no puede llevarse por delante los días buenos de Planta.

2. **Nada se descarta en silencio.** Cada fila que no entra deja su motivo en
   `agro_rechazos_ingesta` con número de fila, campo y valor. Y una fila mala no
   tumba la corrida: se rechaza esa y se sigue.

3. **El impuesto se guarda marcado, no se descarta.** `TipoItem = IMPUESTO` no
   es venta —es recaudo a nombre de terceros— pero se persiste con
   `es_impuesto = True` y se cuenta aparte en la corrida. Guardarlo permite
   conciliar fila a fila con el origen; excluirlo **al reportar** es lo que hace
   que los totales digan la verdad. Descartarlo en la ingesta habría dejado una
   diferencia contra el ERP que nadie podría explicar.

4. **Lo que llega vacío entra con su etiqueta visible, no se descarta ni se
   reparte.** El grupo llega vacío en el 22 % de las filas y entra como
   `SIN GRUPO`; la especie, el tipo comercial y el tipo de ítem, en un 1 %, con
   la suya. Repartir esa venta entre los miembros que sí tienen valor movería
   una quinta parte del total a renglones que no la hicieron.

5. **Lo que la fuente no entrega se persiste como `NULL`, no como cero.** Vale
   para `TotalCosto`: un costo ausente es «no se sabe» y un cero es «costó
   cero», y §4.4 los trata distinto. Un `or CERO` aquí devuelve al tablero el
   100 % de margen inventado.

6. **El catálogo de dimensiones lo puebla la ingesta.** No hay semilla: 626
   clientes y 252 productos que cambian solos no son datos que el negocio deba
   mantener a mano cuando el ERP ya los mantiene. Los miembros nuevos se dan de
   alta la primera vez que aparecen y su nombre se actualiza si cambió.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from time import perf_counter

from sqlalchemy import delete, insert, select
from sqlalchemy import update as sa_update
from sqlalchemy.orm import Session

from app.application.services.bitacora_ingesta import BitacoraIngesta
from app.application.services.periodos import obtener_o_crear_periodo
from app.core.errors import ErrorNoEncontrado
from app.core.logging import obtener_logger
from app.domain.enums import EstadoCorrida
from app.infrastructure.fuentes.agropecuaria import (
    FuenteVentaAgro,
    FuenteVentaAgropecuaria,
    LineaAgro,
)
from app.infrastructure.fuentes.base import AnotacionFuente, RechazoFuente
from app.infrastructure.models.agro_dimensiones import AgroDimension
from app.infrastructure.models.agro_ingesta import AgroCorridaIngesta, AgroRechazoIngesta
from app.infrastructure.models.agro_venta import AgroVentaLinea
from app.infrastructure.models.agro_vocabulario import (
    ETIQUETA_VACIA,
    TipoDimension,
    es_impuesto,
    normalizar_clave,
    normalizar_etiqueta,
)
from app.infrastructure.models.usuario import Usuario
from app.schemas.agro import CorridaAgroSalida, RechazoAgroSalida

logger = obtener_logger(__name__)

#: Filas por `executemany`. Agropecuaria son ~300 filas al día y ~9 000 al mes,
#: así que un lote de 2 000 cubre de sobra el caso real y deja margen para una
#: carga de historia de varios meses sin guardarla entera en memoria.
TAMANO_LOTE = 2000


@dataclass(frozen=True, slots=True)
class _FilaAgro:
    """Una línea lista para insertar, con su par de reemplazo al lado.

    El par `(fecha, centro)` viaja aparte del diccionario de valores para que el
    borrado idempotente no tenga que hurgar dentro de él: son las dos claves de
    la regla de §5 y merecen estar a la vista.
    """

    par: tuple[date, int]
    valores: dict[str, object]


@dataclass(slots=True)
class _Resumen:
    """Lo que produjo una pasada sobre la fuente."""

    leidas: int = 0
    aceptadas: int = 0
    impuesto: int = 0
    desde: date | None = None
    hasta: date | None = None

    def registrar_fecha(self, fecha: date) -> None:
        if self.desde is None or fecha < self.desde:
            self.desde = fecha
        if self.hasta is None or fecha > self.hasta:
            self.hasta = fecha


@dataclass(slots=True)
class _CatalogoAgro:
    """El catálogo de dimensiones, resuelto en memoria y ampliado al vuelo.

    Son poco más de novecientos miembros contando clientes y productos, así que
    caben enteros en un diccionario. Ir a la base una vez por celda de dimensión
    —ocho por fila— sería el cuello de botella de toda la carga.

    Los miembros nuevos se dan de alta aquí mismo, dentro de la transacción de
    la corrida: si la carga se deshace, el catálogo se deshace con ella y no
    quedan vendedores fantasma de una corrida que no llegó a existir.
    """

    sesion: Session
    _por_clave: dict[tuple[str, str], int] = field(default_factory=dict)
    _nombres: dict[tuple[str, str], str] = field(default_factory=dict)
    _periodos: dict[tuple[int, int], int] = field(default_factory=dict)

    @classmethod
    def cargar(cls, sesion: Session) -> _CatalogoAgro:
        catalogo = cls(sesion=sesion)
        for identificador, tipo, clave, nombre in sesion.execute(
            select(AgroDimension.id, AgroDimension.tipo, AgroDimension.clave, AgroDimension.nombre)
        ):
            catalogo._por_clave[(tipo, clave)] = identificador
            catalogo._nombres[(tipo, clave)] = nombre
        return catalogo

    def miembro(self, tipo: TipoDimension, clave_cruda: object, nombre_crudo: object) -> int:
        """`id` del miembro, dándolo de alta si es la primera vez que aparece.

        El nombre se actualiza cuando el origen lo cambia —un vendedor que se
        casa y cambia de apellido sigue siendo el mismo vendedor— pero la llave
        no se toca nunca: es lo que sostiene la historia y el presupuesto.

        Un miembro sin identificador entra con la llave `SIN_DATO` y su etiqueta
        visible (`SIN GRUPO`, `SIN ESPECIE`…). Es una fila más del reporte, no
        un hueco, y no se reparte entre los que sí tienen valor.
        """
        clave = normalizar_clave(tipo, clave_cruda)
        indice = (tipo.value, clave)

        nombre = normalizar_etiqueta(nombre_crudo) or ETIQUETA_VACIA[tipo]
        identificador = self._por_clave.get(indice)
        if identificador is not None:
            if self._nombres.get(indice) != nombre:
                self.sesion.execute(
                    sa_update(AgroDimension)
                    .where(AgroDimension.id == identificador)
                    .values(nombre=nombre)
                )
                self._nombres[indice] = nombre
            return identificador

        fila = AgroDimension(tipo=tipo.value, clave=clave, nombre=nombre)
        self.sesion.add(fila)
        self.sesion.flush()
        self._por_clave[indice] = fila.id
        self._nombres[indice] = nombre
        return fila.id

    def periodo(self, fecha: date) -> int:
        """`periodo_id` de la fecha, abriendo el período si hacía falta."""
        clave = (fecha.year, fecha.month)
        identificador = self._periodos.get(clave)
        if identificador is None:
            periodo = obtener_o_crear_periodo(self.sesion, f"{fecha.year:04d}-{fecha.month:02d}")
            identificador = periodo.id
            self._periodos[clave] = identificador
        return identificador


class AgroIngestaService:
    """Carga de venta agropecuaria y lectura de su bitácora."""

    def __init__(self, sesion: Session) -> None:
        self._sesion = sesion

    # ── Ejecución ─────────────────────────────────────────────────────────────

    def ejecutar(
        self,
        desde: date,
        hasta: date,
        usuario: Usuario | None = None,
        fuente: FuenteVentaAgro | None = None,
    ) -> CorridaAgroSalida:
        """Carga la venta del rango, **ambos extremos incluidos**.

        `fuente` se inyecta en las pruebas; en producción se construye contra la
        API de consulta con `id_cia=3`. Si falta el token, sale un 422 diciendo
        qué configurar antes de abrir la corrida; si la API falla, la corrida
        queda `FALLIDA` con su motivo en la bitácora y **sin medio día cargado**.
        """
        implementacion = fuente if fuente is not None else FuenteVentaAgropecuaria()
        origen = getattr(implementacion, "nombre", type(implementacion).__name__)

        inicio = perf_counter()
        corrida = AgroCorridaIngesta(
            usuario_id=usuario.id if usuario else None,
            fuente="agropecuaria",
            desde=desde,
            hasta=hasta,
            estado=EstadoCorrida.EN_CURSO.value,
            origen=str(origen)[:300],
        )
        self._sesion.add(corrida)
        self._sesion.flush()

        bitacora = BitacoraIngesta()
        resumen = _Resumen()
        try:
            with self._sesion.begin_nested():
                self._cargar(implementacion, desde, hasta, corrida, bitacora, resumen)
        except Exception as exc:
            corrida.estado = EstadoCorrida.FALLIDA.value
            corrida.mensaje = f"{type(exc).__name__}: {exc}"[:1000]
            # Lo que se alcanzó a insertar se deshizo con el `SAVEPOINT`, así que
            # `aceptadas` vuelve a cero. `leidas` y los rechazos sí se conservan:
            # dicen por dónde iba la carga cuando se cayó, que es justo lo que
            # alguien va a querer saber a las tres de la mañana.
            resumen.aceptadas = 0
            resumen.impuesto = 0
            logger.exception("agro_ingesta_fallida", origen=str(origen))
        else:
            corrida.estado = (
                EstadoCorrida.COMPLETADA_CON_RECHAZOS.value
                if bitacora.rechazadas
                else EstadoCorrida.COMPLETADA.value
            )
            if resumen.impuesto:
                corrida.mensaje = (
                    f"{resumen.impuesto} filas de TipoItem = IMPUESTO cargadas y marcadas. "
                    "Están guardadas para poder conciliar con el origen y **no suman** en "
                    "ningún reporte: no son venta, son recaudo a nombre de terceros."
                )
        finally:
            cerrar = getattr(implementacion, "cerrar", None)
            if callable(cerrar):
                cerrar()

        corrida.filas_leidas = resumen.leidas
        corrida.aceptadas = resumen.aceptadas
        corrida.impuesto = resumen.impuesto
        corrida.rechazadas = bitacora.rechazadas
        corrida.duracion_ms = int((perf_counter() - inicio) * 1000)

        for fila in bitacora.filas():
            self._sesion.add(AgroRechazoIngesta(corrida_id=corrida.id, **fila))
        self._sesion.flush()

        logger.info(
            "agro_ingesta_terminada",
            corrida=corrida.id,
            estado=corrida.estado,
            leidas=corrida.filas_leidas,
            aceptadas=corrida.aceptadas,
            impuesto=corrida.impuesto,
            rechazadas=corrida.rechazadas,
            duracion_ms=corrida.duracion_ms,
        )
        return self._a_salida(corrida, usuario)

    # ── Motor de la carga ─────────────────────────────────────────────────────

    def _cargar(
        self,
        implementacion: FuenteVentaAgro,
        desde: date,
        hasta: date,
        corrida: AgroCorridaIngesta,
        bitacora: BitacoraIngesta,
        resumen: _Resumen,
    ) -> None:
        """Lee la fuente, reemplaza los días que trae e inserta por lotes.

        `resumen` lo crea quien llama, no este método: si la carga se cae, lo que
        llevaba contado tiene que sobrevivir a la excepción.
        """
        catalogo = _CatalogoAgro.cargar(self._sesion)
        reemplazados: set[tuple[date, int]] = set()
        lote: list[_FilaAgro] = []

        for linea in implementacion.obtener_ventas(desde, hasta):
            resumen.leidas += 1
            fila = self._normalizar(linea, catalogo, corrida.id, bitacora, resumen)
            resumen.registrar_fecha(linea.fecha)
            lote.append(fila)
            if len(lote) >= TAMANO_LOTE:
                resumen.aceptadas += self._volcar(lote, reemplazados)

        resumen.aceptadas += self._volcar(lote, reemplazados)

        # Lo que la fuente no pudo ni formar —fechas ilegibles, importes que no
        # son números— también es fila leída y también es rechazo con motivo.
        for rechazo in getattr(implementacion, "rechazos", ()):
            if not isinstance(rechazo, RechazoFuente):  # pragma: no cover - defensa
                continue
            resumen.leidas += 1
            bitacora.rechazar(rechazo.fila, rechazo.campo, rechazo.valor, rechazo.motivo)

        # Y lo que la fuente sabe y nadie más puede saber: cuántas filas trajo,
        # cuántas llegaron sin costo, cuáles venían fuera de rango. No son filas
        # perdidas, así que se anotan sin tocar el recuento: contarlas como
        # rechazos diría que se perdió venta que no se perdió.
        for anotacion in getattr(implementacion, "anotaciones", ()):
            if not isinstance(anotacion, AnotacionFuente):  # pragma: no cover - defensa
                continue
            bitacora.anotar(anotacion.fila, anotacion.campo, anotacion.valor, anotacion.motivo)

    def _normalizar(
        self,
        linea: LineaAgro,
        catalogo: _CatalogoAgro,
        corrida_id: int,
        bitacora: BitacoraIngesta,
        resumen: _Resumen,
    ) -> _FilaAgro:
        """Una `LineaAgro` cruda a la fila que se inserta.

        **No devuelve `None` y no rechaza nada**, a diferencia de su homóloga de
        carnes, y la asimetría es deliberada: allí el punto de venta y la
        categoría se resuelven contra un catálogo que el negocio mantiene, y una
        fila que no case con él es un dato que alguien tiene que arreglar. Aquí
        el catálogo lo puebla esta misma ingesta, así que **cualquier** miembro
        es válido por definición y lo único que podía fallar —la fecha, los
        importes, el centro— ya lo rechazó la fuente antes de formar la línea.
        """
        centro_id = catalogo.miembro(
            TipoDimension.CENTRO_OPERACION, linea.co_id, linea.centro_operacion
        )
        impuesto = es_impuesto(linea.tipo_item)
        if impuesto:
            resumen.impuesto += 1

        if linea.grupo_id is None and linea.grupo is None:
            # El 22 % de las filas. Se anota una vez —la bitácora agrega por
            # motivo y lleva el recuento— para que quede constancia de cuánta
            # venta está bajo `SIN GRUPO`, que es una pregunta que el negocio va
            # a hacer en cuanto vea el renglón.
            bitacora.anotar(
                linea.fila_origen,
                "Grupo",
                None,
                "Fila sin grupo en el origen; entra como «SIN GRUPO» y **se reporta como una "
                "fila más**. No se reparte entre los grupos que sí tienen valor ni se "
                "esconde: es una quinta parte de la venta y tiene que verse.",
            )

        if linea.total_costo is None:
            bitacora.anotar(
                linea.fila_origen,
                "TotalCosto",
                None,
                "Fila sin costo en el origen; entra como NULL —no como cero— y **no tiene "
                "margen calculable**. Ningún agregado que la contenga publica margen: la "
                "pantalla muestra «—» hasta que la fuente entregue el dato (§4.4).",
            )

        return _FilaAgro(
            par=(linea.fecha, centro_id),
            valores={
                "periodo_id": catalogo.periodo(linea.fecha),
                "fecha": linea.fecha,
                "centro_id": centro_id,
                "tipo_item_id": catalogo.miembro(
                    TipoDimension.TIPO_ITEM, linea.tipo_item_id, linea.tipo_item
                ),
                "especie_id": catalogo.miembro(
                    TipoDimension.ESPECIE, linea.especie_id, linea.especie
                ),
                "tipo_comercial_id": catalogo.miembro(
                    TipoDimension.TIPO_COMERCIAL, linea.tipo_comercial_id, linea.tipo_comercial
                ),
                "grupo_id": catalogo.miembro(TipoDimension.GRUPO, linea.grupo_id, linea.grupo),
                "vendedor_id": catalogo.miembro(
                    TipoDimension.VENDEDOR, linea.codigo_vendedor, linea.nombre_vendedor
                ),
                # El cliente **no trae NIT en esta fuente**: la única columna es
                # su razón social, así que la llave es el propio nombre
                # normalizado. Dos clientes con la misma razón social en el
                # origen son uno solo aquí; está dicho en `docs/API.md` y es una
                # limitación de la fuente, no una decisión de diseño.
                "cliente_id": catalogo.miembro(TipoDimension.CLIENTE, linea.cliente, linea.cliente),
                "item_id": catalogo.miembro(TipoDimension.ITEM, linea.item_ref, linea.item_desc),
                "es_impuesto": impuesto,
                "cantidad_inv": linea.cantidad_inv,
                "kilos_total": linea.kilos_total,
                "valor_bruto": linea.valor_bruto,
                "descuentos": linea.descuentos,
                "valor_subtotal": linea.valor_subtotal,
                "total_neto": linea.total_neto,
                # **El nulo se persiste tal cual.** Un `or CERO` aquí, por
                # inocente que parezca, devuelve el 100 % de margen falso.
                "total_costo": linea.total_costo,
                "utilidad_bruta": linea.utilidad_bruta,
                "lineas_facturadas": linea.lineas_facturadas,
                "tipo_item_siesa": (linea.tipo_item or "")[:60] or None,
                "corrida_id": corrida_id,
            },
        )

    # ── Idempotencia ──────────────────────────────────────────────────────────

    def _volcar(self, lote: list[_FilaAgro], reemplazados: set[tuple[date, int]]) -> int:
        """Reemplaza los días que trae el lote e inserta. Devuelve lo insertado."""
        if not lote:
            return 0
        self._asegurar_reemplazo(lote, reemplazados)
        self._sesion.execute(insert(AgroVentaLinea), [fila.valores for fila in lote])
        insertadas = len(lote)
        lote.clear()
        return insertadas

    def _asegurar_reemplazo(
        self, lote: list[_FilaAgro], reemplazados: set[tuple[date, int]]
    ) -> None:
        """Borra `(fecha, centro)` la primera vez que aparece en la corrida.

        Es **la** regla de §5: «reprocesar una fecha reemplaza el día completo;
        no duplica». Se borra por par `(fecha, centro de operación)` y no por el
        rango entero por una razón concreta: una corrida puede traer solo un
        centro, y borrar el rango completo se llevaría por delante los días
        buenos del otro sin que nadie lo pidiera. Lo que la corrida trae, lo
        reemplaza; lo que no trae, no lo toca.

        El borrado ocurre justo antes de la primera inserción de ese par y dentro
        del mismo `SAVEPOINT`: no existe ningún instante en el que el día esté
        borrado y no reescrito.
        """
        nuevos = {fila.par for fila in lote} - reemplazados
        for fecha, centro_id in nuevos:
            self._sesion.execute(
                delete(AgroVentaLinea).where(
                    AgroVentaLinea.fecha == fecha,
                    AgroVentaLinea.centro_id == centro_id,
                )
            )
            reemplazados.add((fecha, centro_id))

    # ── Lectura (operativa) ───────────────────────────────────────────────────

    def listar_corridas(self, limite: int = 50) -> list[CorridaAgroSalida]:
        """Últimas corridas, de la más reciente a la más antigua."""
        corridas = self._sesion.execute(
            select(AgroCorridaIngesta).order_by(AgroCorridaIngesta.cuando.desc()).limit(limite)
        ).scalars()
        autores = {
            fila[0]: fila[1] for fila in self._sesion.execute(select(Usuario.id, Usuario.usuario))
        }
        return [self._a_salida(c, None, autores.get(c.usuario_id)) for c in corridas]

    def rechazos(self, corrida_id: int) -> list[RechazoAgroSalida]:
        """Filas rechazadas de una corrida, con su motivo."""
        corrida = self._sesion.get(AgroCorridaIngesta, corrida_id)
        if corrida is None:
            raise ErrorNoEncontrado(f"No existe la corrida agropecuaria {corrida_id}.")

        rechazos = self._sesion.execute(
            select(AgroRechazoIngesta)
            .where(AgroRechazoIngesta.corrida_id == corrida_id)
            .order_by(AgroRechazoIngesta.fila)
        ).scalars()
        return [
            RechazoAgroSalida(fila=r.fila, campo=r.campo, valor=r.valor, motivo=r.motivo)
            for r in rechazos
        ]

    def ultima_corrida(self) -> AgroCorridaIngesta | None:
        """La corrida más reciente."""
        return self._sesion.execute(
            select(AgroCorridaIngesta).order_by(AgroCorridaIngesta.cuando.desc()).limit(1)
        ).scalar_one_or_none()

    # ── Interno ───────────────────────────────────────────────────────────────

    @staticmethod
    def _a_salida(
        corrida: AgroCorridaIngesta, usuario: Usuario | None, quien: str | None = None
    ) -> CorridaAgroSalida:
        return CorridaAgroSalida(
            id=corrida.id,
            cuando=corrida.cuando,
            quien=usuario.usuario if usuario else quien,
            fuente=corrida.fuente,
            desde=corrida.desde,
            hasta=corrida.hasta,
            estado=corrida.estado,
            filas_leidas=corrida.filas_leidas,
            aceptadas=corrida.aceptadas,
            rechazadas=corrida.rechazadas,
            impuesto=corrida.impuesto,
            duracion_ms=corrida.duracion_ms,
        )


def totales_impuesto(sesion: Session, periodo_id: int, hasta: date) -> tuple[Decimal, Decimal, int]:
    """Venta, kilos y líneas de impuesto del corte, para la conciliación.

    Vive aquí y no en el servicio de reportes porque es la contrapartida de la
    decisión de esta ingesta: lo que se guardó marcado y no suma tiene que poder
    verse en alguna parte, o la primera conciliación contra el ERP se convierte
    en una búsqueda a ciegas.
    """
    from sqlalchemy import func

    fila = sesion.execute(
        select(
            func.sum(AgroVentaLinea.total_neto),
            func.sum(AgroVentaLinea.kilos_total),
            func.sum(AgroVentaLinea.lineas_facturadas),
        ).where(
            AgroVentaLinea.periodo_id == periodo_id,
            AgroVentaLinea.fecha <= hasta,
            AgroVentaLinea.es_impuesto.is_(True),
        )
    ).one()
    return Decimal(fila[0] or 0), Decimal(fila[1] or 0), int(fila[2] or 0)
