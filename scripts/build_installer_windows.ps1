<#
.SYNOPSIS
    Compile the MeshStager Windows installer from the existing PyInstaller distribution.

.DESCRIPTION
    Wraps Inno Setup's command-line compiler (ISCC.exe) around installer\MeshStager.iss.

    This script never builds the application. The frozen bundle must already exist, because the
    portable build (scripts\build_shareable_windows.py) is what verifies the bundle actually
    contains its runtime dependencies; rebuilding here would either duplicate that verification or
    silently ship an unverified payload. If dist\MeshStager is missing or incomplete, this fails
    with instructions instead of guessing.

    Steps:
      1. verify dist\MeshStager holds a complete frozen bundle (exe, _internal, required packages)
      2. locate ISCC.exe (parameter, PATH, registry, then the usual install locations)
      3. compile installer\MeshStager.iss
      4. confirm the Setup.exe landed in release\ and write a SHA256 sidecar
      5. fail with a clear message if any of the above is missing

.PARAMETER IsccPath
    Explicit path to ISCC.exe. Use when Inno Setup is installed somewhere unusual.

.PARAMETER Quiet
    Pass /Q to ISCC so only warnings and errors are printed.

.EXAMPLE
    .\scripts\build_installer_windows.ps1

.EXAMPLE
    .\scripts\build_installer_windows.ps1 -IsccPath "D:\Tools\Inno Setup 6\ISCC.exe"

.NOTES
    Exit codes: 2 payload missing or incomplete, 3 ISCC not found, 4 compile failed,
    5 expected Setup.exe not produced.
#>

[CmdletBinding()]
param(
    [AllowEmptyString()]
    [string]$IsccPath = '',

    [switch]$Quiet
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$EXIT_PAYLOAD_MISSING = 2
$EXIT_ISCC_MISSING = 3
$EXIT_COMPILE_FAILED = 4
$EXIT_OUTPUT_MISSING = 5

$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$payloadDir = Join-Path $repoRoot 'dist\MeshStager'
$payloadExe = Join-Path $payloadDir 'MeshStager.exe'
$internalDir = Join-Path $payloadDir '_internal'
$issPath = Join-Path $repoRoot 'installer\MeshStager.iss'
$outputDir = Join-Path $repoRoot 'release'

# Must match REQUIRED_BUNDLED_PACKAGES in scripts/build_shareable_windows.py: shipping an
# installer whose payload lacks SciPy is the RC3 blocker we are not allowed to reintroduce.
$requiredPackages = @('numpy', 'PIL', 'trimesh', 'scipy')


function Write-Section {
    <#
    .SYNOPSIS
        Print a labelled separator so the build log stays readable.
    #>
    param([Parameter(Mandatory = $true)][string]$Title)

    Write-Host ''
    Write-Host "== $Title ==" -ForegroundColor Cyan
}


function Get-IssDefine {
    <#
    .SYNOPSIS
        Read a "#define Name "value"" entry from the Inno Setup script.

    .DESCRIPTION
        Lets the wrapper report the exact artifact name without duplicating the version, keeping
        installer\MeshStager.iss the single source of truth for it.
    #>
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Name
    )

    $pattern = '^\s*#define\s+' + [regex]::Escape($Name) + '\s+"([^"]*)"'
    foreach ($line in (Get-Content -LiteralPath $Path)) {
        $match = [regex]::Match($line, $pattern)
        if ($match.Success) {
            return $match.Groups[1].Value
        }
    }
    return ''
}


function Find-Iscc {
    <#
    .SYNOPSIS
        Return the path to ISCC.exe, or an empty string when Inno Setup is not installed.

    .DESCRIPTION
        Checks PATH, then the registry key Inno Setup writes for both per-user and per-machine
        installs, then the default install directories including the non-admin location.
    #>
    $onPath = Get-Command 'ISCC.exe' -ErrorAction SilentlyContinue
    if ($onPath) {
        return $onPath.Source
    }

    $registryKeys = @(
        'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1',
        'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1',
        'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1'
    )
    foreach ($key in $registryKeys) {
        # Guard the property access: under Set-StrictMode a missing key yields $null, and reading
        # InstallLocation off $null is a terminating error rather than an empty result.
        $entry = Get-ItemProperty -Path $key -Name 'InstallLocation' -ErrorAction SilentlyContinue
        if (-not $entry) {
            continue
        }
        $location = $entry.InstallLocation
        if ([string]::IsNullOrWhiteSpace($location)) {
            continue
        }
        $candidate = Join-Path $location 'ISCC.exe'
        if (Test-Path -LiteralPath $candidate) {
            return (Get-Item -LiteralPath $candidate).FullName
        }
    }

    $directories = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6'),
        (Join-Path $env:ProgramFiles 'Inno Setup 6')
    )
    if (${env:ProgramFiles(x86)}) {
        $directories += (Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6')
    }
    foreach ($directory in $directories) {
        $candidate = Join-Path $directory 'ISCC.exe'
        if (Test-Path -LiteralPath $candidate) {
            return (Get-Item -LiteralPath $candidate).FullName
        }
    }

    return ''
}


# --- 1. Verify the payload ------------------------------------------------------------------

Write-Section 'Verifying frozen payload'

if (-not (Test-Path -LiteralPath $payloadExe)) {
    Write-Host "ERROR: payload not found: $payloadExe" -ForegroundColor Red
    Write-Host '       Build it first (this script never builds the app):'
    Write-Host '         .\.venv\Scripts\python.exe scripts\build_shareable_windows.py --version v0.1.0-rc3'
    exit $EXIT_PAYLOAD_MISSING
}

if (-not (Test-Path -LiteralPath $internalDir -PathType Container)) {
    Write-Host "ERROR: incomplete payload, missing runtime directory: $internalDir" -ForegroundColor Red
    exit $EXIT_PAYLOAD_MISSING
}

$missingPackages = @()
foreach ($package in $requiredPackages) {
    if (-not (Test-Path -LiteralPath (Join-Path $internalDir $package) -PathType Container)) {
        $missingPackages += $package
    }
}
if ($missingPackages.Count -gt 0) {
    Write-Host "ERROR: payload is missing required packages: $($missingPackages -join ', ')" -ForegroundColor Red
    Write-Host "       checked: $internalDir"
    Write-Host '       Rebuild with scripts\build_shareable_windows.py, which verifies this.'
    exit $EXIT_PAYLOAD_MISSING
}

if (-not (Test-Path -LiteralPath $issPath)) {
    Write-Host "ERROR: installer script not found: $issPath" -ForegroundColor Red
    exit $EXIT_PAYLOAD_MISSING
}

$payloadFiles = Get-ChildItem -LiteralPath $payloadDir -Recurse -File
$payloadMb = [math]::Round((($payloadFiles | Measure-Object Length -Sum).Sum / 1MB), 1)
$builtAt = (Get-Item -LiteralPath $payloadExe).LastWriteTime
Write-Host "Payload   : $payloadDir"
Write-Host "Files     : $($payloadFiles.Count) ($payloadMb MB)"
Write-Host "EXE built : $builtAt"
Write-Host "Packages  : $($requiredPackages -join ', ') present" -ForegroundColor Green

# --- 2. Locate ISCC -------------------------------------------------------------------------

Write-Section 'Locating Inno Setup compiler'

if (-not [string]::IsNullOrWhiteSpace($IsccPath)) {
    if (-not (Test-Path -LiteralPath $IsccPath)) {
        Write-Host "ERROR: -IsccPath does not exist: $IsccPath" -ForegroundColor Red
        exit $EXIT_ISCC_MISSING
    }
    $iscc = (Get-Item -LiteralPath $IsccPath).FullName
}
else {
    $iscc = Find-Iscc
}

if ([string]::IsNullOrWhiteSpace($iscc)) {
    Write-Host 'ERROR: ISCC.exe (Inno Setup command-line compiler) not found.' -ForegroundColor Red
    Write-Host '       Install Inno Setup 6.3 or later from https://jrsoftware.org/isdl.php'
    Write-Host '       It offers a non-administrator install into'
    Write-Host '         %LOCALAPPDATA%\Programs\Inno Setup 6'
    Write-Host '       Then re-run this script, or pass -IsccPath <path to ISCC.exe>.'
    exit $EXIT_ISCC_MISSING
}

Write-Host "ISCC: $iscc"
& $iscc /? 2>&1 | Select-Object -First 1 | ForEach-Object { Write-Host "Version: $_" }

# --- 3. Compile -----------------------------------------------------------------------------

Write-Section 'Compiling installer'

$appName = Get-IssDefine -Path $issPath -Name 'MyAppName'
$appVersion = Get-IssDefine -Path $issPath -Name 'MyAppVersion'
if ([string]::IsNullOrWhiteSpace($appName) -or [string]::IsNullOrWhiteSpace($appVersion)) {
    Write-Host "ERROR: could not read MyAppName / MyAppVersion from $issPath" -ForegroundColor Red
    exit $EXIT_COMPILE_FAILED
}
$expectedSetup = Join-Path $outputDir "${appName}_v${appVersion}_Setup.exe"
Write-Host "Script  : $issPath"
Write-Host "Version : v$appVersion"
Write-Host "Expected: $expectedSetup"
Write-Host ''

New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
if (Test-Path -LiteralPath $expectedSetup) {
    Remove-Item -LiteralPath $expectedSetup -Force
}

$isccArgs = @()
if ($Quiet) {
    $isccArgs += '/Q'
}
$isccArgs += $issPath

& $iscc @isccArgs
$compileExit = $LASTEXITCODE
if ($compileExit -ne 0) {
    Write-Host ''
    Write-Host "ERROR: ISCC failed with exit code $compileExit." -ForegroundColor Red
    exit $EXIT_COMPILE_FAILED
}

# --- 4. Confirm the artifact ----------------------------------------------------------------

Write-Section 'Installer artifact'

if (-not (Test-Path -LiteralPath $expectedSetup)) {
    Write-Host "ERROR: compile reported success but no installer at:" -ForegroundColor Red
    Write-Host "       $expectedSetup"
    Write-Host '       Check OutputDir / OutputBaseFilename in the .iss.'
    exit $EXIT_OUTPUT_MISSING
}

$setupItem = Get-Item -LiteralPath $expectedSetup
$setupMb = [math]::Round(($setupItem.Length / 1MB), 1)
$hash = (Get-FileHash -LiteralPath $expectedSetup -Algorithm SHA256).Hash.ToLower()
$shaPath = "$expectedSetup.sha256.txt"
Set-Content -LiteralPath $shaPath -Value $hash -Encoding ascii

Write-Host "Installer : $expectedSetup" -ForegroundColor Green
Write-Host "Size      : $setupMb MB (payload $payloadMb MB)"
Write-Host "SHA256    : $hash"
Write-Host "Sidecar   : $shaPath"
Write-Host ''
Write-Host 'Installs per-user into %LOCALAPPDATA%\Programs\MeshStager (no administrator rights).'
Write-Host 'Unsigned, so Windows SmartScreen will show an "unknown publisher" warning; testers'
Write-Host 'must choose More info -> Run anyway.'

exit 0
