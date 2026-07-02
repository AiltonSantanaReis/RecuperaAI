param(
    [switch]$SkipTests,
    [switch]$SkipExeSmoke,
    [switch]$NoPackage,
    [switch]$NoClean,
    [switch]$OneFile
)
$ErrorActionPreference = "Stop"

function Write-Step([string]$Message) {
    Write-Host ""
    Write-Host "== $Message =="
}

function Invoke-Checked([string]$FilePath, [string[]]$Arguments) {
    Write-Host "> $FilePath $($Arguments -join ' ')"
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Comando falhou com codigo ${LASTEXITCODE}: $FilePath $($Arguments -join ' ')"
    }
}

function Invoke-Capture([string]$FilePath, [string[]]$Arguments) {
    Write-Host "> $FilePath $($Arguments -join ' ')"
    $output = & $FilePath @Arguments 2>&1
    $exitCode = $LASTEXITCODE
    if ($output) { $output | ForEach-Object { Write-Host $_ } }
    if ($exitCode -ne 0) {
        throw "Comando falhou com codigo ${exitCode}: $FilePath $($Arguments -join ' ')"
    }
    return (($output | Out-String).Trim())
}

function Resolve-PythonLauncher {
    $candidates = @(
        @{Exe = "py"; Args = @("-3.11")},
        @{Exe = "py"; Args = @("-3")},
        @{Exe = "python"; Args = @()},
        @{Exe = "python3"; Args = @()}
    )
    foreach ($candidate in $candidates) {
        $cmd = Get-Command $candidate.Exe -ErrorAction SilentlyContinue
        if (-not $cmd) { continue }
        try {
            & $candidate.Exe @($candidate.Args + @("-c", "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)")) *> $null
            if ($LASTEXITCODE -eq 0) { return $candidate }
        } catch { }
    }
    throw "Python 3.11+ nao encontrado. Instale Python 3.11 ou 3.12 e marque a opcao 'Add python.exe to PATH'."
}

Set-Location (Join-Path $PSScriptRoot "..")

if ($env:OS -ne "Windows_NT") {
    throw "Este build deve ser executado no Windows. PyInstaller gera executavel para o sistema atual."
}

Write-Step "RecuperaAI: preparando ambiente"
Write-Host "Pasta do projeto: $(Get-Location)"
Write-Host "PowerShell: $($PSVersionTable.PSVersion)"

if (!(Test-Path "requirements.txt")) { throw "requirements.txt nao encontrado. Execute o build na raiz do projeto RecuperaAI." }
if (!(Test-Path "RecuperaAI.spec")) { throw "RecuperaAI.spec nao encontrado. Execute o build na raiz do projeto RecuperaAI." }
$requirementsFile = "requirements.txt"
if (Test-Path "requirements-lock.txt") {
    $requirementsFile = "requirements-lock.txt"
}

if (!(Test-Path .venv)) {
    $pythonLauncher = Resolve-PythonLauncher
    Write-Host "Criando ambiente virtual com: $($pythonLauncher.Exe) $($pythonLauncher.Args -join ' ')"
    & $pythonLauncher.Exe @($pythonLauncher.Args + @("-m", "venv", ".venv"))
    if ($LASTEXITCODE -ne 0) { throw "Falha ao criar ambiente virtual .venv." }
}

$venvPython = Join-Path (Get-Location) ".venv\Scripts\python.exe"
if (!(Test-Path $venvPython)) {
    throw "Python do ambiente virtual nao encontrado: $venvPython. Apague a pasta .venv e rode novamente."
}

Invoke-Checked $venvPython @("-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel")
Invoke-Checked $venvPython @("-m", "pip", "install", "-r", $requirementsFile)

Write-Step "RecuperaAI: validando codigo"
Invoke-Checked $venvPython @("-m", "compileall", "-q", "recuperaai", "tests", "scripts")
if (-not $SkipTests) {
    Invoke-Checked $venvPython @("-W", "error::ResourceWarning", "-m", "unittest", "discover", "-s", "tests", "-v")
}
$sourceSmokeDir = Join-Path $env:TEMP ("RecuperaAI_Source_Smoke_" + [guid]::NewGuid().ToString("N"))
try {
    Invoke-Checked $venvPython @("-m", "recuperaai", "--smoke-test", "--base-dir", $sourceSmokeDir)
} finally {
    Remove-Item -Path $sourceSmokeDir -Recurse -Force -ErrorAction SilentlyContinue
}
$sourceVersion = Invoke-Capture $venvPython @("-m", "recuperaai", "--version")
Write-Host "Versao do codigo-fonte: $sourceVersion"

Write-Step "RecuperaAI: gerando executavel"
if (-not $NoClean) {
    Remove-Item -Path build, dist, release -Recurse -Force -ErrorAction SilentlyContinue
}
Invoke-Checked $venvPython @("-m", "PyInstaller", "--clean", "--noconfirm", "RecuperaAI.spec")

$exe = Join-Path (Get-Location) "dist\RecuperaAI\RecuperaAI.exe"
$cliExe = Join-Path (Get-Location) "dist\RecuperaAI\RecuperaAI_CLI.exe"
if (!(Test-Path $exe)) { throw "Build falhou: RecuperaAI.exe nao encontrado em $exe." }
if (!(Test-Path $cliExe)) { throw "Build falhou: RecuperaAI_CLI.exe nao encontrado em $cliExe." }

# A versão/smoke test são executados pelo EXE auxiliar com console.
# O EXE principal continua sem console para uso normal pelo cliente.
$exeVersionFile = Join-Path $env:TEMP ("RecuperaAI_EXE_Version_" + [guid]::NewGuid().ToString("N") + ".txt")
try {
    Invoke-Checked $cliExe @("--version", "--output-file", $exeVersionFile)
    if (!(Test-Path $exeVersionFile)) {
        throw "O executavel auxiliar nao gravou o arquivo de versao: $exeVersionFile"
    }
    $exeVersion = (Get-Content $exeVersionFile -Raw -Encoding UTF8).Trim()
} finally {
    Remove-Item -Path $exeVersionFile -Force -ErrorAction SilentlyContinue
}
Write-Host "Versao do executavel auxiliar: $exeVersion"
if ($exeVersion -ne $sourceVersion) {
    throw "EXE gerado nao corresponde ao codigo-fonte atual. Fonte=[$sourceVersion] EXE=[$exeVersion]. Apague build/dist/release e rode novamente."
}

if (-not $SkipExeSmoke) {
    Write-Step "RecuperaAI: smoke test do executavel auxiliar"
    $smokeDir = Join-Path $env:TEMP ("RecuperaAI_Smoke_" + [guid]::NewGuid().ToString("N"))
    $smokeOutputFile = Join-Path $env:TEMP ("RecuperaAI_EXE_Smoke_" + [guid]::NewGuid().ToString("N") + ".json")
    try {
        Invoke-Checked $cliExe @("--smoke-test", "--base-dir", $smokeDir, "--output-file", $smokeOutputFile)
        if (!(Test-Path $smokeOutputFile)) { throw "Smoke test nao gravou saida: $smokeOutputFile" }
    } finally {
        Remove-Item -Path $smokeDir -Recurse -Force -ErrorAction SilentlyContinue
        Remove-Item -Path $smokeOutputFile -Force -ErrorAction SilentlyContinue
    }

    Write-Step "RecuperaAI: validacao operacional visual guiada"
    $visualDir = Join-Path $env:TEMP ("RecuperaAI_Visual_" + [guid]::NewGuid().ToString("N"))
    $visualOutputFile = Join-Path $env:TEMP ("RecuperaAI_EXE_Visual_" + [guid]::NewGuid().ToString("N") + ".json")
    $visualChecklist = Join-Path $env:TEMP ("CHECKLIST_VALIDACAO_VISUAL_" + [guid]::NewGuid().ToString("N") + ".md")
    try {
        Invoke-Checked $cliExe @("--visual-check", "--base-dir", $visualDir, "--output-file", $visualOutputFile, "--checklist-output", $visualChecklist)
        if (!(Test-Path $visualOutputFile)) { throw "Validacao visual nao gravou saida: $visualOutputFile" }
        if (!(Test-Path $visualChecklist)) { throw "Validacao visual nao gravou checklist: $visualChecklist" }
    } finally {
        Remove-Item -Path $visualDir -Recurse -Force -ErrorAction SilentlyContinue
        Remove-Item -Path $visualOutputFile -Force -ErrorAction SilentlyContinue
        Remove-Item -Path $visualChecklist -Force -ErrorAction SilentlyContinue
    }
}

if (-not $NoPackage) {
    Write-Step "RecuperaAI: empacotando para cliente"
    $packageArgs = @("scripts\package_windows_release.py")
    if ($SkipExeSmoke) { $packageArgs += "--skip-smoke" }
    Invoke-Checked $venvPython $packageArgs
}

Write-Host ""
Write-Host "Build concluido."
Write-Host "Executavel principal: dist\RecuperaAI\RecuperaAI.exe"
Write-Host "Executavel diagnostico: dist\RecuperaAI\RecuperaAI_CLI.exe"
Write-Host "Pacote: release\RecuperaAI_Desktop_*.zip"
Write-Host "Log: logs\build_windows_*.log"
