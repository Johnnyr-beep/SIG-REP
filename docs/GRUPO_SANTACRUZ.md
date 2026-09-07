# Instancia Corporativa Grupo Santacruz

## Propósito

La instancia `grupo-santacruz` es el tablero financiero corporativo para los
seis negocios del grupo. Es una instancia independiente de Carnes Santacruz,
Agropecuaria y Carnes Frías: no consulta sus tablas operativas ni reutiliza sus
credenciales de base de datos.

## Base de datos

Nombre recomendado: `sigrep_grupo_santacruz`.

En Dokploy se debe crear un servicio PostgreSQL gestionado y una base con ese
nombre. La conexión se registra exclusivamente en el servicio corporativo:

```text
SIGREP_UNIDAD=grupo-santacruz
SIGREP_DB_URL_GRUPO_SANTACRUZ=postgres://USUARIO:CLAVE@HOST:5432/sigrep_grupo_santacruz
```

`SIGREP_DB_URL_OVERRIDE` no debe apuntar a una base de negocio. La aplicación
se niega a resolver la sesión corporativa si falta
`SIGREP_DB_URL_GRUPO_SANTACRUZ`.

Una vez provisionada la base, el contenedor ejecuta `alembic upgrade head` al
arrancar. Como verificación manual:

```powershell
Set-Location backend
$env:SIGREP_UNIDAD = "grupo-santacruz"
$env:SIGREP_DB_URL_GRUPO_SANTACRUZ = "postgres://USUARIO:CLAVE@HOST:5432/sigrep_grupo_santacruz"
alembic upgrade head
alembic check
```

## Alcance funcional

La primera capa consolida estos negocios:

1. Agropecuaria Santacruz, planta de beneficio.
2. Carnes Santacruz, Serueda y Cristian Serrano, retail cárnico.
3. Inversiones Serrano Millán, procesamiento de carnes frías.
4. Asaderos Santacruz, restaurantes.
5. Agroporcícola, granja.
6. Transantacruz, transporte.

La segunda capa organiza los indicadores en: Planeación y Presupuestos,
Gestión de Ingresos y Rentabilidad, Gestión de Costos y Gastos, Gestión de
Capital de Trabajo, Tesorería y Liquidez, Contabilidad y EEFF, y Control
Financiero y Gestión de la Información.

La tercera capa muestra un tablero por proceso. El inicio corporativo consolida
valor agregado, rentabilidad, crecimiento y liquidez, además del comparativo
por negocio, la evolución, generación de caja y alertas.

## Contrato de datos

La fuente de verdad de los indicadores corporativos es la contabilidad
aprobada. Las ventas de SIGREP pueden usarse para conciliación comercial, no
para sustituir los estados financieros.

Para cada negocio y período se requiere como mínimo: ingresos netos, EBIT,
impuesto operativo, utilidad neta, activos totales de apertura y cierre,
activos corrientes, pasivos corrientes, capital empleado, WACC y escenarios
`real`, `presupuesto` y `forecast` cuando apliquen.

No se deben publicar ceros como sustituto de datos faltantes. Cada indicador
debe exponer su fecha de corte, fuente, estado de conciliación y condición de
disponibilidad.

## Siguiente implementación

La provisión de esta base habilita la fundación técnica, pero no calcula aún
indicadores financieros. El siguiente cambio debe crear el modelo financiero
corporativo: unidades de negocio, procesos, métricas, mapeo contable, hechos
mensuales y corridas de carga. Solo después se construyen la ingesta, fórmulas,
API y tablero consolidado.