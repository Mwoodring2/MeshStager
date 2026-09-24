<#
.SYNOPSIS
    Launch a frozen MeshStager build against a disposable AppData sandbox.

.DESCRIPTION
    Manual RC smoke testing normally runs against the tester's real user data, which means a
    release check can migrate legacy Roundup data forward and then run bridge retention against
    that copied state. This launcher redirects the app's per-user file locations into a throwaway
    folder under %TEMP% for the launched process only, so a smoke test starts from an empty
    profile and leaves the tester's own caches, logs, and bridge output untouched.

    Overridden for the child process only:
      LOCALAPPDATA -> <sandbox>\Local     (MeshStager caches, logs, bridge output, exports,
                                           render staging, and the legacy Roundup migration source)
      APPDATA      -> <sandbox>\Roaming

    The parent shell is never modified: the overrides are applied through the child process's
    own environment block via ProcessStartInfo, not by assigning to $env:.

    Known limits, both by design (this script does not change app behavior):

    * Preferences are NOT isolated. SettingsService uses QSettings("WoodringTools", "MeshStager")
      in NativeFormat, which on Windows is HKCU\Software\WoodringTools\MeshStager in the registry,
      not a file under AppData. A sandboxed run therefore still inherits the last scan folder,
      view mode, and other settings. Use a separate Windows profile if you need those isolated too.
    * USERPROFILE is deliberately left alone. data_migration reads LOCALAPPDATA and only falls
      back to Path.home() when it is unset, which this script always sets; the remaining Path.home()
      uses are file-dialog start directories, which write no app state.
    * Blender discovery scans LOCALAPPDATA among its install roots, so a Blender installed under
      the real LOCALAPPDATA will not be found during a sandboxed run. Installs under
      ProgramFiles are unaffected.

.PARAMETER ExePath
    Path to the built MeshStager.exe, for example
    release\MeshStager_v0.1.0-rc3_Windows_Portable\MeshStager\MeshStager.exe

.PARAMETER Clean
    Delete the sandbox after the app exits. Omit it to keep the sandbox for inspection.

.EXAMPLE
    .\scripts\smoke_test_portable.ps1 "C:\MeshStager_Test\MeshStager_v0.1.0-rc3_Windows_Portable\MeshStager\MeshStager.exe"

.EXAMPLE
    .\scripts\smoke_test_portable.ps1 -ExePath .\dist\MeshStager\MeshStager.exe -Clean

.NOTES
    Exit codes: 2 invalid arguments, 3 sandbox creation failed, 4 launch failed,
    5 isolation check failed. Otherwise the application's own exit code is returned.
#>

[CmdletBinding()]
param(
    # Not Mandatory on purpose: a mandatory parameter prompts, which would hang the script when
    # it is run from a build step or a non-interactive shell. Missing paths are reported instead.
    [Parameter(Position = 0)]
    [AllowEmptyString()]
    [string]$ExePath = '',

    [switch]$Clean
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$EXIT_BAD_ARGS = 2
$EXIT_SANDBOX_FAILED = 3
$EXIT_LAUNCH_FAILED = 4
$EXIT_ISOLATION_FAILED = 5


function Write-Section {
    <#
    .SYNOPSIS
        Print a labelled separator so the launch log stays readable.
    #>
    param([Parameter(Mandatory = $true)][string]$Title)

    Write-Host ''
    Write-Host "== $Title ==" -ForegroundColor Cyan
}


function Get-PathFingerprint {
    <#
    .SYNOPSIS
        Return a comparable snapshot of a directory, used to prove it was not written to.

    .DESCRIPTION
        Records the directory's own timestamp plus its immediate children and the size and
        timestamp of the app log, which is what a stray non-sandboxed run would touch first.
        Deliberately shallow: a recursive walk of a populated thumbnail or bridge cache would
        make a smoke launch feel slow for no extra signal.
    #>
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        return 'absent'
    }

    $parts = New-Object System.Collections.Generic.List[string]
    $root = Get-Item -LiteralPath $Path
    $parts.Add("self=$($root.LastWriteTimeUtc.Ticks)")

    foreach ($child in (Get-ChildItem -LiteralPath $Path -ErrorAction SilentlyContinue | Sort-Object Name)) {
        $parts.Add("$($child.Name)=$($child.LastWriteTimeUtc.Ticks)")
    }

    $logPath = Join-Path $Path 'logs\roundup.log'
    if (Test-Path -LiteralPath $logPath) {
        $log = Get-Item -LiteralPath $logPath
        $parts.Add("log=$($log.Length):$($log.LastWriteTimeUtc.Ticks)")
    }

    return ($parts -join '|')
}


function Get-LongPath {
    <#
    .SYNOPSIS
        Expand an 8.3 short path such as C:\Users\MICHAE~1.WOO\... to its long form.

    .DESCRIPTION
        %TEMP% is frequently handed out in short form. MeshStager has a known path_key
        normalization difference on 8.3 paths (see the warm-reopen note in
        docs/AI_PROJECT_HANDOFF.md), so the sandbox is created under the long form to keep the
        smoke test away from that edge case. Returns the input unchanged if expansion fails.
    #>
    param([Parameter(Mandatory = $true)][string]$Path)

    if ($Path -notlike '*~*') {
        return $Path
    }

    if (-not ('MeshStager.PathNative' -as [type])) {
        Add-Type -Namespace 'MeshStager' -Name 'PathNative' -MemberDefinition @'
[DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
public static extern uint GetLongPathName(string shortPath,
                                          System.Text.StringBuilder longPath,
                                          uint bufferSize);
'@
    }

    $capacity = 1024
    $builder = New-Object System.Text.StringBuilder $capacity
    $written = [MeshStager.PathNative]::GetLongPathName($Path, $builder, $capacity)
    if ($written -gt 0 -and $written -lt $capacity) {
        return $builder.ToString()
    }
    return $Path
}


function Resolve-ExeOrExit {
    <#
    .SYNOPSIS
        Validate the supplied EXE path and return its full path.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$Candidate
    )

    $trimmed = $Candidate.Trim('"', ' ')
    if ([string]::IsNullOrWhiteSpace($trimmed)) {
        Write-Host 'ERROR: no EXE path supplied.' -ForegroundColor Red
        Write-Host 'Usage: .\scripts\smoke_test_portable.ps1 <path to MeshStager.exe> [-Clean]'
        exit $EXIT_BAD_ARGS
    }

    if (-not (Test-Path -LiteralPath $trimmed)) {
        Write-Host "ERROR: EXE not found: $trimmed" -ForegroundColor Red
        exit $EXIT_BAD_ARGS
    }

    $item = Get-Item -LiteralPath $trimmed
    if ($item.PSIsContainer) {
        Write-Host "ERROR: path is a directory, not an EXE: $($item.FullName)" -ForegroundColor Red
        Write-Host '       Point at MeshStager\MeshStager.exe inside the portable folder.'
        exit $EXIT_BAD_ARGS
    }

    if ($item.Extension -ne '.exe') {
        Write-Host "ERROR: not an executable: $($item.FullName)" -ForegroundColor Red
        exit $EXIT_BAD_ARGS
    }

    return $item.FullName
}


# --- Validate input -------------------------------------------------------------------------

$exeFullPath = Resolve-ExeOrExit -Candidate $ExePath
$exeDirectory = Split-Path -Parent $exeFullPath

# --- Record the caller's real values so the run can be proven non-invasive ------------------

$callerLocalAppData = $env:LOCALAPPDATA
$callerAppData = $env:APPDATA
if ([string]::IsNullOrWhiteSpace($callerLocalAppData)) {
    Write-Host 'ERROR: LOCALAPPDATA is not set in this shell; cannot verify isolation.' -ForegroundColor Red
    exit $EXIT_BAD_ARGS
}

$realMeshStagerDir = Join-Path $callerLocalAppData 'MeshStager'
$realRoundupDir = Join-Path $callerLocalAppData 'Roundup'
$beforeMeshStager = Get-PathFingerprint -Path $realMeshStagerDir
$beforeRoundup = Get-PathFingerprint -Path $realRoundupDir
$beforeAppData = Get-PathFingerprint -Path $callerAppData

# --- Create the sandbox ---------------------------------------------------------------------

$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$tempRoot = Get-LongPath -Path $env:TEMP
$sandboxRoot = Join-Path $tempRoot "MeshStager_SmokeTest_$stamp"
$sandboxLocal = Join-Path $sandboxRoot 'Local'
$sandboxRoaming = Join-Path $sandboxRoot 'Roaming'

try {
    foreach ($dir in @($sandboxRoot, $sandboxLocal, $sandboxRoaming)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
}
catch {
    Write-Host "ERROR: could not create sandbox under $env:TEMP : $($_.Exception.Message)" -ForegroundColor Red
    exit $EXIT_SANDBOX_FAILED
}

foreach ($dir in @($sandboxRoot, $sandboxLocal, $sandboxRoaming)) {
    if (-not (Test-Path -LiteralPath $dir -PathType Container)) {
        Write-Host "ERROR: sandbox directory missing after creation: $dir" -ForegroundColor Red
        exit $EXIT_SANDBOX_FAILED
    }
}

Write-Section 'Disposable smoke-test sandbox'
Write-Host "EXE            : $exeFullPath"
Write-Host "Sandbox root   : $sandboxRoot"
Write-Host "LOCALAPPDATA   -> $sandboxLocal"
Write-Host "APPDATA        -> $sandboxRoaming"
Write-Host "App log will be: $(Join-Path $sandboxLocal 'MeshStager\logs\roundup.log')"
Write-Host ''
Write-Host 'Real user data left alone:' -ForegroundColor Green
Write-Host "  $realMeshStagerDir"
Write-Host "  $realRoundupDir"
Write-Host "  $callerAppData"
Write-Host ''
Write-Host 'Note: preferences are NOT sandboxed. QSettings uses the registry' -ForegroundColor Yellow
Write-Host '      (HKCU\Software\WoodringTools\MeshStager), so the last scan folder and' -ForegroundColor Yellow
Write-Host '      view mode still carry over. See this script''s help for details.' -ForegroundColor Yellow

# --- Launch with an overridden child environment only ---------------------------------------

Write-Section 'Launching (waiting for exit)'

$startInfo = New-Object System.Diagnostics.ProcessStartInfo
$startInfo.FileName = $exeFullPath
$startInfo.WorkingDirectory = $exeDirectory
# UseShellExecute must be false for the custom environment block to apply.
$startInfo.UseShellExecute = $false
$startInfo.EnvironmentVariables['LOCALAPPDATA'] = $sandboxLocal
$startInfo.EnvironmentVariables['APPDATA'] = $sandboxRoaming

$startedAt = Get-Date
try {
    $process = [System.Diagnostics.Process]::Start($startInfo)
}
catch {
    Write-Host "ERROR: failed to launch: $($_.Exception.Message)" -ForegroundColor Red
    exit $EXIT_LAUNCH_FAILED
}

Write-Host "Started PID $($process.Id) at $($startedAt.ToString('HH:mm:ss')). Close MeshStager to finish."
$process.WaitForExit()
$appExitCode = $process.ExitCode
$elapsed = (Get-Date) - $startedAt
Write-Host ("Exited with code {0} after {1:n1}s." -f $appExitCode, $elapsed.TotalSeconds)

# --- Verify isolation held ------------------------------------------------------------------

Write-Section 'Isolation check'

$failures = New-Object System.Collections.Generic.List[string]

if ($env:LOCALAPPDATA -ne $callerLocalAppData) {
    $failures.Add("caller LOCALAPPDATA changed: '$callerLocalAppData' -> '$env:LOCALAPPDATA'")
}
if ($env:APPDATA -ne $callerAppData) {
    $failures.Add("caller APPDATA changed: '$callerAppData' -> '$env:APPDATA'")
}
if ((Get-PathFingerprint -Path $realMeshStagerDir) -ne $beforeMeshStager) {
    $failures.Add("real $realMeshStagerDir was modified")
}
if ((Get-PathFingerprint -Path $realRoundupDir) -ne $beforeRoundup) {
    $failures.Add("real $realRoundupDir was modified")
}
if ((Get-PathFingerprint -Path $callerAppData) -ne $beforeAppData) {
    $failures.Add("real $callerAppData was modified")
}

$sandboxUsed = Test-Path -LiteralPath (Join-Path $sandboxLocal 'MeshStager')
if ($sandboxUsed) {
    Write-Host "PASS  app wrote into the sandbox: $(Join-Path $sandboxLocal 'MeshStager')" -ForegroundColor Green
    Get-ChildItem -LiteralPath (Join-Path $sandboxLocal 'MeshStager') -Directory -ErrorAction SilentlyContinue |
        ForEach-Object { Write-Host "        $($_.Name)\" }
}
else {
    Write-Host 'WARN  app created nothing under the sandbox; did it start correctly?' -ForegroundColor Yellow
}

Write-Host "PASS  caller LOCALAPPDATA unchanged: $env:LOCALAPPDATA" -ForegroundColor Green

if ($failures.Count -gt 0) {
    Write-Host ''
    foreach ($failure in $failures) {
        Write-Host "FAIL  $failure" -ForegroundColor Red
    }
    Write-Host ''
    Write-Host "Sandbox kept for inspection: $sandboxRoot"
    exit $EXIT_ISOLATION_FAILED
}

Write-Host 'PASS  real MeshStager / Roundup / APPDATA locations untouched' -ForegroundColor Green

# --- Report the readiness line the release gate cares about ---------------------------------

$sandboxLog = Join-Path $sandboxLocal 'MeshStager\logs\roundup.log'
if (Test-Path -LiteralPath $sandboxLog) {
    Write-Section 'Startup environment (from the sandboxed run)'
    Select-String -Path $sandboxLog -Pattern 'Startup environment' |
        ForEach-Object { Write-Host $_.Line }
    $errorLines = Select-String -Path $sandboxLog -Pattern '\| ERROR \|'
    if ($errorLines) {
        Write-Host ''
        Write-Host "$($errorLines.Count) ERROR line(s) in the sandbox log:" -ForegroundColor Yellow
        $errorLines | Select-Object -First 10 | ForEach-Object { Write-Host $_.Line }
    }
    else {
        Write-Host 'No ERROR lines in the sandbox log.' -ForegroundColor Green
    }
}

# --- Keep or remove the sandbox -------------------------------------------------------------

Write-Section 'Sandbox'
if ($Clean) {
    Remove-Item -LiteralPath $sandboxRoot -Recurse -Force -ErrorAction SilentlyContinue
    if (Test-Path -LiteralPath $sandboxRoot) {
        Write-Host "Could not fully remove $sandboxRoot (files may still be locked)." -ForegroundColor Yellow
    }
    else {
        Write-Host 'Removed (-Clean).'
    }
}
else {
    Write-Host "Kept for inspection: $sandboxRoot"
    Write-Host "Logs: $(Join-Path $sandboxLocal 'MeshStager\logs')"
    Write-Host 'Re-run with -Clean to delete it automatically.'
}

exit $appExitCode
