param(
    [string]$PackageZip
)
$ErrorActionPreference = "Stop"
if (-not $PackageZip) {
    $latest = Get-ChildItem -Path "release" -Filter "RecuperaAI_Desktop_*.zip" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $latest) { throw "Nenhum pacote encontrado em release\. Informe -PackageZip." }
    $PackageZip = $latest.FullName
}
$tmp = Join-Path $env:TEMP ("RecuperaAI_Verificacao_" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $tmp | Out-Null
try {
    Expand-Archive -Path $PackageZip -DestinationPath $tmp -Force
    $exe = Get-ChildItem -Path $tmp -Filter "RecuperaAI.exe" -Recurse | Select-Object -First 1
    if (-not $exe) { throw "RecuperaAI.exe não encontrado dentro do pacote." }
    $cliExe = Get-ChildItem -Path $tmp -Filter "RecuperaAI_CLI.exe" -Recurse | Select-Object -First 1
    if (-not $cliExe) { throw "RecuperaAI_CLI.exe não encontrado dentro do pacote." }
    $base = Join-Path $tmp "dados_smoke"
    Push-Location $cliExe.DirectoryName
    try {
        & $cliExe.FullName --smoke-test --base-dir $base
        if ($LASTEXITCODE -ne 0) { throw "Smoke test do pacote falhou." }
    }
    finally {
        Pop-Location
    }
    Write-Host "Pacote validado com sucesso: $PackageZip"
}
finally {
    Remove-Item -Path $tmp -Recurse -Force -ErrorAction SilentlyContinue
}
