# Corre en local exactamente lo que corre la integracion continua.
#
#   .\scripts\pruebas-como-ci.ps1              # backend y frontend
#   .\scripts\pruebas-como-ci.ps1 -Backend     # solo backend
#   .\scripts\pruebas-como-ci.ps1 -Frontend    # solo frontend
#
# Gemelo de `pruebas-como-ci.sh` para quien trabaja desde PowerShell. Las dos
# versiones leen el mismo `scripts/entorno-pruebas.env`, que es donde vive la
# unica definicion del entorno de pruebas.
#
# Sin acentos a proposito: Windows PowerShell 5.1 lee los .ps1 sin BOM como ANSI
# y convertiria cada acento en un caracter roto.

[CmdletBinding()]
param(
    [switch]$Backend,
    [switch]$Frontend
)

$ErrorActionPreference = 'Continue'

$raiz = Split-Path -Parent $PSScriptRoot
$hacerBackend  = $true
$hacerFrontend = $true
if ($Backend -and -not $Frontend)  { $hacerFrontend = $false }
if ($Frontend -and -not $Backend)  { $hacerBackend  = $false }

# ---- Paridad de entorno ------------------------------------------------------
#
# Se borra TODA variable SIGREP_* heredada de la sesion antes de cargar las del
# CI. `conftest.py` usa `os.environ.setdefault`, asi que una variable que ya
# venga puesta gana sobre el valor de las pruebas: un SIGREP_DB_URL_OVERRIDE
# apuntando a un archivo .db, o un SIGREP_FUENTE_VENTA=siesa de una prueba
# manual, cambian en silencio lo que se esta verificando.
Get-ChildItem Env: | Where-Object { $_.Name -like 'SIGREP_*' } | ForEach-Object {
    Remove-Item -Path "Env:$($_.Name)" -ErrorAction SilentlyContinue
}

$archivoEntorno = Join-Path $raiz 'scripts\entorno-pruebas.env'
Get-Content -Path $archivoEntorno -Encoding UTF8 | ForEach-Object {
    $linea = $_.Trim()
    if ($linea -and -not $linea.StartsWith('#')) {
        $partes = $linea -split '=', 2
        Set-Item -Path "Env:$($partes[0])" -Value $partes[1]
    }
}

if (Test-Path (Join-Path $raiz 'backend\.env')) {
    Write-Output 'AVISO: existe backend\.env. Pydantic lo lee, pero las variables de'
    Write-Output '       entorno tienen prioridad, asi que no altera esta corrida.'
    Write-Output ''
}

# El entorno virtual del backend, si esta y no hay ninguno activo. El CI instala
# las dependencias en el interprete del runner; en local casi siempre viven aqui.
if (-not $env:VIRTUAL_ENV) {
    $activador = Join-Path $raiz 'backend\.venv\Scripts\Activate.ps1'
    if (Test-Path $activador) {
        . $activador
        Write-Output "Entorno virtual activado: $env:VIRTUAL_ENV"
        Write-Output ''
    }
}

$fallos = 0
$resumen = @()

# Corre un comando, informa el resultado y sigue. El CI se detiene en el primer
# paso rojo; aqui interesa la lista completa para no descubrir los errores de
# uno en uno. El veredicto final es el mismo.
function Invoke-Paso {
    param([string]$Etiqueta, [string]$Programa, [string[]]$Argumentos, [string]$Directorio)

    Write-Output ''
    Write-Output "-- $Etiqueta"
    Push-Location $Directorio
    & $Programa @Argumentos
    $codigo = $LASTEXITCODE
    Pop-Location

    if ($codigo -eq 0) {
        $script:resumen += "  OK    $Etiqueta"
    } else {
        $script:resumen += "  FALLA $Etiqueta"
        $script:fallos++
    }
}

$dirBackend  = Join-Path $raiz 'backend'
$dirFrontend = Join-Path $raiz 'frontend'

if ($hacerBackend) {
    Invoke-Paso 'Formato (ruff format --check)' 'ruff'   @('format', '--check', 'app', 'tests') $dirBackend
    Invoke-Paso 'Lint (ruff check)'             'ruff'   @('check', 'app', 'tests')             $dirBackend
    Invoke-Paso 'Tipos (mypy)'                  'mypy'   @('app')                               $dirBackend
    Invoke-Paso 'Pruebas'                       'pytest' @('--cov=app', '--cov-report=term')    $dirBackend
}

if ($hacerFrontend) {
    Invoke-Paso 'Frontend - tipos'    'npm' @('run', 'typecheck') $dirFrontend
    Invoke-Paso 'Frontend - compilar' 'npm' @('run', 'build')     $dirFrontend
}

# `alembic upgrade head` y `alembic check` no estan aqui a proposito: el CI los
# corre contra un PostgreSQL efimero levantado por el propio runner. Reproducirlo
# en local es `docker compose up -d postgres` y apuntar SIGREP_DB_URL_OVERRIDE a
# esa base; verificarlos contra SQLite no probaria lo mismo.

Write-Output ''
Write-Output '-- Resumen'
$resumen | ForEach-Object { Write-Output $_ }

if ($fallos -gt 0) {
    Write-Output ''
    Write-Output "$fallos paso(s) en rojo. Esto mismo pondria el CI en rojo."
    exit 1
}

Write-Output ''
Write-Output 'Todo en verde con el entorno del CI.'
