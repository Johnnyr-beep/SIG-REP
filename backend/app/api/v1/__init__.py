"""Routers de la versión 1 de la API. Contrato: `docs/API.md`.

El RBAC se declara **endpoint por endpoint**, nunca por prefijo: un router con
permisos heredados es el sitio donde, tarde o temprano, alguien añade una ruta
que no debía estar abierta y nadie lo nota.

`ADMIN` es superusuario del negocio: aparece en las tres dependencias de abajo
allí donde aparece `GERENTE`, sin excepción. La separación que sí existe va en
el otro sentido y es `AdministracionDep`: administrar cuentas es **solo** de
`ADMIN`, y ni siquiera `GERENTE` entra ahí.
"""

from typing import Annotated

from fastapi import Depends

from app.core.deps import exigir_lectura_general, exigir_roles
from app.domain.enums import Rol
from app.infrastructure.models.usuario import Usuario

#: Cualquiera que haya iniciado sesión puede consultar; JEFE_PDV queda
#: restringido a sus puntos por `alcance_puntos_venta`, no por el rol.
LecturaDep = Annotated[
    Usuario,
    Depends(exigir_lectura_general),
]
#: Parametriza: presupuesto, calendario, mapeo de categorías, ingesta.
AnalistaDep = Annotated[Usuario, Depends(exigir_roles(Rol.ADMIN, Rol.ANALISTA, Rol.GERENTE))]
#: Cierra períodos. Gerencia —y Sistemas, que puede lo mismo que Gerencia.
GerenteDep = Annotated[Usuario, Depends(exigir_roles(Rol.ADMIN, Rol.GERENTE))]
#: Administra cuentas de usuario. **Solo** Sistemas.
#:
#: Es la única dependencia que excluye a GERENTE, y ese es justamente el punto:
#: quien reparte las llaves y quien mira dentro de la caja son cargos
#: distintos. Que ADMIN además vea el negocio no rompe la separación —la
#: rompería que GERENTE pudiera darse a sí mismo el rol que quisiera—.
AdministracionDep = Annotated[Usuario, Depends(exigir_roles(Rol.ADMIN))]
