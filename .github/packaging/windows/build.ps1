param(
    [ValidateSet("x86_64", "arm64")]
    [string]$Architecture
)

$ErrorActionPreference = "Stop"

Write-Host "# === Windows Builder ==="

$AppName = "ZapZap"
$DictionaryRevision = "cccf64a8acc951afe3f47fee023908e55699bc58"
$DictionarySha256 = "6b2850f5a54994a5204a9a88d4b586e9d4e028a0360b67352b04cffdb2a3e0ea"
$DictionaryUrl = "https://chromium.googlesource.com/chromium/deps/hunspell_dictionaries/+/$DictionaryRevision/pt-BR-3-0.bdic?format=TEXT"
$DictionaryDirectory = "zapzap/qtwebengine_dictionaries"
$DictionaryPath = "$DictionaryDirectory/pt_BR.bdic"

if ([string]::IsNullOrWhiteSpace($Architecture)) {
    if ($env:PROCESSOR_ARCHITECTURE -eq "ARM64") {
        $Architecture = "arm64"
    } else {
        $Architecture = "x86_64"
    }
}

$RuntimeArchitecture = (python -c "import platform; print(platform.machine())").Trim().ToLowerInvariant()
$ExpectedRuntimeArchitectures = if ($Architecture -eq "arm64") {
    @("arm64", "aarch64")
} else {
    @("amd64", "x86_64")
}

if ($RuntimeArchitecture -notin $ExpectedRuntimeArchitectures) {
    throw "Python architecture '$RuntimeArchitecture' does not match requested artifact architecture '$Architecture'."
}

Write-Host "Target architecture: $Architecture (Python: $RuntimeArchitecture)"

# Generated Qt Python files now live in zapzap/ui/generated and are committed.
# Keep this list for future .ui sources, but do not point to removed legacy paths.
$UiFiles = @()

$AdditionalData = @(
    @("zapzap/po", "zapzap/po"),
    @("zapzap/assets", "zapzap/assets"),
    @("zapzap/features/browser/web/scripts", "zapzap/features/browser/web/scripts"),
    @($DictionaryDirectory, "qtwebengine_dictionaries")
)

$ApplicationIcon = "share/icons/com.rtosta.zapzap.ico"

if (-not (Test-Path $ApplicationIcon)) {
    throw "Icone do aplicativo nao encontrado: $ApplicationIcon"
}

Write-Host "# === Instalando dependências ==="
python -m pip install --upgrade pip
python -m pip install pyinstaller
python -m pip install -r requirements.txt

Write-Host "# === Preparando dicionário pt-BR ==="
New-Item -ItemType Directory -Force -Path $DictionaryDirectory | Out-Null
$DictionaryBase64 = "$DictionaryPath.base64"
try {
    Invoke-WebRequest -UseBasicParsing -Uri $DictionaryUrl -OutFile $DictionaryBase64
    $EncodedDictionary = [IO.File]::ReadAllText($DictionaryBase64).Trim()
    [IO.File]::WriteAllBytes(
        $DictionaryPath,
        [Convert]::FromBase64String($EncodedDictionary)
    )
} finally {
    Remove-Item -LiteralPath $DictionaryBase64 -Force -ErrorAction SilentlyContinue
}
$ActualDictionarySha256 = (Get-FileHash -Algorithm SHA256 $DictionaryPath).Hash.ToLowerInvariant()
if ($ActualDictionarySha256 -ne $DictionarySha256) {
    throw "SHA-256 inválido para o dicionário pt-BR: $ActualDictionarySha256"
}

if ($UiFiles.Count -gt 0) {
    Write-Host "# === Compilando arquivos .ui ==="

    foreach ($item in $UiFiles) {
        $source = $item[0]
        $target = $item[1]

        if (-not (Test-Path $source)) {
            Write-Host "[IGNORADO] $source"
            continue
        }

        Write-Host "$source -> $target"

        python -m PyQt6.uic.pyuic -x $source -o $target
    }
} else {
    Write-Host "# === Nenhum arquivo .ui para compilar ==="
}

Write-Host "# === Limpando builds anteriores ==="

if (Test-Path "dist") {
    Remove-Item "dist" -Recurse -Force
}

if (Test-Path "build") {
    Remove-Item "build" -Recurse -Force
}

Write-Host "# === Executando PyInstaller ==="

$Args = @(
    "--name", $AppName,
    "--onefile",
    "--windowed",
    "--noconfirm",
    "--icon", $ApplicationIcon,
    "--collect-submodules", "zapzap.features.settings.pages",
    "--collect-submodules", "windows_toasts"
)

foreach ($item in $AdditionalData) {
    $source = $item[0]
    $target = $item[1]

    if (-not (Test-Path $source)) {
        throw "Arquivo ou diretório de dados não encontrado: $source"
    }

    $Args += "--add-data"
    $Args += "$source;$target"
}

$Args += "zapzap/__main__.py"

python -m PyInstaller @Args

Write-Host "# === Renomeando executável ==="

$VersionLine = Get-Content "zapzap/__init__.py" | Where-Object {
    $_ -match "^__version__"
} | Select-Object -First 1

if ($VersionLine -match "=\s*['""]([^'""]+)['""]") {
    $Version = $Matches[1]
} else {
    $Version = "dev"
}

$ExePath = "dist/ZapZap.exe"
$FinalPath = "dist/ZapZap-$Version-windows-$Architecture.exe"

if (-not (Test-Path $ExePath)) {
    throw "Executável não encontrado: $ExePath"
}

if (Test-Path $FinalPath) {
    Remove-Item $FinalPath -Force
}

Move-Item -Path $ExePath -Destination $FinalPath -Force

Write-Host "Executável gerado: $FinalPath"
