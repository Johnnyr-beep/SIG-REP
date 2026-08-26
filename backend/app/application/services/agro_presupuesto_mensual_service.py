"""Presupuesto mensual configurable de la unidad Agropecuaria.

── La diferencia con `agro_presupuesto_service` ──────────────────────────────

El presupuesto por dimensiones (`agro_presupuesto_service`) es **una meta
descompuesta en cuatro vistas** que no se suman. Este servicio es **cuatro
metas independientes** que **sí se suman**: comercial, agro distribución,
servicio y nacional son bloques distintos y el total mensual es la suma de los
cuatro.

No se toca `agro_presupuesto_service` ni sus tablas. Este módulo tiene sus
propias tablas (`agro_ppto_mensual_*`) y sus propias rutas
(`/agro/presupuesto-mensual`).

── Bloques y su lógica de captura ─────────────────────────────────────────────

- **commercial**: presupuestos por vendedor con categoría A–F. Cada vendedor
  tiene una categoría asignada en función de sus clientes. Las filas de detalle
  llevan vendedor, cliente y categoría.
- **agro_distribucion**: los clientes pertenecen al vendedor `AGROPECUARIA`.
  Las filas de detalle llevan vendedor fijo y cliente variable.
- **nacional**: los clientes pertenecen a Juan Sierra, incluido Éxito. Las
  filas de detalle llevan vendedor fijo y cliente variable.
- **servicio**: un solo valor mensual. No se descompone. Vive en su propia
  tabla y su propio endpoint.

── Reglas compartidas con el presupuesto por dimensiones ────────────────────

- El bloqueo por período cerrado (§7): un período cerrado no admite cambios.
- El versionado con autor: `actualizado_por_id` queda registrado en cada fila.
- Las claves se normalizan con `normalizar_clave` para que crucen con la venta.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.services.agro_importacion_comercial_parser import (
    leer_canales,
    normalizar_canal,
)
from app.application.services.periodos import obtener_o_crear_periodo, obtener_periodo
from app.core.errors import ErrorNoEncontrado, ErrorPeriodoCerrado, ErrorValidacion
from app.core.logging import obtener_logger
from app.infrastructure.models.agro_presupuesto_mensual import (
    BLOQUES_PRESUPUESTO_MENSUAL,
    AgroPptoMensualCanalMapeo,
    AgroPptoMensualDetalle,
    AgroPptoMensualMapeo,
    AgroPptoMensualServicio,
)
from app.infrastructure.models.agro_vocabulario import (
    TipoDimension,
    normalizar_clave,
    normalizar_etiqueta,
)
from app.infrastructure.models.periodo import Periodo
from app.infrastructure.models.usuario import Usuario
from app.schemas.agro import (
    BloqueMensualSalida,
    CanalMapeoMensualEntrada,
    CanalMapeoMensualSalida,
    DetalleMensualEntrada,
    DetalleMensualSalida,
    FilaImportacionComercial,
    MapeoMensualEntrada,
    MapeoMensualSalida,
    ResultadoImportacionComercial,
    ResumenPresupuestoMensualSalida,
    ServicioMensualEntrada,
    ServicioMensualSalida,
)

logger = obtener_logger(__name__)

CERO = Decimal("0")

#: Vendedor fijo del bloque agro distribución.
VENDEDOR_AGRO_DISTRIBUCION = "AGROPECUARIA"

#: Vendedor fijo del bloque nacional (Juan Sierra, incluido Éxito).
VENDEDOR_NACIONAL = "JUAN SIERRA"

#: Bloques que se capturan como filas de detalle (no servicio).
BLOQUES_DETALLE: frozenset[str] = frozenset({"commercial", "agro_distribucion", "nacional"})

#: Etiquetas legibles de los bloques, para la salida.
_ETIQUETAS_BLOQUE: dict[str, str] = {
    "commercial": "Comercial",
    "agro_distribucion": "Agro Distribución",
    "servicio": "Servicio",
    "nacional": "Nacional",
}


class AgroPresupuestoMensualService:
    """Casos de uso del presupuesto mensual configurable."""

    def __init__(self, sesion: Session) -> None:
        self._sesion = sesion

    # ── Resumen ───────────────────────────────────────────────────────────────

    def resumen(self, codigo_periodo: str) -> ResumenPresupuestoMensualSalida:
        """El presupuesto mensual completo: los cuatro bloques y el total.

        El total **es la suma de los cuatro bloques**, porque cada bloque es una
        meta independiente. Esto es lo opuesto al presupuesto por dimensiones,
        donde las cuatro descomposiciones describen el mismo dinero y no se suman.
        """
        periodo = obtener_periodo(self._sesion, codigo_periodo)

        bloques: list[BloqueMensualSalida] = []
        total_monto = CERO
        total_kilos = CERO

        for bloque in BLOQUES_PRESUPUESTO_MENSUAL:
            if bloque == "servicio":
                fila_servicio = self._fila_servicio(periodo)
                monto = Decimal(fila_servicio.monto) if fila_servicio else CERO
                kilos = Decimal(fila_servicio.kilos) if fila_servicio else CERO
                bloques.append(
                    BloqueMensualSalida(
                        bloque=bloque,
                        total_monto=monto,
                        total_kilos=kilos,
                        filas=[],
                    )
                )
            else:
                filas = self._filas_detalle(periodo, bloque)
                monto = sum((Decimal(f.monto) for f in filas), start=CERO)
                kilos = sum((Decimal(f.kilos) for f in filas), start=CERO)
                bloques.append(
                    BloqueMensualSalida(
                        bloque=bloque,
                        total_monto=monto,
                        total_kilos=kilos,
                        filas=[self._detalle_a_salida(f) for f in filas],
                    )
                )
            total_monto += monto
            total_kilos += kilos

        return ResumenPresupuestoMensualSalida(
            periodo=periodo.codigo,
            bloques=bloques,
            total_monto=total_monto,
            total_kilos=total_kilos,
        )

    # ── Mapeo de asignaciones ─────────────────────────────────────────────────

    def listar_mapeos(self, bloque: str | None = None) -> list[MapeoMensualSalida]:
        """Lista las asignaciones configuradas, opcionalmente filtradas por bloque."""
        self._validar_bloque(bloque) if bloque else None
        consulta = select(AgroPptoMensualMapeo).order_by(
            AgroPptoMensualMapeo.bloque,
            AgroPptoMensualMapeo.vendedor_clave,
            AgroPptoMensualMapeo.cliente_clave,
        )
        if bloque is not None:
            consulta = consulta.where(AgroPptoMensualMapeo.bloque == bloque)
        return [
            MapeoMensualSalida(
                id=m.id,
                bloque=m.bloque,
                vendedor_clave=m.vendedor_clave,
                cliente_clave=m.cliente_clave,
                categoria=m.categoria,
                activo=m.activo,
            )
            for m in self._sesion.execute(consulta).scalars()
        ]

    def guardar_mapeo(
        self,
        datos: MapeoMensualEntrada,
        *,
        mapeo_id: int | None = None,
    ) -> MapeoMensualSalida:
        """Crea o actualiza una asignación de bloque.

        Si `mapeo_id` es `None` crea una nueva; si existe, la actualiza. La
        unicidad (bloque, vendedor, cliente, categoría) la garantiza la
        restricción de la tabla y se traduce a 409 por el manejador global.
        """
        self._validar_bloque(datos.bloque)
        self._validar_asignacion_bloque(
            datos.bloque, datos.vendedor_clave, datos.cliente_clave, datos.categoria
        )

        vendedor_norm = self._normalizar_vendedor(datos.vendedor_clave)
        cliente_norm = self._normalizar_cliente(datos.cliente_clave)

        if mapeo_id is not None:
            mapeo = self._sesion.get(AgroPptoMensualMapeo, mapeo_id)
            if mapeo is None:
                raise ErrorNoEncontrado(f"No existe la asignación {mapeo_id}.")
            mapeo.bloque = datos.bloque
            mapeo.vendedor_clave = vendedor_norm
            mapeo.cliente_clave = cliente_norm
            mapeo.categoria = datos.categoria
            mapeo.activo = datos.activo
        else:
            mapeo = AgroPptoMensualMapeo(
                bloque=datos.bloque,
                vendedor_clave=vendedor_norm,
                cliente_clave=cliente_norm,
                categoria=datos.categoria,
                activo=datos.activo,
            )
            self._sesion.add(mapeo)

        self._sesion.flush()
        logger.info(
            "agro_ppto_mensual_mapeo_guardado",
            bloque=mapeo.bloque,
            vendedor=mapeo.vendedor_clave,
            cliente=mapeo.cliente_clave,
        )
        return MapeoMensualSalida(
            id=mapeo.id,
            bloque=mapeo.bloque,
            vendedor_clave=mapeo.vendedor_clave,
            cliente_clave=mapeo.cliente_clave,
            categoria=mapeo.categoria,
            activo=mapeo.activo,
        )

    # ── Detalle por bloque ─────────────────────────────────────────────────────

    def guardar_detalle(
        self,
        codigo_periodo: str,
        datos: DetalleMensualEntrada,
        *,
        usuario: Usuario | None = None,
    ) -> DetalleMensualSalida:
        """Crea o actualiza una fila de presupuesto mensual de un bloque de detalle.

        Los bloques `agro_distribucion` y `nacional` tienen vendedor fijo:
        `AGROPECUARIA` y `JUAN SIERRA` respectivamente. Si la petición no lo
        envía, se fija automáticamente; si lo envía con otro valor, se valida
        y se rechaza.
        """
        self._validar_bloque_detalle(datos.bloque)

        periodo = obtener_o_crear_periodo(self._sesion, codigo_periodo)
        self._exigir_periodo_abierto(periodo)

        vendedor_clave = self._resolver_vendedor(datos.bloque, datos.vendedor_clave)
        cliente_clave = self._normalizar_cliente(datos.cliente_clave)
        categoria = datos.categoria.upper() if datos.categoria else None

        self._validar_categoria_bloque(datos.bloque, categoria)

        fila = self._sesion.execute(
            select(AgroPptoMensualDetalle).where(
                AgroPptoMensualDetalle.periodo_id == periodo.id,
                AgroPptoMensualDetalle.bloque == datos.bloque,
                AgroPptoMensualDetalle.cliente_clave == cliente_clave,
                AgroPptoMensualDetalle.vendedor_clave == vendedor_clave,
                AgroPptoMensualDetalle.categoria == categoria,
            )
        ).scalar_one_or_none()

        if fila is None:
            fila = AgroPptoMensualDetalle(
                periodo_id=periodo.id,
                bloque=datos.bloque,
                cliente_clave=cliente_clave,
                vendedor_clave=vendedor_clave,
                categoria=categoria,
                monto=datos.monto,
                kilos=datos.kilos,
            )
            self._sesion.add(fila)
        else:
            fila.monto = datos.monto
            fila.kilos = datos.kilos

        nueva_cliente_etq = normalizar_etiqueta(datos.cliente_etiqueta)
        if nueva_cliente_etq is not None:
            fila.cliente_etiqueta = nueva_cliente_etq
        nueva_vendedor_etq = normalizar_etiqueta(datos.vendedor_etiqueta)
        if nueva_vendedor_etq is not None:
            fila.vendedor_etiqueta = nueva_vendedor_etq
        fila.actualizado_por_id = usuario.id if usuario else None
        self._sesion.flush()

        logger.info(
            "agro_ppto_mensual_detalle_guardado",
            periodo=periodo.codigo,
            bloque=datos.bloque,
            vendedor=vendedor_clave,
            cliente=cliente_clave,
        )
        return self._detalle_a_salida(fila)

    # ── Servicio ──────────────────────────────────────────────────────────────

    def obtener_servicio(self, codigo_periodo: str) -> ServicioMensualSalida:
        """Lee el presupuesto mensual del bloque de servicio."""
        periodo = obtener_periodo(self._sesion, codigo_periodo)
        fila = self._fila_servicio(periodo)
        if fila is None:
            return ServicioMensualSalida(monto=CERO, kilos=CERO)
        return ServicioMensualSalida(monto=Decimal(fila.monto), kilos=Decimal(fila.kilos))

    def guardar_servicio(
        self,
        codigo_periodo: str,
        datos: ServicioMensualEntrada,
        *,
        usuario: Usuario | None = None,
    ) -> ServicioMensualSalida:
        """Fija el presupuesto mensual del bloque de servicio.

        Es un solo valor por período: no se descompone por vendedor ni por
        cliente. La restricción de unicidad por período lo garantiza.
        """
        periodo = obtener_o_crear_periodo(self._sesion, codigo_periodo)
        self._exigir_periodo_abierto(periodo)

        fila = self._fila_servicio(periodo)
        if fila is None:
            fila = AgroPptoMensualServicio(
                periodo_id=periodo.id,
                monto=datos.monto,
                kilos=datos.kilos,
            )
            self._sesion.add(fila)
        else:
            fila.monto = datos.monto
            fila.kilos = datos.kilos

        fila.actualizado_por_id = usuario.id if usuario else None
        self._sesion.flush()

        logger.info(
            "agro_ppto_mensual_servicio_guardado",
            periodo=periodo.codigo,
            monto=datos.monto,
        )
        return ServicioMensualSalida(monto=Decimal(fila.monto), kilos=Decimal(fila.kilos))

    # ── Interno: validaciones ──────────────────────────────────────────────────

    @staticmethod
    def _validar_bloque(bloque: str) -> None:
        if bloque not in BLOQUES_PRESUPUESTO_MENSUAL:
            raise ErrorValidacion(
                f"Bloque inválido: {bloque!r}. Opciones: {', '.join(BLOQUES_PRESUPUESTO_MENSUAL)}."
            )

    @staticmethod
    def _validar_bloque_detalle(bloque: str) -> None:
        """El bloque de servicio no se captura por detalle."""
        if bloque not in BLOQUES_DETALLE:
            raise ErrorValidacion(
                f"El bloque {bloque!r} no admite filas de detalle. Use el endpoint "
                "de servicio para el bloque de servicio."
            )

    @staticmethod
    def _validar_asignacion_bloque(
        bloque: str,
        vendedor_clave: str | None,
        cliente_clave: str | None,
        categoria: str | None,
    ) -> None:
        """Valida que la asignación tenga sentido para el bloque.

        - `servicio`: no lleva vendedor, cliente ni categoría.
        - `commercial`: la categoría es obligatoria.
        - `agro_distribucion` y `nacional`: no llevan categoría.
        """
        if bloque == "servicio":
            if vendedor_clave or cliente_clave or categoria:
                raise ErrorValidacion(
                    "El bloque de servicio no admite vendedor, cliente ni categoría: "
                    "es un solo valor mensual."
                )
        elif bloque == "commercial":
            if categoria is None:
                raise ErrorValidacion("El bloque comercial requiere una categoría (A–F).")
        else:
            if categoria is not None:
                raise ErrorValidacion(
                    f"El bloque {bloque!r} no admite categoría: solo el bloque "
                    "comercial usa categorías A–F."
                )

    @staticmethod
    def _validar_categoria_bloque(bloque: str, categoria: str | None) -> None:
        """En el detalle, la categoría solo aplica al bloque comercial."""
        if bloque == "commercial" and categoria is None:
            raise ErrorValidacion("El bloque comercial requiere una categoría (A–F) en cada fila.")
        if bloque != "commercial" and categoria is not None:
            raise ErrorValidacion(
                f"El bloque {bloque!r} no admite categoría: solo el bloque "
                "comercial usa categorías A–F."
            )

    @staticmethod
    def _resolver_vendedor(bloque: str, vendedor_clave: str | None) -> str | None:
        """Fija el vendedor de los bloques con vendedor fijo.

        - `agro_distribucion`: vendedor `AGROPECUARIA`.
        - `nacional`: vendedor `JUAN SIERRA`.
        - `commercial`: el vendedor lo envía la petición; es obligatorio.
        """
        if bloque == "agro_distribucion":
            return VENDEDOR_AGRO_DISTRIBUCION
        if bloque == "nacional":
            return VENDEDOR_NACIONAL
        if bloque == "commercial":
            if vendedor_clave is None:
                raise ErrorValidacion("El bloque comercial requiere un vendedor en cada fila.")
            return normalizar_clave(TipoDimension.VENDEDOR, vendedor_clave)
        return vendedor_clave

    @staticmethod
    def _normalizar_vendedor(vendedor_clave: str | None) -> str | None:
        if vendedor_clave is None:
            return None
        return normalizar_clave(TipoDimension.VENDEDOR, vendedor_clave)

    @staticmethod
    def _normalizar_cliente(cliente_clave: str | None) -> str | None:
        if cliente_clave is None:
            return None
        return normalizar_clave(TipoDimension.CLIENTE, cliente_clave)

    @staticmethod
    def _exigir_periodo_abierto(periodo: Periodo) -> None:
        """§7: un período cerrado no admite cambios de presupuesto."""
        if periodo.cerrado:
            raise ErrorPeriodoCerrado(
                f"El período {periodo.codigo} está cerrado y no admite cambios de "
                "presupuesto mensual."
            )

    # ── Interno: consultas ─────────────────────────────────────────────────────

    def _filas_detalle(self, periodo: Periodo, bloque: str) -> Sequence[AgroPptoMensualDetalle]:
        return list(
            self._sesion.execute(
                select(AgroPptoMensualDetalle)
                .where(
                    AgroPptoMensualDetalle.periodo_id == periodo.id,
                    AgroPptoMensualDetalle.bloque == bloque,
                )
                .order_by(
                    AgroPptoMensualDetalle.vendedor_clave,
                    AgroPptoMensualDetalle.cliente_clave,
                    AgroPptoMensualDetalle.categoria,
                )
            ).scalars()
        )

    def _fila_servicio(self, periodo: Periodo) -> AgroPptoMensualServicio | None:
        return self._sesion.execute(
            select(AgroPptoMensualServicio).where(AgroPptoMensualServicio.periodo_id == periodo.id)
        ).scalar_one_or_none()

    @staticmethod
    def _detalle_a_salida(fila: AgroPptoMensualDetalle) -> DetalleMensualSalida:
        return DetalleMensualSalida(
            id=fila.id,
            bloque=fila.bloque,
            cliente_clave=fila.cliente_clave,
            vendedor_clave=fila.vendedor_clave,
            categoria=fila.categoria,
            cliente_etiqueta=fila.cliente_etiqueta,
            vendedor_etiqueta=fila.vendedor_etiqueta,
            monto=Decimal(fila.monto),
            kilos=Decimal(fila.kilos),
        )

    # ── Mapeo de canales del Excel ────────────────────────────────────────────

    def listar_canales_mapeos(self) -> list[CanalMapeoMensualSalida]:
        """Lista los mapeos de canal del Excel → vendedor / cliente / categoría."""
        consulta = select(AgroPptoMensualCanalMapeo).order_by(AgroPptoMensualCanalMapeo.canal)
        return [
            CanalMapeoMensualSalida(
                id=m.id,
                canal=m.canal,
                vendedor_clave=m.vendedor_clave,
                cliente_clave=m.cliente_clave,
                categoria=m.categoria,
                activo=m.activo,
            )
            for m in self._sesion.execute(consulta).scalars()
        ]

    def guardar_canal_mapeo(
        self,
        datos: CanalMapeoMensualEntrada,
        *,
        mapeo_id: int | None = None,
    ) -> CanalMapeoMensualSalida:
        """Crea o actualiza un mapeo de canal del Excel.

        El canal se normaliza (mayúsculas, sin tildes, espacios colapsados) y
        es único: la restricción de la tabla lo garantiza y se traduce a 409 por
        el manejador global. Los tres campos —vendedor, cliente y categoría—
        son obligatorios, porque la importación escribe filas del bloque
        comercial y ese bloque los exige.
        """
        canal = normalizar_canal(datos.canal)
        if not canal:
            raise ErrorValidacion("El canal no puede estar vacío.")

        vendedor_norm = normalizar_clave(TipoDimension.VENDEDOR, datos.vendedor_clave)
        cliente_norm = normalizar_clave(TipoDimension.CLIENTE, datos.cliente_clave)
        categoria = datos.categoria.upper()

        if mapeo_id is not None:
            mapeo = self._sesion.get(AgroPptoMensualCanalMapeo, mapeo_id)
            if mapeo is None:
                raise ErrorNoEncontrado(f"No existe el mapeo de canal {mapeo_id}.")
            mapeo.canal = canal
            mapeo.vendedor_clave = vendedor_norm
            mapeo.cliente_clave = cliente_norm
            mapeo.categoria = categoria
            mapeo.activo = datos.activo
        else:
            mapeo = AgroPptoMensualCanalMapeo(
                canal=canal,
                vendedor_clave=vendedor_norm,
                cliente_clave=cliente_norm,
                categoria=categoria,
                activo=datos.activo,
            )
            self._sesion.add(mapeo)

        self._sesion.flush()
        logger.info(
            "agro_ppto_mensual_canal_mapeo_guardado",
            canal=mapeo.canal,
            vendedor=mapeo.vendedor_clave,
            cliente=mapeo.cliente_clave,
        )
        return CanalMapeoMensualSalida(
            id=mapeo.id,
            canal=mapeo.canal,
            vendedor_clave=mapeo.vendedor_clave,
            cliente_clave=mapeo.cliente_clave,
            categoria=mapeo.categoria,
            activo=mapeo.activo,
        )

    # ── Importación del Excel comercial ───────────────────────────────────────

    def importar_comercial(
        self,
        contenido: bytes,
        nombre_archivo: str,
        codigo_periodo: str,
        motivo: str,
        *,
        usuario: Usuario | None = None,
    ) -> ResultadoImportacionComercial:
        """Importa el libro anual al bloque **commercial** del período.

        Lee la hoja `RESUMEN (MES)`, toma el valor del mes del período **tal
        cual está almacenado** (sin escalar por 1 000) y, por cada canal del
        Excel, lo vuelca en una fila de detalle del bloque comercial usando el
        mapeo configurado. Los canales sin mapeo se rechazan con su motivo: no
        se adivina un destino.

        Una fila mala no aborta las buenas: cada canal se procesa por su cuenta
        y el resultado publica aceptados y rechazados. El total es la suma de
        las filas aceptadas, no la del libro: lo que se rechazó no entra al
        presupuesto.
        """
        periodo = obtener_o_crear_periodo(self._sesion, codigo_periodo)
        self._exigir_periodo_abierto(periodo)

        canales = leer_canales(contenido, codigo_periodo)

        mapeos: dict[str, AgroPptoMensualCanalMapeo] = {
            m.canal: m
            for m in self._sesion.execute(
                select(AgroPptoMensualCanalMapeo).where(AgroPptoMensualCanalMapeo.activo.is_(True))
            ).scalars()
        }

        filas: list[FilaImportacionComercial] = []
        aceptadas = 0
        rechazadas = 0
        total_monto = CERO
        total_kilos = CERO

        for canal_leido in canales:
            canal_norm = normalizar_canal(canal_leido.canal)
            mapeo = mapeos.get(canal_norm)

            if mapeo is None:
                filas.append(
                    FilaImportacionComercial(
                        canal=canal_leido.canal,
                        monto=canal_leido.monto,
                        kilos=CERO,
                        aceptada=False,
                        motivo=(
                            f"El canal «{canal_leido.canal}» no tiene mapeo "
                            "configurado. Créelo en la configuración de canales "
                            "y vuelva a importar."
                        ),
                    )
                )
                rechazadas += 1
                continue

            if not mapeo.vendedor_clave or not mapeo.cliente_clave or not mapeo.categoria:
                filas.append(
                    FilaImportacionComercial(
                        canal=canal_leido.canal,
                        vendedor_clave=mapeo.vendedor_clave,
                        cliente_clave=mapeo.cliente_clave,
                        categoria=mapeo.categoria,
                        monto=canal_leido.monto,
                        kilos=CERO,
                        aceptada=False,
                        motivo=(
                            f"El mapeo del canal «{canal_leido.canal}» está "
                            "incompleto: requiere vendedor, cliente y categoría."
                        ),
                    )
                )
                rechazadas += 1
                continue

            datos = DetalleMensualEntrada(
                bloque="commercial",
                vendedor_clave=mapeo.vendedor_clave,
                cliente_clave=mapeo.cliente_clave,
                categoria=mapeo.categoria,
                monto=canal_leido.monto,
                kilos=CERO,
            )
            self.guardar_detalle(codigo_periodo, datos, usuario=usuario)

            filas.append(
                FilaImportacionComercial(
                    canal=canal_leido.canal,
                    vendedor_clave=mapeo.vendedor_clave,
                    cliente_clave=mapeo.cliente_clave,
                    categoria=mapeo.categoria,
                    monto=canal_leido.monto,
                    kilos=CERO,
                    aceptada=True,
                )
            )
            aceptadas += 1
            total_monto += canal_leido.monto
            total_kilos += CERO

        logger.info(
            "agro_importacion_comercial",
            periodo=codigo_periodo,
            archivo=nombre_archivo,
            motivo=motivo,
            aceptadas=aceptadas,
            rechazadas=rechazadas,
            total_monto=total_monto,
        )

        return ResultadoImportacionComercial(
            periodo=codigo_periodo,
            aceptadas=aceptadas,
            rechazadas=rechazadas,
            total_monto=total_monto,
            total_kilos=total_kilos,
            filas=filas,
        )
