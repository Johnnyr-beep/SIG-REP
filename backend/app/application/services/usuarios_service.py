"""Administración de cuentas de usuario. Solo el rol ADMIN llega hasta aquí.

Este servicio existe porque hasta ahora los usuarios se creaban por línea de
órdenes, y una cuenta que solo se puede crear con acceso al servidor es una
cuenta que acaba creándose mal o no creándose.

Las seis reglas que lo gobiernan están implementadas cada una en un sitio
identificable, y no repartidas por los endpoints:

1. `_rechazar_autoadministracion` — nadie se administra a sí mismo.
2. `_exigir_relevo_admin` — siempre queda al menos un ADMIN activo.
3. No hay método de borrado. Se desactiva. Ver la nota de `desactivar`.
4. `_registrar` — toda operación deja rastro en `usuario_auditoria`.
5. `_clave_provisional` — clave de un solo uso con cambio obligatorio.
6. Los esquemas de salida no tienen campo para el hash (`schemas/usuarios.py`).
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import PERMISOS_CONSULTA
from app.core.errors import (
    ErrorAutorizacion,
    ErrorConflicto,
    ErrorNoEncontrado,
    ErrorReglaNegocio,
)
from app.core.logging import obtener_logger
from app.core.security import generar_password_temporal, hashear_password
from app.domain.enums import AccionUsuario, Rol
from app.infrastructure.models.mixins import ahora_utc
from app.infrastructure.models.organizacion import PuntoVenta
from app.infrastructure.models.usuario import (
    Usuario,
    UsuarioAuditoria,
    UsuarioPermiso,
    UsuarioPuntoVenta,
)
from app.schemas.usuarios import (
    AlcanceEntrada,
    AuditoriaSalida,
    PermisoSalida,
    UsuarioModificacion,
    UsuarioNuevo,
    UsuarioSalida,
)

logger = obtener_logger(__name__)

#: Entropía de la clave provisional. `token_urlsafe(18)` devuelve 24
#: caracteres: muy por encima de los 12 que exige la política y fuera del
#: alcance de cualquier ataque por diccionario mientras dura.
ENTROPIA_CLAVE_PROVISIONAL = 18


class UsuariosService:
    """Casos de uso de administración de cuentas.

    Se construye con el **actor** —quién está administrando— y no lo recibe
    método a método a propósito: las dos reglas que hacen seguro este módulo
    (nadie se administra a sí mismo, todo deja rastro) necesitan al actor en
    cada operación, y un parámetro opcional que se olvida en una llamada es una
    regla que deja de aplicarse en un endpoint sin que nadie lo note.
    """

    def __init__(self, sesion: Session, actor: Usuario, ip_origen: str | None = None) -> None:
        self._sesion = sesion
        self._actor = actor
        self._ip = ip_origen

    # ── Consulta ──────────────────────────────────────────────────────────────

    def listar(self, *, rol: Rol | None = None, activo: bool | None = None) -> list[UsuarioSalida]:
        """Todas las cuentas, activas e inactivas.

        Las inactivas se devuelven por defecto y no detrás de un
        `incluir_inactivos=true`: como aquí no se borra nada (regla 3), una
        pantalla que solo listara las activas dejaría a las desactivadas fuera
        de la vista, y volver a activar a alguien es media razón de ser de esta
        pantalla.
        """
        consulta = select(Usuario).order_by(Usuario.usuario)
        if rol is not None:
            consulta = consulta.where(Usuario.rol == rol.value)
        if activo is not None:
            consulta = consulta.where(Usuario.activo.is_(activo))
        return [self._salida(u) for u in self._sesion.execute(consulta).scalars()]

    def auditoria(self, usuario_id: int | None = None, limite: int = 100) -> list[AuditoriaSalida]:
        """Rastro de administración, del más reciente al más antiguo."""
        consulta = select(UsuarioAuditoria).order_by(UsuarioAuditoria.cuando.desc()).limit(limite)
        if usuario_id is not None:
            consulta = consulta.where(UsuarioAuditoria.usuario_id == usuario_id)
        return [
            AuditoriaSalida(
                cuando=fila.cuando,
                accion=AccionUsuario(fila.accion),
                usuario=fila.usuario,
                actor=fila.actor,
                campo=fila.campo,
                valor_anterior=fila.valor_anterior,
                valor_nuevo=fila.valor_nuevo,
                ip_origen=fila.ip_origen,
            )
            for fila in self._sesion.execute(consulta).scalars()
        ]

    # ── Alta ──────────────────────────────────────────────────────────────────

    def crear(self, datos: UsuarioNuevo) -> tuple[UsuarioSalida, str]:
        """Crea la cuenta y devuelve su clave provisional **una sola vez**.

        La clave la genera el servidor y no la elige el administrador: una clave
        que alguien teclea es una clave que alguien recuerda, y la que se le
        pone a un tercero acaba siendo la misma para todos.
        """
        if self._existe_nombre(datos.usuario):
            raise ErrorConflicto(f"Ya existe un usuario con el nombre «{datos.usuario}».")
        if datos.email is not None and self._existe_email(datos.email):
            raise ErrorConflicto(f"Ya existe un usuario con el correo «{datos.email}».")

        clave = self._clave_provisional()
        usuario = Usuario(
            usuario=datos.usuario,
            nombre=datos.nombre.strip(),
            email=datos.email,
            rol=datos.rol.value,
            password_hash=hashear_password(clave),
            debe_cambiar_password=True,
            activo=True,
        )
        self._sesion.add(usuario)
        self._sesion.flush()

        self._registrar(usuario, AccionUsuario.CREAR, campo="rol", nuevo=datos.rol.value)
        if datos.puntos_venta:
            self._fijar_alcance(usuario, datos.puntos_venta)
        self._sesion.flush()

        # El log lleva quién y a quién. **Nunca la clave**: un log se copia a un
        # agregador, se rota a disco y lo lee más gente que la que puede entrar
        # a la cuenta.
        logger.info(
            "usuario_creado", usuario=usuario.usuario, rol=usuario.rol, actor=self._actor.usuario
        )
        return self._salida(usuario), clave

    # ── Modificación ──────────────────────────────────────────────────────────

    def modificar(self, usuario_id: int, datos: UsuarioModificacion) -> UsuarioSalida:
        """Cambia nombre, correo y rol. Lo ausente no se toca."""
        objetivo = self._obtener(usuario_id)
        self._rechazar_autoadministracion(objetivo)

        enviados = datos.model_fields_set

        if "rol" in enviados and datos.rol is not None and datos.rol.value != objetivo.rol:
            self._exigir_relevo_admin(
                objetivo,
                motivo=(
                    f"Degradar a «{objetivo.usuario}» dejaría el sistema sin ningún "
                    "administrador activo."
                ),
            )
            self._registrar(
                objetivo,
                AccionUsuario.MODIFICAR,
                campo="rol",
                anterior=objetivo.rol,
                nuevo=datos.rol.value,
            )
            objetivo.rol = datos.rol.value

        if "nombre" in enviados and datos.nombre is not None:
            nombre = datos.nombre.strip()
            if nombre != objetivo.nombre:
                self._registrar(
                    objetivo,
                    AccionUsuario.MODIFICAR,
                    campo="nombre",
                    anterior=objetivo.nombre,
                    nuevo=nombre,
                )
                objetivo.nombre = nombre

        if "email" in enviados and datos.email != objetivo.email:
            if datos.email is not None and self._existe_email(datos.email, excepto=objetivo.id):
                raise ErrorConflicto(f"Ya existe un usuario con el correo «{datos.email}».")
            self._registrar(
                objetivo,
                AccionUsuario.MODIFICAR,
                campo="email",
                anterior=objetivo.email,
                nuevo=datos.email,
            )
            objetivo.email = datos.email

        self._sesion.flush()
        return self._salida(objetivo)

    def fijar_alcance(self, usuario_id: int, datos: AlcanceEntrada) -> UsuarioSalida:
        """Reemplaza el alcance por punto de venta del usuario."""
        objetivo = self._obtener(usuario_id)
        self._rechazar_autoadministracion(objetivo)
        self._fijar_alcance(objetivo, datos.puntos_venta)
        self._sesion.flush()
        return self._salida(objetivo)

    def asignar_permiso(self, usuario_id: int, codigo: str) -> UsuarioSalida:
        if codigo not in PERMISOS_CONSULTA:
            raise ErrorNoEncontrado(f"No existe el permiso {codigo!r}.")
        objetivo = self._obtener(usuario_id)
        self._rechazar_autoadministracion(objetivo)
        if not objetivo.tiene_permiso(codigo):
            objetivo.permisos.append(UsuarioPermiso(codigo=codigo))
            self._registrar(objetivo, AccionUsuario.ASIGNAR_PERMISO, campo="permiso", nuevo=codigo)
            self._sesion.flush()
        return self._salida(objetivo)

    def listar_permisos(self, usuario_id: int) -> list[PermisoSalida]:
        objetivo = self._obtener(usuario_id)
        return [
            PermisoSalida(usuario_id=objetivo.id, codigo=permiso.codigo)
            for permiso in sorted(objetivo.permisos, key=lambda permiso: permiso.codigo)
        ]

    def retirar_permiso(self, usuario_id: int, codigo: str) -> UsuarioSalida:
        objetivo = self._obtener(usuario_id)
        self._rechazar_autoadministracion(objetivo)
        for permiso in list(objetivo.permisos):
            if permiso.codigo == codigo:
                objetivo.permisos.remove(permiso)
                self._registrar(
                    objetivo, AccionUsuario.RETIRAR_PERMISO, campo="permiso", anterior=codigo
                )
                self._sesion.flush()
                break
        return self._salida(objetivo)

    # ── Estado de la cuenta ───────────────────────────────────────────────────

    def activar(self, usuario_id: int) -> UsuarioSalida:
        """Reactiva la cuenta y le levanta el bloqueo por intentos fallidos.

        Levantar el bloqueo es parte de activar y no un endpoint aparte: quien
        pide que le reactiven la cuenta suele haberla bloqueado intentando
        entrar, y dejarle el contador puesto es reactivarle una cuenta que sigue
        sin dejarle pasar.
        """
        objetivo = self._obtener(usuario_id)
        self._rechazar_autoadministracion(objetivo)

        if not objetivo.activo:
            self._registrar(
                objetivo, AccionUsuario.ACTIVAR, campo="activo", anterior="false", nuevo="true"
            )
        objetivo.activo = True
        objetivo.intentos_fallidos = 0
        objetivo.bloqueado_hasta = None
        self._sesion.flush()
        return self._salida(objetivo)

    def desactivar(self, usuario_id: int) -> UsuarioSalida:
        """Desactiva la cuenta. **No hay borrado, y es deliberado** (§3.3).

        Las acciones de un usuario están referenciadas desde
        `presupuesto_historial` y desde `corridas_ingesta`. Borrar la fila
        rompería esas claves ajenas o —peor, porque son anulables— las dejaría
        en nulo, y el historial pasaría a decir que aquel presupuesto lo cambió
        nadie. El rastro que §3.3 existe para conservar se destruiría para
        ahorrar una fila.
        """
        objetivo = self._obtener(usuario_id)
        self._rechazar_autoadministracion(objetivo)
        self._exigir_relevo_admin(
            objetivo,
            motivo=(
                f"Desactivar a «{objetivo.usuario}» dejaría el sistema sin ningún "
                "administrador activo."
            ),
        )

        if objetivo.activo:
            self._registrar(
                objetivo, AccionUsuario.DESACTIVAR, campo="activo", anterior="true", nuevo="false"
            )
        objetivo.activo = False
        self._sesion.flush()
        logger.info("usuario_desactivado", usuario=objetivo.usuario, actor=self._actor.usuario)
        return self._salida(objetivo)

    def restablecer_clave(self, usuario_id: int) -> tuple[UsuarioSalida, str]:
        """Genera otra clave provisional y fuerza el cambio en el siguiente acceso."""
        objetivo = self._obtener(usuario_id)
        self._rechazar_autoadministracion(objetivo)

        clave = self._clave_provisional()
        objetivo.password_hash = hashear_password(clave)
        objetivo.debe_cambiar_password = True
        # Restablecer sirve, casi siempre, para rescatar a alguien que se quedó
        # fuera. Dejarle el bloqueo puesto es no rescatarlo.
        objetivo.intentos_fallidos = 0
        objetivo.bloqueado_hasta = None

        self._registrar(objetivo, AccionUsuario.RESTABLECER_CLAVE)
        self._sesion.flush()
        logger.info("clave_restablecida", usuario=objetivo.usuario, actor=self._actor.usuario)
        return self._salida(objetivo), clave

    # ── Las reglas ────────────────────────────────────────────────────────────

    def _rechazar_autoadministracion(self, objetivo: Usuario) -> None:
        """Regla 1: nadie se administra a sí mismo.

        Sin esto el rol es una formalidad: cualquiera con ADMIN se concede lo
        que quiera y nadie más se entera. Cubre también el accidente
        —desactivarse uno mismo y quedarse fuera— y es la razón de que alcance
        también a `restablecer_clave`: para la clave propia está
        `POST /auth/cambiar-clave`, que exige conocer la actual.
        """
        if objetivo.id == self._actor.id:
            raise ErrorAutorizacion(
                "Un administrador no puede administrar su propia cuenta. "
                "Pídaselo a otro administrador; para su clave use "
                "«cambiar clave» desde su perfil.",
                detalles={"regla": "sin_autoadministracion"},
            )

    def _exigir_relevo_admin(self, objetivo: Usuario, *, motivo: str) -> None:
        """Regla 2: siempre queda al menos un ADMIN activo.

        Es la protección contra quedarse fuera del sistema sin forma de volver a
        entrar: sin ningún ADMIN no hay quien cree usuarios, y recuperar la
        instalación exige entrar al servidor a correr la semilla.

        Nota honesta sobre su alcance: **mientras la regla 1 se mantenga, esta
        no puede dispararse a través de la API**, porque quien administra es
        siempre un ADMIN activo distinto del objetivo, de modo que él mismo es
        el relevo. Se conserva igualmente como segunda barrera —para el día que
        alguien añada una operación en lote, un endpoint de borrado o relaje la
        regla 1— y se prueba a nivel de servicio, que es donde sí se alcanza.
        Ver `tests/test_usuarios.py::test_la_regla_del_ultimo_admin_bloquea_el_relevo_ausente`.
        """
        if objetivo.rol != Rol.ADMIN.value or not objetivo.activo:
            return
        if self._admins_activos(excepto=objetivo.id) == 0:
            raise ErrorReglaNegocio(
                f"{motivo} Nombre antes a otro administrador y repita la operación.",
                detalles={"regla": "ultimo_admin_activo"},
            )

    def _admins_activos(self, *, excepto: int | None = None) -> int:
        consulta = (
            select(func.count())
            .select_from(Usuario)
            .where(Usuario.rol == Rol.ADMIN.value, Usuario.activo.is_(True))
        )
        if excepto is not None:
            consulta = consulta.where(Usuario.id != excepto)
        return int(self._sesion.execute(consulta).scalar_one())

    def _registrar(
        self,
        objetivo: Usuario,
        accion: AccionUsuario,
        *,
        campo: str | None = None,
        anterior: str | None = None,
        nuevo: str | None = None,
    ) -> None:
        """Regla 4: una fila por campo modificado, como `presupuesto_historial`."""
        self._sesion.add(
            UsuarioAuditoria(
                usuario_id=objetivo.id,
                usuario=objetivo.usuario[:50],
                accion=accion.value,
                campo=campo,
                valor_anterior=anterior[:200] if anterior is not None else None,
                valor_nuevo=nuevo[:200] if nuevo is not None else None,
                actor_id=self._actor.id,
                actor=self._actor.usuario[:50],
                ip_origen=self._ip,
                cuando=ahora_utc(),
            )
        )

    @staticmethod
    def _clave_provisional() -> str:
        """Regla 5: clave de un solo uso.

        No se somete a `validar_fortaleza_clave`, y no es un descuido: esa
        política existe para las claves que **elige una persona**, y aplicarla a
        24 caracteres de `secrets` solo introduciría un fallo aleatorio el día
        que el generador no saque una mayúscula. Quien la recibe está obligado a
        cambiarla por una que sí pasa la política.
        """
        return generar_password_temporal(ENTROPIA_CLAVE_PROVISIONAL)

    # ── Auxiliares ────────────────────────────────────────────────────────────

    def _obtener(self, usuario_id: int) -> Usuario:
        usuario = self._sesion.get(Usuario, usuario_id)
        if usuario is None:
            raise ErrorNoEncontrado(f"No existe el usuario {usuario_id}.")
        return usuario

    def _existe_nombre(self, nombre: str) -> bool:
        fila = self._sesion.execute(
            select(Usuario.id).where(Usuario.usuario == nombre)
        ).scalar_one_or_none()
        return fila is not None

    def _existe_email(self, email: str, *, excepto: int | None = None) -> bool:
        consulta = select(Usuario.id).where(Usuario.email == email)
        if excepto is not None:
            consulta = consulta.where(Usuario.id != excepto)
        return self._sesion.execute(consulta).scalar_one_or_none() is not None

    def _fijar_alcance(self, objetivo: Usuario, codigos: list[str]) -> None:
        """Reemplaza el alcance y deja el conjunto anterior y el nuevo en el rastro."""
        pedidos = sorted(set(codigos))
        puntos: dict[str, int] = {}
        for codigo in pedidos:
            punto = self._sesion.execute(
                select(PuntoVenta).where(PuntoVenta.codigo_co == codigo)
            ).scalar_one_or_none()
            if punto is None:
                raise ErrorNoEncontrado(f"No existe el punto de venta {codigo}.")
            puntos[codigo] = punto.id

        anterior = sorted(a.punto_venta.codigo_co for a in objetivo.alcances)
        if anterior == pedidos:
            return

        for alcance in list(objetivo.alcances):
            if alcance.punto_venta.codigo_co not in puntos:
                objetivo.alcances.remove(alcance)
        ya_tiene = {a.punto_venta.codigo_co for a in objetivo.alcances}
        for codigo, punto_id in puntos.items():
            if codigo not in ya_tiene:
                objetivo.alcances.append(UsuarioPuntoVenta(punto_venta_id=punto_id))

        self._registrar(
            objetivo,
            AccionUsuario.ASIGNAR_ALCANCE,
            campo="alcance",
            anterior=", ".join(anterior) or "(ninguno)",
            nuevo=", ".join(pedidos) or "(ninguno)",
        )
        self._sesion.flush()

    @staticmethod
    def _salida(usuario: Usuario) -> UsuarioSalida:
        """Construye la salida **campo a campo**, nunca desde el modelo entero.

        `EsquemaBase` lleva `from_attributes=True`, así que un
        `UsuarioSalida.model_validate(usuario)` funcionaría; pero entonces
        bastaría con que alguien añadiera un campo al esquema para que el hash
        empezara a viajar. Enumerarlos aquí obliga a escribirlo a mano para que
        se filtre.
        """
        return UsuarioSalida(
            id=usuario.id,
            usuario=usuario.usuario,
            nombre=usuario.nombre,
            email=usuario.email,
            rol=Rol(usuario.rol),
            activo=usuario.activo,
            debe_cambiar_password=usuario.debe_cambiar_password,
            bloqueado=usuario.esta_bloqueado,
            ultimo_acceso=usuario.ultimo_acceso,
            creado_en=usuario.creado_en,
            puntos_venta=sorted(a.punto_venta.codigo_co for a in usuario.alcances),
            permisos=sorted(permiso.codigo for permiso in usuario.permisos),
        )
