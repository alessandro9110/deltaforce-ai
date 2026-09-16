#
# DeltaForce AI bootstrap for Windows PowerShell.
#
# Run it from the root of the target repository, in the IDE terminal:
#   irm https://raw.githubusercontent.com/alessandro9110/deltaforce-ai/main/install.ps1 | iex
#
# It only finds the bash of Git for Windows and hands over to install.sh, which does
# everything else: it clones DeltaForce AI into .deltaforce/framework and installs from there.
# Installer options go in $env:DF_INSTALL_ARGS, e.g. $env:DF_INSTALL_ARGS = '--advanced'.
#

$ErrorActionPreference = 'Stop'

$repoUrl = if ($env:DF_REPO_URL) { $env:DF_REPO_URL } else { 'https://github.com/alessandro9110/deltaforce-ai' }
$ref = if ($env:DF_REF) { $env:DF_REF } else { 'main' }

# bash comes with Git for Windows: next to git.exe, or in the usual install locations.
$candidates = @()
$git = Get-Command git.exe -ErrorAction SilentlyContinue
if ($git) { $candidates += (Join-Path (Split-Path (Split-Path $git.Source -Parent) -Parent) 'bin\bash.exe') }
$candidates += "$env:ProgramFiles\Git\bin\bash.exe"
$candidates += "${env:ProgramFiles(x86)}\Git\bin\bash.exe"
$candidates += "$env:LOCALAPPDATA\Programs\Git\bin\bash.exe"
$bash = $candidates | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
if (-not $bash) {
    Write-Host "  x DeltaForce AI needs Git for Windows (it provides bash): https://git-scm.com/download/win" -ForegroundColor Red
    return
}

# Download install.sh and run it: piped or not, it bootstraps itself into .deltaforce/framework.
$raw = ($repoUrl -replace '\.git$', '' -replace 'github\.com', 'raw.githubusercontent.com') + "/$ref/install.sh"
$script = Join-Path ([System.IO.Path]::GetTempPath()) 'deltaforce-install.sh'
try {
    Invoke-WebRequest -UseBasicParsing -Uri $raw -OutFile $script
} catch {
    Write-Host "  x Could not download $raw" -ForegroundColor Red
    Write-Host "    $($_.Exception.Message)"
    return
}

$unix = $script -replace '\\', '/'
try {
    & $bash -c "bash '$unix' $($env:DF_INSTALL_ARGS)"
} finally {
    Remove-Item $script -ErrorAction SilentlyContinue
}
