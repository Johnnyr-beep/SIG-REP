"""Normalización de los campos que entrega SIESA (§3.4).

Todas las funciones de este módulo son **puras**: no tocan la base y no saben
nada de SQLAlchemy. Eso es a propósito, porque cada una de ellas resuelve un
problema real y medido del archivo de SIESA y quiero poder probarlas sueltas,
sin montar un escenario:

- `C.O.` llega **a veces como texto y a veces como número** (`'606'` y `606`
  conviven en el mismo archivo: 1 466 filas de un tipo y 109 del otro). Sin
  normalizar, ALAMEDA 2 aparecería dos veces en el reporte, una de ellas
  huérfana.
- Los NIT llegan con **espacios de relleno a la derecha** (`'900983334      '`).
  Sin `strip()`, el cruce con el catálogo de clientes falla y el reporte por
  vendedor sale vacío sin decir por qué.
- `CLASES DE CLIENTES` viene **corrupta**: 95 907 filas vacías, 109 con un
  nombre de usuario (`johana.muñoz`) y unas cuantas con marcas de tiempo. Solo
  se aceptan valores con forma de clase; el resto entra como `SIN CLASIFICAR`
  y queda registrado.
- `Domicilio` trae 28 filas en blanco. En blanco es `NULL`, no `False`: nadie
  afirmó que esas ventas no fueran a domicilio.
- Los importes se convierten a `Decimal` **desde texto**. Pasar por `float`
  arrastra el error binario, y en un consolidado de veinte mil millones eso es
  un defecto, no un detalle.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

#: Valor con el que entra una clase de cliente que no supera el catálogo (§3.4).
SIN_CLASIFICAR = "SIN CLASIFICAR"

# No existe `CATEGORIA_POR_DEFECTO` y su ausencia es la decisión, no un olvido.
# Hubo una constante `"OTROS"` a la que aterrizaba todo texto de SIESA sin
# mapeo. Se retiró junto con el cajón: una categoría de SIESA sin mapeo ahora
# **rechaza la fila nombrando el texto que no se reconoció** (§3.1, §7). Dar por
# defecto una de las once categorías reales sería peor que el cajón —engordaría
# la venta de RES o de VIVERES con producto que no es— y ninguna es «la
# neutral». Quien eche de menos la red de seguridad tiene
# `POST /catalogos/mapeo-categorias`, que resuelve el caso en un minuto y sin
# despliegue; 200 filas en el informe de rechazos son visibles, 200 filas en la
# categoría equivocada no lo son.

#: Categorías que **existieron en SIGREP y ya no**, con las categorías reales
#: entre las que hay que repartir lo que llevaban.
#:
#: Se conservan aquí porque el sistema tiene que **reconocerlas para poder
#: rechazarlas bien**. La hoja `CUMPLIMIENTO PPTO` del libro que el negocio usa
#: hoy sigue trayendo el renglón `OTROS` con 616 000 000 de un total de
#: 20 000 000 000, y quien la suba merece leer «reparta ese presupuesto entre
#: VIVERES, HUEVOS, QUESO Y LACTEOS y DOMICILIOS» en vez de un
#: «No existe la categoría 'OTROS'» que es cierto y no dice qué hacer.
#:
#: El reparto lo decidió el negocio, no el sistema, y lo decidió así: **a
#: prorrata de la venta real ya cargada, punto de venta por punto de venta**.
#: Esa decisión la ejecuta `PresupuestoService.repartir_categoria_retirada`
#: —invocable por `python -m app.infrastructure.reparto_presupuesto`— y deja en
#: `presupuesto_historial` un motivo que dice de dónde salió cada cifra y que la
#: gerencia tiene que confirmarla por pantalla. El reparto es un **punto de
#: partida**, no una verdad; lo que no era admisible era dejar 616 000 000
#: colgando de una categoría que ya no existe.
#:
#: Este diccionario sigue vivo después del reparto porque el libro que el
#: negocio usa **sigue trayendo el renglón `OTROS`**: la carga masiva lo tiene
#: que reconocer para rechazarlo con un motivo que diga qué hacer.
CATEGORIAS_RETIRADAS: dict[str, tuple[str, ...]] = {
    "OTROS": ("VIVERES", "HUEVOS", "QUESO Y LACTEOS", "DOMICILIOS"),
}

#: Marca con la que la migración `0004` renombró la categoría que retiraba en
#: lugar de borrarla. Se declara aquí, y no solo en la migración, porque el
#: reparto tiene que **encontrar la categoría por el nombre que hoy tiene en la
#: base** —`OTROS (RETIRADA - REUBICAR)`— y saber que sus destinos son los de
#: `OTROS`. Sin esto, quien ejecute el reparto tendría que teclear los cuatro
#: destinos a mano, que es la forma más segura de que un día falte uno.
SUFIJO_RETIRADA = " (RETIRADA - REUBICAR)"

#: Escalas de persistencia, iguales a las de `models/mixins.py`.
ESCALA_DINERO = Decimal("0.01")
ESCALA_KILOS = Decimal("0.001")
ESCALA_PORCENTAJE = Decimal("0.000001")

#: Clases de cliente conocidas hoy, tal cual vienen del ERP.
CLASES_CLIENTE_CONOCIDAS: frozenset[str] = frozenset(
    {
        "001 - EMPLEADOS",
        "002 - CLIENTES NACIONALES",
    }
)

#: El catálogo de clases no es cerrado —cada PDV nuevo trae su propio
#: `CONSUMIDOR FINAL PDV ...`— así que además de la lista de arriba se aceptan
#: las dos **formas** legítimas. La basura medida en el archivo (`johana.muñoz`,
#: `2026-08-03 16:29:02`) no encaja en ninguna de las dos, que es exactamente lo
#: que se necesita: un filtro que deje pasar lo que el negocio sí usa y frene lo
#: que se coló por un formulario mal hecho.
_PATRON_CLASE_CODIFICADA = re.compile(r"^\d{3}\s*-\s*\S.*$")
_PATRON_CLASE_CONSUMIDOR = re.compile(r"^CONSUMIDOR\b.*\bPDV\b.*$", re.IGNORECASE)

_AFIRMATIVOS = frozenset({"SI", "S", "SÍ", "TRUE", "1"})
_NEGATIVOS = frozenset({"NO", "N", "FALSE", "0"})

#: Formatos de fecha admitidos cuando la celda llega como texto. `openpyxl` con
#: `data_only=True` entrega `datetime` en el archivo real; esto cubre el día en
#: que alguien exporte a CSV y lo vuelva a subir.
_FORMATOS_FECHA = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d/%m/%y")

#: Espacios que hay que recortar. Además de los habituales, el no separable
#: (U+00A0) y el de ancho cero (U+200B), que llegan pegados a los textos que
#: alguien pegó desde una página web y que no se ven al mirar la celda. Se
#: escriben escapados justamente porque son invisibles.
_ESPACIOS = " \t\r\n\xa0\u200b"


def normalizar_texto(valor: object, limite: int | None = None) -> str | None:
    """Texto saneado, o `None` si no queda nada.

    Un `' '` de relleno de SIESA está tan vacío como un `None` y se trata igual:
    distinguirlos solo serviría para que media aplicación compruebe `is None` y
    la otra media `== " "`.
    """
    if valor is None:
        return None
    limpio = _a_texto(valor).strip(_ESPACIOS)
    if not limpio:
        return None
    return limpio[:limite] if limite else limpio


def normalizar_centro_operacion(valor: object) -> str | None:
    """C.O. a texto de tres posiciones con ceros a la izquierda.

    `606` (número) y `'606'` (texto) son el mismo punto de venta. Un valor que
    no es numérico se devuelve tal cual, saneado: no existe, la ingesta lo va a
    rechazar y el motivo del rechazo tiene que mostrar lo que venía de verdad.
    """
    crudo = normalizar_texto(valor)
    if crudo is None:
        return None
    if crudo.endswith(".0") and crudo[:-2].isdigit():
        crudo = crudo[:-2]
    return crudo.zfill(3) if crudo.isdigit() else crudo


def normalizar_nit(valor: object, limite: int = 30) -> str | None:
    """NIT sin los espacios de relleno con que lo entrega SIESA.

    El catálogo de clientes trae el NIT como número (`901733567`) y la venta lo
    trae como texto rellenado (`'901733567     '`). Los dos tienen que acabar en
    la misma cadena o el cruce por vendedor no existe.
    """
    crudo = normalizar_texto(valor)
    if crudo is None:
        return None
    if crudo.endswith(".0") and crudo[:-2].isdigit():
        crudo = crudo[:-2]
    return crudo[:limite]


def normalizar_clase_cliente(valor: object) -> str | None:
    """Clase de cliente si supera el catálogo; `None` si no.

    Devolver `None` en vez de `SIN CLASIFICAR` es deliberado: quien llama tiene
    que decidir qué hacer con el valor descartado —registrarlo en la bitácora—
    y una función que ya hubiera puesto la etiqueta se lo pondría fácil para
    olvidarlo.
    """
    crudo = normalizar_texto(valor, limite=60)
    if crudo is None:
        return None
    if crudo in CLASES_CLIENTE_CONOCIDAS:
        return crudo
    if _PATRON_CLASE_CODIFICADA.match(crudo) or _PATRON_CLASE_CONSUMIDOR.match(crudo):
        return crudo
    return None


def normalizar_domicilio(valor: object) -> bool | None:
    """`Si`/`No` a booleano. En blanco es `NULL`, nunca `False` (§3.4)."""
    crudo = normalizar_texto(valor)
    if crudo is None:
        return None
    normalizado = sin_acentos(crudo).upper()
    if normalizado in _AFIRMATIVOS:
        return True
    if normalizado in _NEGATIVOS:
        return False
    return None


def normalizar_condicion_pago(valor: object) -> str | None:
    """`CON`, `15D`, `30D`… en mayúsculas y acotado a la columna."""
    crudo = normalizar_texto(valor, limite=10)
    return crudo.upper() if crudo else None


def a_decimal(valor: object, escala: Decimal | None = None) -> Decimal | None:
    """Convierte a `Decimal` sin pasar nunca por `float`.

    Se admite el formato colombiano (`1.234.567,89`) porque estos archivos los
    arma el negocio a mano y un punto de miles no debería costar una fila.
    """
    if valor is None:
        return None
    if isinstance(valor, Decimal):
        numero = valor
    else:
        texto = _a_texto(valor).strip(_ESPACIOS).replace("$", "").replace(" ", "")
        if not texto:
            return None
        if "," in texto and "." in texto:
            texto = texto.replace(".", "").replace(",", ".")
        elif "," in texto:
            texto = texto.replace(",", ".")
        try:
            numero = Decimal(texto)
        except (InvalidOperation, ValueError):
            return None
    if not numero.is_finite():
        return None
    return numero.quantize(escala, rounding=ROUND_HALF_UP) if escala is not None else numero


def a_fecha(valor: object) -> date | None:
    """Fecha del día de la venta, o `None` si la celda es ilegible."""
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    crudo = normalizar_texto(valor)
    if crudo is None:
        return None
    for formato in _FORMATOS_FECHA:
        try:
            return datetime.strptime(crudo[:10] if len(crudo) > 10 else crudo, formato).date()
        except ValueError:
            continue
    return None


def nombre_sin_marca_de_retirada(nombre: object) -> str:
    """`'OTROS (RETIRADA - REUBICAR)'` → `'OTROS'`. Lo demás, en mayúsculas.

    La marca la puso la migración `0004` sobre el **nombre**, que es la columna
    única de `categorias`, así que es lo único de lo que se dispone para volver
    al nombre original.
    """
    limpio = (normalizar_texto(nombre) or "").upper()
    if limpio.endswith(SUFIJO_RETIRADA):
        return limpio[: -len(SUFIJO_RETIRADA)].strip()
    return limpio


def destinos_de_categoria_retirada(nombre: object) -> tuple[str, ...] | None:
    """Categorías entre las que se reparte lo que llevaba una categoría retirada.

    Acepta tanto el nombre original (`OTROS`, el que trae el libro del negocio)
    como el marcado (`OTROS (RETIRADA - REUBICAR)`, el que tiene hoy la fila en
    la base). `None` si esa categoría no está retirada.
    """
    return CATEGORIAS_RETIRADAS.get(nombre_sin_marca_de_retirada(nombre))


def sin_acentos(texto: str) -> str:
    """Quita las tildes conservando el resto. Sirve para comparar encabezados."""
    descompuesto = unicodedata.normalize("NFKD", texto)
    return "".join(caracter for caracter in descompuesto if not unicodedata.combining(caracter))


def clave_columna(nombre: object) -> str:
    """Encabezado reducido a una llave comparable.

    `'Razón social cliente POS'` y `'RAZON SOCIAL CLIENTE POS '` son la misma
    columna. `'CATEGORIA'` y `'NUEVA CATEGORIA'` **no**, y por eso la comparación
    es por igualdad exacta de la llave y no por «contiene».
    """
    if nombre is None:
        return ""
    limpio = sin_acentos(_a_texto(nombre)).strip(_ESPACIOS).lower()
    limpio = limpio.replace(".", " ")
    return re.sub(r"\s+", " ", limpio).strip()


def _a_texto(valor: object) -> str:
    """`606.0` → `'606'`; el resto, `str()` a secas."""
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    return str(valor)
