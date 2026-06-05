# Launch MeshStager on the interactive desktop (double-click or run from Explorer).
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Pythonw = Join-Path $Root ".venv\Scripts\pythonw.exe"

if (-not (Test-Path $Pythonw)) {
    $Pythonw = Join-Path $Root ".venv\Scripts\python.exe"
}
if (-not (Test-Path $Pythonw)) {
    Write-Host "MeshStager: missing $Pythonw"
    Read-Host "Press Enter to close"
    exit 1
}

try {
    $reg = "HKCU:\Software\MeshCorral\MeshStager"
    if (-not (Test-Path $reg)) {
        New-Item -Path $reg -Force | Out-Null
    }
} catch {
    # Non-fatal if registry is unavailable.
}

Start-Process -FilePath $Pythonw -ArgumentList "-m", "meshcorral.app" -WorkingDirectory $Root
