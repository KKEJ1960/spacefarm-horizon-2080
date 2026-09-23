<#
.SYNOPSIS
    Arrête SpaceFarm : simulateur, API et dashboard (fenêtres et processus).

.DESCRIPTION
    1. ferme les 3 fenêtres ouvertes par start.ps1 (numéros lus dans .run\pids.json), avec leurs processus ;
    2. par sécurité, arrête aussi tout processus du projet encore actif (lancé à la main, par exemple).
    Le broker Mosquitto (Docker) n'est PAS arrêté : il peut rester allumé.
#>

$racine = $PSScriptRoot
$fichierPids = Join-Path $racine ".run\pids.json"
$arretes = 0

# Arrête un processus ET tous ses processus enfants
function Stop-Arbre($id) {
    Get-CimInstance Win32_Process -Filter "ParentProcessId=$id" | ForEach-Object { Stop-Arbre $_.ProcessId }
    Stop-Process -Id $id -Force -ErrorAction SilentlyContinue
}

Write-Host "=== SpaceFarm : arrêt ===" -ForegroundColor Cyan

# 1. Les fenêtres lancées par start.ps1
if (Test-Path $fichierPids) {
    $notes = Get-Content $fichierPids -Raw | ConvertFrom-Json
    foreach ($nom in "dashboard", "api", "simulateur", "pont") {
        $id = $notes.$nom
        if ($id -and (Get-Process -Id $id -ErrorAction SilentlyContinue)) {
            Stop-Arbre $id
            Write-Host "  $nom arrêté" -ForegroundColor Green
            $arretes++
        }
    }
    Remove-Item $fichierPids -Force
}

# 2. Filet de sécurité : processus de ce projet restés actifs (on ne garde que les "racines" de chaque groupe)
$restes = @(Get-CimInstance Win32_Process | Where-Object {
    $_.CommandLine -and
    $_.CommandLine.IndexOf($racine, [StringComparison]::OrdinalIgnoreCase) -ge 0 -and
    ($_.CommandLine -like "*uvicorn*" -or $_.CommandLine -like "*simulateur.py*" -or $_.CommandLine -like "*pont_capteur.py*" -or $_.CommandLine -like "*vite*")
})
$idsRestes = $restes | ForEach-Object { $_.ProcessId }
foreach ($processus in ($restes | Where-Object { $idsRestes -notcontains $_.ParentProcessId })) {
    Stop-Arbre $processus.ProcessId
    Write-Host "  processus $($processus.ProcessId) arrêté (lancé à la main)" -ForegroundColor Green
    $arretes++
}

if ($arretes -eq 0) {
    Write-Host "  Rien à arrêter : SpaceFarm ne tournait pas."
}

# 3. Vérification : les ports doivent être libres
Start-Sleep -Seconds 2
$occupes = @(8000, 5173 | Where-Object { Get-NetTCPConnection -State Listen -LocalPort $_ -ErrorAction SilentlyContinue })
if ($occupes.Count -eq 0) {
    Write-Host "Ports 8000 et 5173 libres. Le broker Mosquitto reste allumé." -ForegroundColor Cyan
} else {
    Write-Host "ATTENTION : port(s) encore occupé(s) : $($occupes -join ', ') (un autre programme les utilise ?)" -ForegroundColor Yellow
    exit 1
}
