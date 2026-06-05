# Launch Roundup (deprecated — use launch_meshstager.ps1). Forwards to MeshStager.
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
& (Join-Path $Root "launch_meshstager.ps1")
