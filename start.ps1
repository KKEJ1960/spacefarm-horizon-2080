<#
.SYNOPSIS
    Lance SpaceFarm : simulateur, API et dashboard, chacun dans sa propre fenêtre PowerShell.

.DESCRIPTION
    Vérifie que le broker Mosquitto (conteneur Docker "mosquitto-workshop") tourne, sinon le démarre.
    Les numéros de processus des 3 fenêtres sont notés dans .run\pids.json : stop.ps1 s'en sert.

.PARAMETER DureeCrise
    Durée de la crise en secondes. 480 = 8 minutes réelles = 48 h simulées. Transmise à l'API.

.EXAMPLE
    .\start.ps1                       # crise de 8 minutes

.EXAMPLE
    .\start.ps1 -DureeCrise 180       # crise de 3 minutes (démo)
#>
param(
    [ValidateRange(10, 86400)]
    [int]$DureeCrise = 480
)

$racine = $PSScriptRoot
$python = Join-Path $racine "spacefarm\.venv\Scripts\python.exe"
$dossierRun = Join-Path $racine ".run"
$fichierPids = Join-Path $dossierRun "pids.json"
$pids = @{}

# ---------------------------------------------------------------------------
# Petites fonctions
# ---------------------------------------------------------------------------
function Echec($message) {
    Write-Host "ERREUR : $message" -ForegroundColor Red
    if ($pids.Count -gt 0) { Write-Host "Des fenêtres ont déjà été ouvertes : lancez .\stop.ps1 pour les fermer." -ForegroundColor Yellow }
    exit 1
}

# Attend qu'un port TCP accepte les connexions (renvoie $true / $false)
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

# Attend qu'une adresse HTTP réponde (renvoie $true / $false)
function Attendre-Http($url, $secondes) {
    $limite = (Get-Date).AddSeconds($secondes)
    while ((Get-Date) -lt $limite) {
        try { Invoke-WebRequest $url -UseBasicParsing -TimeoutSec 2 | Out-Null; return $true } catch { Start-Sleep -Seconds 1 }
    }
    return $false
}

# Ouvre une nouvelle fenêtre PowerShell avec un titre, dans un dossier, qui exécute une commande.
# (la commande est encodée en base64 pour éviter tout problème de guillemets)
function Lancer-Fenetre($nom, $titre, $dossier, $commande) {
    $script = "`$Host.UI.RawUI.WindowTitle = '$titre'; " +
              "[Console]::OutputEncoding = [Text.Encoding]::UTF8; " +   # accents lisibles dans la fenêtre
              "`$env:PYTHONUTF8 = '1'; " +
              "Set-Location '$dossier'; " + $commande
    $encode = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($script))
    $fenetre = Start-Process powershell -ArgumentList "-NoExit", "-EncodedCommand", $encode -PassThru

    # On note le numéro de la fenêtre pour que stop.ps1 puisse l'arrêter
    $script:pids[$nom] = $fenetre.Id
    New-Item -ItemType Directory -Force $dossierRun | Out-Null
    $script:pids | ConvertTo-Json | Set-Content -Path $fichierPids -Encoding UTF8
}

Write-Host "=== SpaceFarm : démarrage (crise de $DureeCrise s) ===" -ForegroundColor Cyan

# ---------------------------------------------------------------------------
# 1. Vérifications
# ---------------------------------------------------------------------------
if (-not (Test-Path $python)) {
    Echec "environnement Python introuvable ($python). Voir la section Installation du README."
}
if (-not (Test-Path (Join-Path $racine "dashboard\node_modules"))) {
    Echec "dépendances du dashboard absentes. Lancez : cd dashboard ; npm install"
}
foreach ($port in 8000, 5173) {
    if (Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue) {
        Echec "le port $port est déjà utilisé (SpaceFarm tourne peut-être déjà). Lancez .\stop.ps1 puis recommencez."
    }
}

# ---------------------------------------------------------------------------
# 2. Broker Mosquitto (conteneur Docker)
# ---------------------------------------------------------------------------
Write-Host "[1/4] Broker Mosquitto (Docker)..."
docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Echec "Docker ne répond pas. Lancez Docker Desktop, attendez qu'il soit prêt, puis recommencez."
}
$enMarche = docker inspect -f "{{.State.Running}}" mosquitto-workshop 2>$null
if ($LASTEXITCODE -ne 0) {
    Echec "le conteneur mosquitto-workshop n'existe pas. Voir la section Installation du README pour le créer."
}
if ($enMarche -ne "true") {
    Write-Host "      le conteneur est arrêté : démarrage..."
    docker start mosquitto-workshop | Out-Null
}
if (-not (Attendre-Port "127.0.0.1" 1883 20)) {
    Echec "le broker MQTT ne répond pas sur le port 1883."
}
Write-Host "      broker prêt (port 1883)" -ForegroundColor Green

# ---------------------------------------------------------------------------
# 3. API, simulateur, dashboard : une fenêtre chacun
# ---------------------------------------------------------------------------
Write-Host "[2/4] API FastAPI (port 8000)..."
Lancer-Fenetre "api" "SpaceFarm - API (port 8000)" (Join-Path $racine "spacefarm") `
    "`$env:DUREE_CRISE_SECONDES = '$DureeCrise'; & '$python' -m uvicorn api:app --host 0.0.0.0 --port 8000"
if (-not (Attendre-Http "http://127.0.0.1:8000/etat" 30)) {
    Echec "l'API ne répond pas (regardez le message dans sa fenêtre)."
}
Write-Host "      API prête" -ForegroundColor Green

Write-Host "[3/4] Simulateur..."
Lancer-Fenetre "simulateur" "SpaceFarm - Simulateur" (Join-Path $racine "spacefarm") "& '$python' simulateur.py"
Write-Host "      simulateur lancé" -ForegroundColor Green

Write-Host "[4/4] Dashboard React (port 5173)..."
Lancer-Fenetre "dashboard" "SpaceFarm - Dashboard (port 5173)" (Join-Path $racine "dashboard") "npm.cmd run dev"
if (-not (Attendre-Http "http://127.0.0.1:5173" 40)) {
    Echec "le dashboard ne répond pas (regardez le message dans sa fenêtre)."
}
Write-Host "      dashboard prêt" -ForegroundColor Green

# ---------------------------------------------------------------------------
# 4. Adresses à ouvrir
# ---------------------------------------------------------------------------
# Adresses IP du PC sur le réseau (on ignore les cartes virtuelles : WSL, Docker, VirtualBox...)
$adresses = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" -and $_.InterfaceAlias -notmatch "vEthernet|WSL|VirtualBox|VMware|Loopback|Docker" } |
    Select-Object -ExpandProperty IPAddress

Write-Host ""
Write-Host "Tout est lancé (crise de $DureeCrise s)." -ForegroundColor Cyan
Write-Host ("  {0,-22}: http://127.0.0.1:5173" -f "Dashboard (ce PC)") -ForegroundColor Green
foreach ($ip in $adresses) {
    Write-Host ("  {0,-22}: http://{1}:5173" -f "Dashboard (réseau)", $ip) -ForegroundColor Green
}
Write-Host ("  {0,-22}: http://127.0.0.1:8000/docs" -f "API (documentation)")
Write-Host ""
Write-Host "Un autre PC n'arrive pas à se connecter ? Ouvrez les ports 5173 et 8000 dans le pare-feu (voir README)."
Write-Host "Pour tout arrêter : .\stop.ps1"
