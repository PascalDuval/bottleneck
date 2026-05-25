# run_build.ps1
# Script PowerShell pour créer l'environnement virtuel, installer les dépendances et exécuter build_consolidation.py.

Set-Location $PSScriptRoot

function Get-PythonLauncher {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        return "py"
    }
    if (Get-Command python -ErrorAction SilentlyContinue) {
        return "python"
    }
    return $null
}

$pythonCommand = Get-PythonLauncher
if (-not $pythonCommand) {
    Write-Error "Python n'est pas installé ou n'est pas accessible. Installe Python depuis https://www.python.org/downloads/."
    exit 1
}

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Création de l'environnement virtuel..."
    & $pythonCommand -3 -m venv .venv
}

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Error "Impossible de trouver le Python de l'environnement virtuel."
    exit 1
}

Write-Host "Installation des dépendances..."
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install pandas numpy openpyxl

Write-Host "Exécution de nettoyage_reconciliation.py..."
& $venvPython nettoyage_reconciliation.py

Write-Host "Terminé. Le fichier de sortie est data\consolidation.xlsx."