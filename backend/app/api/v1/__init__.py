"""Routers de la versión 1 de la API. Contrato: `docs/API.md`.

El RBAC se declara **endpoint por endpoint**, nunca por prefijo: un router con
permisos heredados es el sitio donde, tarde o temprano, alguien añade una ruta
que no debía estar abierta y nadie lo nota.
"""

from typing import Annotated

from fastapi import Depends

from app.core.deps import exigir_roles
from app.domain.enums import Rol
from app.infrastructure.models.usuario import Usuario

#: Cualquiera que haya iniciado sesión puede consultar; JEFE_PDV queda
#: restringido a sus puntos por `alcance_puntos_venta`, no por el rol.
LecturaDep = Annotated[
    Usuario, Depends(exigir_roles(Rol.GERENTE, Rol.ANALISTA, Rol.JEFE_PDV, Rol.CONSULTA))
]
#: Parametriza: presupuesto, calendario, mapeo de categorías, ingesta.
AnalistaDep = Annotated[Usuario, Depends(exigir_roles(Rol.ANALISTA, Rol.GERENTE))]
#: Cierra períodos. Solo Gerencia.
GerenteDep = Annotated[Usuario, Depends(exigir_roles(Rol.GERENTE))]
