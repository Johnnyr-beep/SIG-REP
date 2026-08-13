"""Ingesta de venta: carga, idempotencia y bitácora (§5).

El servicio consume el puerto `FuenteVenta` de `app/domain/puertos.py` y nunca
la fuente concreta. Hay dos vivas —`FuenteVentaExcel` y `FuenteVentaSiesa`— y
elegir una es `SIGREP_FUENTE_VENTA`, no un refactor: todo lo que sigue funciona
igual con cualquiera de las dos.

Las cinco invariantes que esta implementación hace cumplir:

1. **Idempotencia (§5, §7).** Reprocesar un rango reemplaza esas fechas; no
   duplica. El borrado es por `(fecha, punto_venta)` y ocurre **dentro de la
   misma transacción** que la inserción, en un `SAVEPOINT`: si la carga falla a
   la mitad, la base no queda con medio día cargado. Se borra por par y no por
   rango entero a propósito —ver `_asegurar_reemplazo`—.
2. **Nada se descarta en silencio.** Cada fila que no entra deja su motivo en
   `rechazos_ingesta` con número de fila, campo y valor. Y una fila mala no
   tumba la corrida: se rechaza esa y se sigue.
3. **Normalización de §3.4.** C.O. a tres posiciones, `strip()` en los NIT,
   clase de cliente contra catálogo, `Domicilio` en blanco a `NULL`. Vive en
   `app/domain/normalizacion.py`, con pruebas propias.
4. **Categoría por mapeo, no por código.** Se resuelve contra `mapeo_categorias`
   por texto exacto; lo que no está mapeado va a `OTROS` **y queda registrado**.
5. **Un punto de venta sin presupuesto no rompe nada.** 432 EVENTOS BUCARAMANGA
   se ingiere como cualquier otro; es el reporte quien lo muestra aparte.
6. **Lo que la fuente no entrega se persiste como `NULL`, no como cero.** Vale
   para el costo, que la API no da para PEREIRA: `costo_promedio` viaja nulo
   hasta la base y §4.4 lo convierte en «—» en lugar de en un 100 % de margen.

Sobre el tamaño: 131 819 filas por nueve días, ~440 000 al mes. Se lee en
streaming y se inserta por lotes de `TAMANO_LOTE` con `executemany`. Ni la
fuente ni el servicio materializan la hoja completa.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from time import perf_counter

from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from app.application.services.bitacora_ingesta import BitacoraIngesta
from app.application.services.periodos import obtener_o_crear_periodo
from app.core.config import obtener_settings
from app.core.errors import ErrorNoEncontrado, ErrorValidacion
from app.core.logging import obtener_logger
from app.domain.enums import EstadoCorrida, FuenteIngesta
from app.domain.normalizacion import (
    CATEGORIA_POR_DEFECTO,
    SIN_CLASIFICAR,
    normalizar_centro_operacion,
    normalizar_clase_cliente,
    normalizar_condicion_pago,
    normalizar_domicilio,
    normalizar_nit,
    normalizar_texto,
)
from app.domain.puertos import FuenteVenta, LineaVenta
from app.infrastructure.fuentes import (
    AnotacionFuente,
    ClienteFuente,
    FuenteConClientes,
    FuenteVentaExcel,
    FuenteVentaSiesa,
    RechazoFuente,
)
from app.infrastructure.models.catalogo import Categoria, MapeoCategoria
from app.infrastructure.models.ingesta import CorridaIngesta, RechazoIngesta
from app.infrastructure.models.organizacion import PuntoVenta
from app.infrastructure.models.usuario import Usuario
from app.infrastructure.models.venta import Cliente, VentaLinea
from app.schemas.ingesta import CorridaSalida, RechazoSalida

logger = obtener_logger(__name__)

#: Filas por `executemany`. 2 000 es el punto donde deja de notarse el coste por
#: sentencia y todavía no se guarda medio archivo en memoria.
TAMANO_LOTE = 2000

#: Rango que se pide a la fuente cuando lo marca el propio archivo (carga por
#: `POST /ingesta/archivo`): se toma todo y las fechas de la corrida se deducen
#: de lo que traía.
_RANGO_COMPLETO = (date(1900, 1, 1), date(2999, 12, 31))

MENSAJE_RUTA_PENDIENTE = (
    "La fuente «excel» necesita saber qué libro leer. Configure "
    "`SIGREP_RUTA_ARCHIVO_VENTA` con la ruta del archivo de SIESA, o suba el "
    "archivo por `POST /ingesta/archivo`."
)


def obtener_fuente(
    fuente: FuenteIngesta | None = None, sesion: Session | None = None
) -> FuenteVenta:
    """Devuelve la implementación configurada del puerto `FuenteVenta`.

    Sin argumento manda `SIGREP_FUENTE_VENTA`. Es el **único** punto del sistema
    que conoce las dos implementaciones: cambiar de Excel a SIESA es una
    variable de entorno, no un refactor (§5).

    `sesion` solo la necesita la fuente SIESA, y para una cosa concreta: la API
    no entrega el código de centro de operación, solo su descripción (`desc_co`),
    así que hay que pasarle el directorio `{descripción: C.O.}` que la semilla ya
    guarda en `puntos_venta`. Se le pasa armado en lugar de dejar que la fuente
    consulte la base: así la fuente se prueba entera sin montar un esquema.
    """
    settings = obtener_settings()
    elegida = fuente.value if fuente is not None else settings.fuente_venta

    if elegida == FuenteIngesta.SIESA.value:
        return FuenteVentaSiesa(_descripciones_siesa(sesion))

    ruta = normalizar_texto(settings.ruta_archivo_venta)
    if ruta is None:
        raise ErrorValidacion(MENSAJE_RUTA_PENDIENTE)
    return FuenteVentaExcel(ruta)


def _descripciones_siesa(sesion: Session | None) -> dict[str, str]:
    """`{descripcion_siesa: codigo_co}` de los puntos que tienen descripción."""
    if sesion is None:
        return {}
    filas = sesion.execute(
        select(PuntoVenta.descripcion_siesa, PuntoVenta.codigo_co).where(
            PuntoVenta.descripcion_siesa.is_not(None)
        )
    ).tuples()
    return {descripcion: codigo for descripcion, codigo in filas if descripcion}


@dataclass(frozen=True, slots=True)
class _FilaVenta:
    """Una línea lista para insertar, con su par de reemplazo al lado.

    El par `(fecha, punto de venta)` viaja aparte del diccionario de valores
    para que el borrado idempotente no tenga que hurgar dentro de él: son las
    dos claves de la regla de §5 y merecen estar a la vista.
    """

    par: tuple[date, int]
    valores: dict[str, object]


@dataclass(slots=True)
class _ResumenCarga:
    """Lo que produjo una pasada sobre la fuente."""

    leidas: int = 0
    aceptadas: int = 0
    desde: date | None = None
    hasta: date | None = None
    clientes: int = 0

    def registrar_fecha(self, fecha: date) -> None:
        if self.desde is None or fecha < self.desde:
            self.desde = fecha
        if self.hasta is None or fecha > self.hasta:
            self.hasta = fecha


@dataclass(slots=True)
class _Catalogo:
    """Los catálogos que la ingesta consulta una vez por fila.

    Se cargan enteros al empezar y se resuelven en memoria. Son 17 puntos de
    venta, 8 categorías, una docena de mapeos y unos cientos de clientes: ir a
    la base 440 000 veces al mes para preguntar lo mismo sería el cuello de
    botella de toda la carga.
    """

    sesion: Session
    puntos: dict[str, int] = field(default_factory=dict)
    categorias: dict[str, int] = field(default_factory=dict)
    clientes: dict[str, int] = field(default_factory=dict)
    id_otros: int = 0
    _periodos: dict[tuple[int, int], int] = field(default_factory=dict)

    @classmethod
    def cargar(cls, sesion: Session) -> _Catalogo:
        catalogo = cls(sesion=sesion)
        catalogo.puntos = dict(
            sesion.execute(select(PuntoVenta.codigo_co, PuntoVenta.id)).tuples().all()
        )
        catalogo.categorias = dict(
            sesion.execute(select(MapeoCategoria.texto_siesa, MapeoCategoria.categoria_id))
            .tuples()
            .all()
        )
        catalogo.clientes = dict(sesion.execute(select(Cliente.nit, Cliente.id)).tuples().all())
        id_otros = sesion.execute(
            select(Categoria.id).where(Categoria.nombre == CATEGORIA_POR_DEFECTO)
        ).scalar_one_or_none()
        if id_otros is None:
            raise ErrorNoEncontrado(
                f"Falta la categoría {CATEGORIA_POR_DEFECTO}, que es donde aterriza toda "
                "categoría de SIESA sin mapeo. Siembre la estructura antes de ingerir."
            )
        catalogo.id_otros = id_otros
        return catalogo

    def periodo(self, fecha: date) -> int:
        """`periodo_id` de la fecha, abriendo el período si hacía falta."""
        clave = (fecha.year, fecha.month)
        identificador = self._periodos.get(clave)
        if identificador is None:
            periodo = obtener_o_crear_periodo(self.sesion, f"{fecha.year:04d}-{fecha.month:02d}")
            identificador = periodo.id
            self._periodos[clave] = identificador
        return identificador


class IngestaService:
    """Carga de venta y lectura de la bitácora de ingesta."""

    def __init__(self, sesion: Session) -> None:
        self._sesion = sesion
        self._settings = obtener_settings()

    # ── Ejecución ─────────────────────────────────────────────────────────────

    def ejecutar(
        self,
        desde: date,
        hasta: date,
        fuente: FuenteIngesta,
        usuario: Usuario | None = None,
    ) -> CorridaSalida:
        """Carga la venta del rango desde la fuente indicada.

        Con `fuente="siesa"` se consulta la API de consulta de Grupo Santa Cruz;
        si falta el token o la estructura no está sembrada, sale un 422 diciendo
        qué configurar, y si la API falla, la corrida queda `FALLIDA` con su
        motivo en la bitácora.
        """
        implementacion = obtener_fuente(fuente, self._sesion)
        origen = getattr(implementacion, "nombre", type(implementacion).__name__)
        return self._correr(
            implementacion,
            fuente=fuente,
            desde=desde,
            hasta=hasta,
            origen=str(origen),
            usuario=usuario,
        )

    def ingerir_archivo(
        self,
        contenido: bytes,
        nombre_archivo: str,
        usuario: Usuario | None = None,
    ) -> CorridaSalida:
        """Carga la venta de un `.xlsx` con el formato del libro de SIESA.

        Es el camino que permite validar SIGREP contra el archivo actual sin
        esperar a la API. Si el libro trae además la hoja `CLIENTES`, se carga
        el catálogo **en la misma transacción y antes que la venta**, que es lo
        que hace que las líneas queden enlazadas con su vendedor de una sola
        pasada.

        El rango de la corrida no se pide: lo dice el archivo. Se toma el mínimo
        y el máximo de las fechas que traía.
        """
        if not nombre_archivo.lower().endswith((".xlsx", ".xlsm")):
            raise ErrorValidacion("Formato no admitido. Use .xlsx.")

        fuente = FuenteVentaExcel(contenido, nombre=nombre_archivo)
        if not fuente.tiene_venta and not fuente.tiene_clientes:
            fuente.cerrar()
            raise ErrorValidacion(
                "El libro no trae ninguna hoja reconocible. Se espera «VENTA» con el "
                "detalle de SIESA y, opcionalmente, «CLIENTES» con el catálogo."
            )

        return self._correr(
            fuente,
            fuente=FuenteIngesta.EXCEL,
            desde=None,
            hasta=None,
            origen=nombre_archivo,
            usuario=usuario,
        )

    # ── Motor de la corrida ───────────────────────────────────────────────────

    def _correr(
        self,
        implementacion: FuenteVenta,
        *,
        fuente: FuenteIngesta,
        desde: date | None,
        hasta: date | None,
        origen: str,
        usuario: Usuario | None,
    ) -> CorridaSalida:
        """Abre la corrida, carga y la cierra con su estado y su bitácora.

        La corrida se registra **fuera** del `SAVEPOINT` de los datos. Así, si la
        carga se cae a mitad, los datos se deshacen enteros —nunca medio día
        cargado— pero el intento fallido queda en la bitácora con su motivo. Una
        corrida que falla y no deja rastro es indistinguible de una que nadie
        lanzó.
        """
        inicio = perf_counter()
        corrida = CorridaIngesta(
            usuario_id=usuario.id if usuario else None,
            fuente=fuente.value,
            desde=desde,
            hasta=hasta,
            estado=EstadoCorrida.EN_CURSO.value,
            origen=origen[:300],
        )
        self._sesion.add(corrida)
        self._sesion.flush()

        bitacora = BitacoraIngesta()
        resumen = _ResumenCarga()
        try:
            with self._sesion.begin_nested():
                self._cargar(implementacion, desde, hasta, corrida, bitacora, resumen)
        except NotImplementedError:
            # Una fuente que declara el puerto pero no lo implementa. No se
            # intentó nada, así que no hay corrida que contar: se deja subir y
            # `core/errors.py` responde 501. Un fallo de la API de SIESA **no**
            # entra por aquí: es `ErrorFuenteSiesa` y cierra la corrida como
            # FALLIDA con su motivo, que es lo que exige §5.
            raise
        except Exception as exc:
            corrida.estado = EstadoCorrida.FALLIDA.value
            corrida.mensaje = f"{type(exc).__name__}: {exc}"[:1000]
            # Lo que se alcanzó a insertar se deshizo con el `SAVEPOINT`, así que
            # `aceptadas` vuelve a cero. `leidas` y los rechazos sí se conservan:
            # dicen por dónde iba la carga cuando se cayó, que es justo lo que
            # alguien va a querer saber a las tres de la mañana.
            resumen.aceptadas = 0
            logger.exception("ingesta_fallida", origen=origen, fuente=fuente.value)
        else:
            corrida.estado = (
                EstadoCorrida.COMPLETADA_CON_RECHAZOS.value
                if bitacora.rechazadas
                else EstadoCorrida.COMPLETADA.value
            )
            if resumen.clientes:
                corrida.mensaje = f"Catálogo de clientes: {resumen.clientes} registros al día."
        finally:
            cerrar = getattr(implementacion, "cerrar", None)
            if callable(cerrar):
                cerrar()

        corrida.filas_leidas = resumen.leidas
        corrida.aceptadas = resumen.aceptadas
        corrida.rechazadas = bitacora.rechazadas
        corrida.desde = desde or resumen.desde
        corrida.hasta = hasta or resumen.hasta
        corrida.duracion_ms = int((perf_counter() - inicio) * 1000)

        for fila in bitacora.filas():
            self._sesion.add(RechazoIngesta(corrida_id=corrida.id, **fila))
        self._sesion.flush()

        logger.info(
            "ingesta_terminada",
            corrida=corrida.id,
            estado=corrida.estado,
            leidas=corrida.filas_leidas,
            aceptadas=corrida.aceptadas,
            rechazadas=corrida.rechazadas,
            duracion_ms=corrida.duracion_ms,
        )
        return self._a_salida(corrida, usuario)

    def _cargar(
        self,
        implementacion: FuenteVenta,
        desde: date | None,
        hasta: date | None,
        corrida: CorridaIngesta,
        bitacora: BitacoraIngesta,
        resumen: _ResumenCarga,
    ) -> None:
        """Lee la fuente, reemplaza los días que trae e inserta por lotes.

        `resumen` lo crea quien llama, no este método: si la carga se cae, lo
        que llevaba contado tiene que sobrevivir a la excepción.
        """
        if isinstance(implementacion, FuenteConClientes):
            resumen.clientes = self._cargar_clientes(implementacion.obtener_clientes(), bitacora)

        catalogo = _Catalogo.cargar(self._sesion)
        reemplazados: set[tuple[date, int]] = set()
        lote: list[_FilaVenta] = []

        inicio = desde or _RANGO_COMPLETO[0]
        fin = hasta or _RANGO_COMPLETO[1]

        for linea in implementacion.obtener_ventas(inicio, fin):
            resumen.leidas += 1
            fila = self._normalizar(linea, catalogo, corrida.id, bitacora)
            if fila is None:
                continue
            resumen.registrar_fecha(linea.fecha)
            lote.append(fila)
            if len(lote) >= TAMANO_LOTE:
                resumen.aceptadas += self._volcar(lote, reemplazados)

        resumen.aceptadas += self._volcar(lote, reemplazados)

        # Lo que la fuente no pudo ni formar (fechas ilegibles, importes que no
        # son números) también es fila leída y también es rechazo con motivo.
        for rechazo in getattr(implementacion, "rechazos", ()):
            if not isinstance(rechazo, RechazoFuente):  # pragma: no cover - defensa
                continue
            resumen.leidas += 1
            bitacora.rechazar(rechazo.fila, rechazo.campo, rechazo.valor, rechazo.motivo)

        # Y lo que la fuente sabe y nadie más puede saber: de qué módulo de
        # SIESA vino cada fila —el `Origen` de `costos-razon-social`— y que el
        # de PEREIRA no trae costo. No son filas perdidas, así que se anotan sin
        # tocar el recuento: contarlas como rechazos diría que se perdió venta
        # que no se perdió.
        for anotacion in getattr(implementacion, "anotaciones", ()):
            if not isinstance(anotacion, AnotacionFuente):  # pragma: no cover - defensa
                continue
            bitacora.anotar(anotacion.fila, anotacion.campo, anotacion.valor, anotacion.motivo)

    def _normalizar(
        self,
        linea: LineaVenta,
        catalogo: _Catalogo,
        corrida_id: int,
        bitacora: BitacoraIngesta,
    ) -> _FilaVenta | None:
        """Una `LineaVenta` cruda a la fila que se inserta, o `None` si se rechaza."""
        centro = normalizar_centro_operacion(linea.centro_operacion)
        punto_venta_id = catalogo.puntos.get(centro or "")
        if punto_venta_id is None:
            bitacora.rechazar(
                linea.fila_origen,
                "C.O.",
                linea.centro_operacion,
                f"El centro de operación {centro!r} no es un punto de venta conocido.",
            )
            return None

        categoria_id, categoria_cruda = self._resolver_categoria(linea, catalogo, bitacora)
        clase = self._resolver_clase(linea, bitacora)
        domicilio = normalizar_domicilio(linea.domicilio)
        if domicilio is None:
            bitacora.anotar(
                linea.fila_origen,
                "Domicilio",
                linea.domicilio,
                "Domicilio sin valor reconocible; se guarda como NULL, no como «No».",
            )

        nit = normalizar_nit(linea.nit_cliente)
        return _FilaVenta(
            par=(linea.fecha, punto_venta_id),
            valores={
                "periodo_id": catalogo.periodo(linea.fecha),
                "fecha": linea.fecha,
                "punto_venta_id": punto_venta_id,
                "categoria_id": categoria_id,
                "cliente_id": catalogo.clientes.get(nit or ""),
                "corrida_id": corrida_id,
                "valor_subtotal": linea.valor_subtotal,
                # **El nulo se persiste tal cual.** Si la fuente no entregó el
                # costo —PEREIRA, en el 100 % de sus filas—, la columna queda en
                # `NULL` y §4.4 publica «—» en todo agregado que contenga esa
                # línea. Un `or CERO` aquí, por inocente que parezca, devuelve el
                # 100 % de margen falso al tablero de la gerencia.
                "costo_promedio": linea.costo_promedio,
                "cantidad_inv": linea.cantidad_inv,
                "margen_siesa": linea.margen_siesa,
                "categoria_siesa": categoria_cruda,
                "nit_cliente": nit,
                "domicilio": domicilio,
                "clase_cliente": clase,
                "condicion_pago": normalizar_condicion_pago(linea.condicion_pago),
            },
        )

    def _resolver_categoria(
        self, linea: LineaVenta, catalogo: _Catalogo, bitacora: BitacoraIngesta
    ) -> tuple[int, str | None]:
        """Categoría por la tabla `mapeo_categorias`, nunca por un `dict` del código.

        El mapeo es por **texto exacto**: existen `0006 - QUESO Y LACTEOS` y
        `0006 - QUESOS Y LACTEOS`, con distinta ortografía, y ambos están
        sembrados como filas separadas. Normalizar el texto para «arreglarlo»
        escondería un problema de origen que el negocio necesita ver.

        Lo que no está mapeado va a `OTROS` **y deja constancia**. Esa constancia
        es la diferencia entre reclasificar por decisión y por accidente.
        """
        cruda = normalizar_texto(linea.categoria_siesa, limite=120)
        if cruda is None:
            bitacora.anotar(
                linea.fila_origen,
                "CATEGORIA",
                None,
                f"Fila sin categoría en el origen; se clasifica como {CATEGORIA_POR_DEFECTO}.",
            )
            return catalogo.id_otros, None

        categoria_id = catalogo.categorias.get(cruda)
        if categoria_id is None:
            bitacora.anotar(
                linea.fila_origen,
                "CATEGORIA",
                cruda,
                "Texto sin mapeo en `mapeo_categorias`; se clasifica como "
                f"{CATEGORIA_POR_DEFECTO}. Añada el mapeo en Catálogos si corresponde a "
                "otra categoría.",
            )
            return catalogo.id_otros, cruda
        return categoria_id, cruda

    @staticmethod
    def _resolver_clase(linea: LineaVenta, bitacora: BitacoraIngesta) -> str:
        """`CLASES DE CLIENTES` contra el catálogo; el resto, `SIN CLASIFICAR`.

        En el archivo real esta columna trae 95 907 filas vacías, 109 con un
        nombre de usuario y unas cuantas con marcas de tiempo. Nada de eso se
        guarda como si fuera una clase de cliente, y nada de eso se calla.
        """
        clase = normalizar_clase_cliente(linea.clase_cliente)
        if clase is not None:
            return clase

        crudo = normalizar_texto(linea.clase_cliente)
        motivo = (
            f"Fila sin clase de cliente en el origen; se guarda como {SIN_CLASIFICAR}."
            if crudo is None
            else (
                "Valor que no es una clase de cliente del catálogo; se guarda como "
                f"{SIN_CLASIFICAR}."
            )
        )
        bitacora.anotar(linea.fila_origen, "CLASES DE CLIENTES", crudo, motivo)
        return SIN_CLASIFICAR

    # ── Idempotencia ──────────────────────────────────────────────────────────

    def _volcar(self, lote: list[_FilaVenta], reemplazados: set[tuple[date, int]]) -> int:
        """Reemplaza los días que trae el lote e inserta. Devuelve lo insertado."""
        if not lote:
            return 0
        self._asegurar_reemplazo(lote, reemplazados)
        self._sesion.execute(insert(VentaLinea), [fila.valores for fila in lote])
        insertadas = len(lote)
        lote.clear()
        return insertadas

    def _asegurar_reemplazo(
        self, lote: list[_FilaVenta], reemplazados: set[tuple[date, int]]
    ) -> None:
        """Borra `(fecha, punto_venta)` la primera vez que aparece en la corrida.

        Es **la** regla de §5: «reprocesar una fecha reemplaza el día completo;
        no duplica». Y se borra por par `(fecha, punto de venta)` y no por el
        rango entero por una razón concreta: un archivo puede traer solo tres
        puntos de venta, y borrar el rango completo se llevaría por delante los
        días buenos de los otros trece sin que nadie lo pidiera. Lo que la
        corrida trae, lo reemplaza; lo que no trae, no lo toca.

        El borrado ocurre justo antes de la primera inserción de ese par y
        dentro del mismo `SAVEPOINT`: no existe ningún instante en el que el día
        esté borrado y no reescrito.
        """
        nuevos = {fila.par for fila in lote} - reemplazados
        for fecha, punto_venta_id in nuevos:
            self._sesion.execute(
                delete(VentaLinea).where(
                    VentaLinea.fecha == fecha,
                    VentaLinea.punto_venta_id == punto_venta_id,
                )
            )
            reemplazados.add((fecha, punto_venta_id))

    # ── Catálogo de clientes ──────────────────────────────────────────────────

    def _cargar_clientes(
        self, registros: Iterable[ClienteFuente], bitacora: BitacoraIngesta
    ) -> int:
        """Alta y actualización del catálogo de clientes (hoja `CLIENTES`).

        Es lo que habilita el reporte por vendedor, que hoy no existe en el
        Excel y que el negocio claramente quiere (§3.4).

        Se actualiza campo a campo y solo con lo que viene: un archivo que trae
        el canal pero no el vendedor no debe borrar el vendedor que ya estaba.
        Los problemas de esta hoja se **anotan**, no se cuentan como rechazos:
        son registros de catálogo, no líneas de venta, y mezclarlos descuadraría
        `leidas = aceptadas + rechazadas`.
        """
        existentes = {
            cliente.nit: cliente for cliente in self._sesion.execute(select(Cliente)).scalars()
        }
        vistos: set[str] = set()
        procesados = 0

        for registro in registros:
            nit = normalizar_nit(registro.nit)
            if nit is None:
                bitacora.anotar(
                    registro.fila_origen, "NIT", registro.nit, "Registro de cliente sin NIT."
                )
                continue
            if nit in vistos:
                bitacora.anotar(
                    registro.fila_origen,
                    "NIT",
                    nit,
                    "NIT repetido en el catálogo; manda el último registro del archivo.",
                )
            vistos.add(nit)

            cliente = existentes.get(nit)
            if cliente is None:
                cliente = Cliente(nit=nit, activo=True)
                self._sesion.add(cliente)
                existentes[nit] = cliente

            razon_social = normalizar_texto(registro.razon_social, limite=200)
            canal = normalizar_texto(registro.canal, limite=40)
            vendedor = normalizar_texto(registro.vendedor, limite=120)
            if razon_social is not None:
                cliente.razon_social = razon_social
            if canal is not None:
                cliente.canal = canal.upper()
            if vendedor is not None:
                cliente.vendedor = vendedor
            procesados += 1

        if procesados:
            self._sesion.flush()
        return procesados

    # ── Lectura (operativa) ───────────────────────────────────────────────────

    def listar_corridas(self, limite: int = 50) -> list[CorridaSalida]:
        """Últimas corridas, de la más reciente a la más antigua."""
        corridas = self._sesion.execute(
            select(CorridaIngesta).order_by(CorridaIngesta.cuando.desc()).limit(limite)
        ).scalars()
        autores = {
            fila[0]: fila[1] for fila in self._sesion.execute(select(Usuario.id, Usuario.usuario))
        }
        return [
            CorridaSalida(
                id=c.id,
                cuando=c.cuando,
                quien=autores.get(c.usuario_id),
                fuente=c.fuente,
                desde=c.desde,
                hasta=c.hasta,
                estado=c.estado,
                filas_leidas=c.filas_leidas,
                aceptadas=c.aceptadas,
                rechazadas=c.rechazadas,
                duracion_ms=c.duracion_ms,
            )
            for c in corridas
        ]

    def rechazos(self, corrida_id: int) -> list[RechazoSalida]:
        """Filas rechazadas de una corrida, con su motivo."""
        corrida = self._sesion.get(CorridaIngesta, corrida_id)
        if corrida is None:
            raise ErrorNoEncontrado(f"No existe la corrida {corrida_id}.")

        rechazos = self._sesion.execute(
            select(RechazoIngesta)
            .where(RechazoIngesta.corrida_id == corrida_id)
            .order_by(RechazoIngesta.fila)
        ).scalars()
        return [
            RechazoSalida(fila=r.fila, campo=r.campo, valor=r.valor, motivo=r.motivo)
            for r in rechazos
        ]

    def ultima_corrida(self) -> CorridaIngesta | None:
        """La corrida más reciente. Alimenta `GET /salud`."""
        return self._sesion.execute(
            select(CorridaIngesta).order_by(CorridaIngesta.cuando.desc()).limit(1)
        ).scalar_one_or_none()

    # ── Interno ───────────────────────────────────────────────────────────────

    @staticmethod
    def _a_salida(corrida: CorridaIngesta, usuario: Usuario | None) -> CorridaSalida:
        return CorridaSalida(
            id=corrida.id,
            cuando=corrida.cuando,
            quien=usuario.usuario if usuario else None,
            fuente=corrida.fuente,
            desde=corrida.desde,
            hasta=corrida.hasta,
            estado=EstadoCorrida(corrida.estado),
            filas_leidas=corrida.filas_leidas,
            aceptadas=corrida.aceptadas,
            rechazadas=corrida.rechazadas,
            duracion_ms=corrida.duracion_ms,
        )
