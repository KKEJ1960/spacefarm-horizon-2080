<#
.SYNOPSIS
    Arrête UNIQUEMENT le pont du capteur réel (spacefarm/pont_capteur.py), pour libérer le port
    série (COM3 par défaut) : utile pour téléverser un nouveau programme depuis l'IDE Arduino.

.DESCRIPTION
    Laisse tourner le simulateur, l'API, le dashboard et le broker Docker.
    1. ferme la fenêtre ouverte par start.ps1 pour le pont (numéro noté dans .run\pids.json) ;
    2. par sécurité, arrête aussi tout processus "pont_capteur.py" resté actif ailleurs (lancé à la
       main, ou dans une fenêtre qu'on ne retrouve plus) ;
    3. vérifie que le port série est bien libre (tente de l'ouvrir, puis le referme aussitôt).

.EXAMPLE
    .\pont-stop.ps1
#>

$racine = $PSScriptRoot
$python = Join-Path $racine "spacefarm\.venv\Scripts\python.exe"
$fichierPids = Join-Path $racine ".run\pids.json"
$arretes = 0

# Arrête un processus ET tous ses processus enfants (le lanceur du venv Python en crée un)
function Stop-Arbre($id) {
    Get-CimInstance Win32_Process -Filter "ParentProcessId=$id" | ForEach-Object { Stop-Arbre $_.ProcessId }
    Stop-Process -Id $id -Force -ErrorAction SilentlyContinue
}

Write-Host "=== SpaceFarm : arrêt du pont capteur seul ===" -ForegroundColor Cyan

# 1. La fenêtre notée par start.ps1 (si elle existe)
if (Test-Path $fichierPids) {
    $notes = Get-Content $fichierPids -Raw | ConvertFrom-Json
    if ($notes.pont -and (Get-Process -Id $notes.pont -ErrorAction SilentlyContinue)) {
        Stop-Arbre $notes.pont
        Write-Host "  fenêtre du pont arrêtée" -ForegroundColor Green
        $arretes++
    }
    # On retire seulement l'entrée "pont" : les autres composants restent notés et ne sont pas touchés
    $copie = $notes.PSObject.Copy()
    $copie.PSObject.Properties.Remove("pont")
    $copie | ConvertTo-Json | Set-Content -Path $fichierPids -Encoding UTF8
}

# 2. Filet de sécurité : tout processus pont_capteur.py resté actif ailleurs (racine du processus
#    seulement, pour ne pas tuer deux fois le même arbre)
$restes = @(Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "*pont_capteur.py*" })
$idsRestes = $restes | ForEach-Object { $_.ProcessId }
foreach ($processus in ($restes | Where-Object { $idsRestes -notcontains $_.ParentProcessId })) {
    Stop-Arbre $processus.ProcessId
    Write-Host "  processus $($processus.ProcessId) arrêté (pont_capteur.py lancé ailleurs)" -ForegroundColor Green
    $arretes++
}

if ($arretes -eq 0) {
    Write-Host "  Rien à arrêter : le pont ne tournait pas."
}

# 3. Vérification : le port série doit être réellement libre (comme le testerait l'IDE Arduino)
Start-Sleep -Seconds 1
if (Test-Path $python) {
    $portSerie = if ($env:PORT_SERIE) { $env:PORT_SERIE } else { "COM3" }
    $script = "import serial`ntry:`n    p = serial.Serial('$portSerie', 115200, timeout=1)`n    p.close()`n    print('LIBRE')`nexcept serial.SerialException as e:`n    print(f'OCCUPE : {e}')"
    $resultat = & $python -c $script 2>&1
    if ($resultat -match "^LIBRE") {
        Write-Host "Port $portSerie libre : vous pouvez téléverser depuis Arduino IDE." -ForegroundColor Cyan
    } else {
        Write-Host "ATTENTION : port $portSerie encore occupé : $resultat" -ForegroundColor Yellow
        exit 1
    }
} else {
    Write-Host "Environnement Python introuvable : impossible de vérifier le port automatiquement." -ForegroundColor Yellow
}

Write-Host "Le simulateur, l'API et le dashboard continuent de tourner."
Write-Host "Pour relancer le pont : .\pont-start.ps1"
