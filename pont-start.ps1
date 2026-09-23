<#
.SYNOPSIS
    Relance UNIQUEMENT le pont du capteur réel (spacefarm/pont_capteur.py), dans sa propre fenêtre.

.DESCRIPTION
    Ne touche pas au simulateur, à l'API ni au dashboard : ils doivent déjà tourner (lancés par
    start.ps1). À utiliser après .\pont-stop.ps1, une fois le nouveau programme de l'ESP32
    téléversé et l'IDE Arduino fermé (sinon il retient le port).

.EXAMPLE
    .\pont-start.ps1
#>

$racine = $PSScriptRoot
$python = Join-Path $racine "spacefarm\.venv\Scripts\python.exe"
$dossierRun = Join-Path $racine ".run"
$fichierPids = Join-Path $dossierRun "pids.json"

function Attendre-Port($adresse, $port, $secondes) {
    $limite = (Get-Date).AddSeconds($secondes)
    while ((Get-Date) -lt $limite) {
        try {
            $client = New-Object Net.Sockets.TcpClient
            $ok = $client.ConnectAsync($adresse, $port).Wait(500)
            $client.Close()
            if ($ok) { return $true }
        } catch { }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

Write-Host "=== SpaceFarm : relance du pont capteur seul ===" -ForegroundColor Cyan

if (-not (Test-Path $python)) {
    Write-Host "ERREUR : environnement Python introuvable ($python)." -ForegroundColor Red
    exit 1
}
if (-not (Attendre-Port "127.0.0.1" 1883 5)) {
    Write-Host "ERREUR : le broker MQTT (port 1883) ne répond pas. Le pont a besoin du broker (et de l'API pour être utile) : vérifiez qu'ils tournent (.\start.ps1)." -ForegroundColor Red
    exit 1
}

# Même façon d'ouvrir une fenêtre que start.ps1 (titre, encodage, dossier de travail)
$script = "`$Host.UI.RawUI.WindowTitle = 'SpaceFarm - Capteur réel (COM3)'; " +
          "[Console]::OutputEncoding = [Text.Encoding]::UTF8; " +
          "`$env:PYTHONUTF8 = '1'; " +
          "Set-Location '$(Join-Path $racine "spacefarm")'; & '$python' pont_capteur.py"
$encode = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($script))
$fenetre = Start-Process powershell -ArgumentList "-NoExit", "-EncodedCommand", $encode -PassThru

# On note la fenêtre dans .run\pids.json, sans toucher aux autres entrées (api, simulateur, dashboard)
New-Item -ItemType Directory -Force $dossierRun | Out-Null
$notes = if (Test-Path $fichierPids) { Get-Content $fichierPids -Raw | ConvertFrom-Json } else { [PSCustomObject]@{} }
$notes | Add-Member -NotePropertyName "pont" -NotePropertyValue $fenetre.Id -Force
$notes | ConvertTo-Json | Set-Content -Path $fichierPids -Encoding UTF8

Write-Host "Pont relancé (fenêtre PID $($fenetre.Id))." -ForegroundColor Green
Write-Host "Si l'ESP32 n'est pas branché ou que le port est encore occupé, sa fenêtre l'indique."
Write-Host "Pour l'arrêter de nouveau : .\pont-stop.ps1"
