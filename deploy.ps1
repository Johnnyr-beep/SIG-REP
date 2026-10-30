param([switch]$SoloLabels)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Set-Location $PSScriptRoot

function Invoke-Native {
    param([string]$Program, [string[]]$Arguments)
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        if ($Program -eq 'ssh') {
            & $Program -n -T @Arguments
        } else {
            & $Program @Arguments
        }
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousPreference
    }
    if ($exitCode -ne 0) { throw "$Program termino con codigo $exitCode" }
}

$secrets = @{}
if (Test-Path (Join-Path $PSScriptRoot '.deploy-secrets')) {
    Get-Content (Join-Path $PSScriptRoot '.deploy-secrets') | ForEach-Object {
        if ($_ -match '^\s*([A-Z_]+)=(.*)$') {
            $secrets[$Matches[1]] = $Matches[2].Trim().Trim('"').Trim("'")
        }
    }
}
foreach ($name in @('SSH_KEY', 'SSH_HOST', 'SERVICE_NAME', 'APP_URL', 'DK_BASE', 'DK_TOKEN', 'APP_ID', 'IMAGE', 'DEPLOY_SOURCE')) {
    if (-not $secrets.ContainsKey($name)) {
        $secrets[$name] = [Environment]::GetEnvironmentVariable($name)
    }
}
$gitProvider = $secrets['DEPLOY_SOURCE'] -ne 'docker'
foreach ($name in @('SSH_KEY', 'SSH_HOST', 'SERVICE_NAME', 'APP_URL')) {
    if ([string]::IsNullOrWhiteSpace($secrets[$name])) { throw "Falta $name en .deploy-secrets" }
}
$sshKey = $secrets['SSH_KEY'] -replace '^/([A-Za-z])/', '$1:/'
if (-not (Test-Path -LiteralPath $sshKey)) { throw 'No se encuentra la clave SSH configurada.' }
$sshHost = $secrets['SSH_HOST']
$service = $secrets['SERVICE_NAME']
$appUrl = $secrets['APP_URL'].TrimEnd('/')
$publicUri = [uri]$appUrl
$domain = $publicUri.DnsSafeHost
if ($publicUri.Scheme -ne 'https' -or $domain -notmatch '^[a-zA-Z0-9.-]+$') {
    throw 'APP_URL debe ser una URL HTTPS valida.'
}
if ($service -notmatch '^[a-zA-Z0-9_-]+$') { throw 'SERVICE_NAME invalido.' }
$sshArgs = @('-i', $sshKey, '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
    '-o', 'ConnectTimeout=15', '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=3')
$remote = '/tmp/sigrep-deploy-' + [guid]::NewGuid().ToString('N')

if (-not $SoloLabels) {
    foreach ($name in @('DK_BASE', 'DK_TOKEN', 'APP_ID')) {
        if ([string]::IsNullOrWhiteSpace($secrets[$name])) { throw "Falta $name en .deploy-secrets" }
    }
    $dirty = @(Invoke-Native -Program git -Arguments @('status', '--porcelain'))
    if ($dirty.Count -gt 0) { throw 'Hay cambios sin commit. Confirma los cambios antes de desplegar.' }
    $commit = (Invoke-Native -Program git -Arguments @('rev-parse', 'HEAD')).Trim()
    if (-not $gitProvider) {
        $image = $secrets['IMAGE']
        if ($image -notmatch '^[a-zA-Z0-9._:/-]+$') { throw 'IMAGE invalida.' }
        $currentImage = (Invoke-Native -Program ssh -Arguments ($sshArgs + @($sshHost,
            "docker service inspect '$service' --format '{{.Spec.TaskTemplate.ContainerSpec.Image}}'"))).Trim()
        if (($currentImage -split '@')[0] -ne $image) {
            throw 'IMAGE debe coincidir con la imagen del servicio y del proveedor Docker de Dokploy.'
        }
    }
    $archive = Join-Path $env:TEMP ("sigrep-$commit.tar.gz")
    try {
        Invoke-Native -Program ssh -Arguments ($sshArgs + @($sshHost, "mkdir -p '$remote'"))
        if ($gitProvider) {
            Write-Host '[1/5] Verificando que el commit este publicado...'
            $branch = (Invoke-Native -Program git -Arguments @('branch', '--show-current')).Trim()
            if (-not $branch) { throw 'El despliegue Git requiere una rama activa.' }
            $remoteHead = Invoke-Native -Program git -Arguments @('ls-remote', 'origin', "refs/heads/$branch")
            if (($remoteHead -split '\s+')[0] -ne $commit) { throw 'Ejecute git push antes del despliegue.' }
            Write-Host '[2/5] Dokploy construira la imagen desde Git.'
        } else {
            Write-Host '[1/5] Empaquetando el commit y subiendo al servidor...'
            Invoke-Native -Program git -Arguments @('archive', '--format=tar.gz', "--output=$archive", 'HEAD')
            Invoke-Native -Program scp -Arguments ($sshArgs + @($archive, "${sshHost}:$remote/source.tar.gz"))
            Write-Host '[2/5] Construyendo y publicando imagen...'
            Invoke-Native -Program ssh -Arguments ($sshArgs + @($sshHost,
                "cd '$remote' && tar xzf source.tar.gz && docker build --build-arg SIGREP_VERSION='$commit' -t '$image' . && docker push '$image'"))
        }
        Write-Host '[3/5] Desplegando con Dokploy...'
        $headers = @{ 'x-api-key' = $secrets['DK_TOKEN'] }
        $base = $secrets['DK_BASE'].TrimEnd('/')
        $body = @{ json = @{ applicationId = $secrets['APP_ID'] } } | ConvertTo-Json -Compress
        $inputQuery = [uri]::EscapeDataString($body)
        $application = (Invoke-RestMethod -Uri "$base/application.one?input=$inputQuery" `
            -Headers $headers -TimeoutSec 20).result.data.json
        if ($application.appName -ne $service) { throw 'APP_ID no corresponde a SERVICE_NAME.' }
        if ($application.applicationStatus -eq 'running') { throw 'Dokploy ya tiene un despliegue activo.' }
        if ($gitProvider) {
            if ($application.sourceType -eq 'docker' -or $application.buildType -ne 'dockerfile' `
                -or $application.branch -ne $branch) {
                throw 'El proveedor, Dockerfile o rama de Dokploy no coincide con el despliegue Git.'
            }
            $buildArgs = [regex]::Replace([string]$application.buildArgs, '(?m)^SIGREP_VERSION=.*\r?\n?', '')
            $buildArgs = $buildArgs.TrimEnd() + "`nSIGREP_VERSION=$commit"
            $update = @{ json = @{ applicationId = $secrets['APP_ID']; buildArgs = $buildArgs; autoDeploy = $false } } |
                ConvertTo-Json -Compress
            Invoke-RestMethod -Method Post -Uri "$base/application.update" -Headers $headers `
                -ContentType 'application/json' -Body $update -TimeoutSec 20 | Out-Null
        }
        Invoke-RestMethod -Method Post -Uri "$base/application.deploy" -Headers $headers `
            -ContentType 'application/json' -Body $body -TimeoutSec 30 | Out-Null
        $done = $false
        for ($attempt = 0; $attempt -lt 180; $attempt++) {
            Start-Sleep -Seconds 5
            $status = (Invoke-RestMethod -Uri "$base/application.one?input=$inputQuery" `
                -Headers $headers -TimeoutSec 15).result.data.json.applicationStatus
            if ($status -eq 'error') { throw 'Dokploy reporto un error de despliegue.' }
            if ($status -eq 'done') { $done = $true; break }
        }
        if (-not $done) { throw 'Dokploy no termino dentro del tiempo permitido.' }
        Invoke-Native -Program ssh -Arguments ($sshArgs + @($sshHost, "docker service update --detach=false '$service'"))
        if ($gitProvider) {
            $deployedCommit = (Invoke-Native -Program ssh -Arguments ($sshArgs + @($sshHost,
                "docker exec dokploy git -C '/etc/dokploy/applications/$service/code' rev-parse HEAD"))).Trim()
            if ($deployedCommit -ne $commit) { throw 'Dokploy construyo un commit diferente al publicado.' }
            $deployedHash = (Invoke-Native -Program ssh -Arguments ($sshArgs + @($sshHost,
                "docker exec dokploy sha256sum '/etc/dokploy/applications/$service/code/backend/app/core/config.py'"))) -split '\s+'
            $runningHash = (Invoke-Native -Program ssh -Arguments ($sshArgs + @($sshHost,
                "docker ps -q --filter 'label=com.docker.swarm.service.name=$service' | xargs -r -I '{}' docker exec '{}' sha256sum /app/app/core/config.py"))) -split '\s+'
            if (-not $runningHash[0] -or $runningHash[0] -ne $deployedHash[0]) {
                throw 'El contenedor no ejecuta la configuracion del commit desplegado.'
            }
        }
    } finally {
        if (Test-Path -LiteralPath $archive) { Remove-Item -LiteralPath $archive -Force }
    }
} else {
    Invoke-Native -Program ssh -Arguments ($sshArgs + @($sshHost, "mkdir -p '$remote'"))
}

Write-Host '[4/5] Reponiendo labels y red Traefik...'
Invoke-Native -Program scp -Arguments ($sshArgs + @((Join-Path $PSScriptRoot 'scripts/apply-traefik.sh'), "${sshHost}:$remote/apply-traefik.sh"))
Invoke-Native -Program ssh -Arguments ($sshArgs + @($sshHost, "bash '$remote/apply-traefik.sh' '$service' '$domain'"))
Write-Host '[5/5] Verificando HTTPS, API e interfaz...'
$healthy = $false
for ($attempt = 0; $attempt -lt 12; $attempt++) {
    try {
        $health = Invoke-RestMethod -Uri "$appUrl/api/v1/salud" -TimeoutSec 15
        if ($health.estado -ne 'operativo') { throw 'La API reporta un estado degradado.' }
        $page = Invoke-WebRequest -Uri "$appUrl/" -UseBasicParsing -TimeoutSec 15
        if (-not $SoloLabels) {
            $version = (Invoke-WebRequest -Uri "$appUrl/version.txt" -UseBasicParsing -TimeoutSec 15).Content.Trim()
            if ($version -ne $health.version -or $version -ne $commit) {
                throw 'La version publicada no coincide con el commit desplegado.'
            }
        }
        if ($page.StatusCode -eq 200) { $healthy = $true; break }
    } catch {
        if ($attempt -eq 11) { throw 'SIGREP no supera la verificacion HTTPS/API/version. Revisar Dokploy.' }
        Start-Sleep -Seconds 5
    }
}
if (-not $healthy) { throw 'SIGREP no responde correctamente.' }
Invoke-Native -Program ssh -Arguments ($sshArgs + @($sshHost, "rm -rf '$remote'"))
Write-Host "Despliegue verificado: $appUrl"