# Assembles the portfolio-demo Hugging Face Space folder (Gradio + RAG data)
# Usage:
#   powershell -ExecutionPolicy Bypass -File preparer_demo.ps1 [-Dest <path>]
# Result: a folder ready to be pushed / uploaded as a Docker Space (see README.md).

param(
  [string]$Dest = (Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) "hf-demo-space")
)

$Root   = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)   # repo root
$Src    = Join-Path $Root "src"
$Server = Join-Path $Root "server"
$Data   = Join-Path $Root "data\processed"
$Dest   = [System.IO.Path]::GetFullPath($Dest)

function Copier([string]$source, [string]$destPath) {
  if (-not (Test-Path -LiteralPath $source)) {
    Write-Warning ("Source absente : " + $source)
    return
  }
  $parent = Split-Path -Parent $destPath
  New-Item -ItemType Directory -Force -Path $parent | Out-Null
  if ((Get-Item -LiteralPath $source).PSIsContainer) {
    New-Item -ItemType Directory -Force -Path $destPath | Out-Null
    Get-ChildItem -LiteralPath $source | Where-Object { $_.Name -ne "__pycache__" } | ForEach-Object {
      Copy-Item -LiteralPath $_.FullName -Destination $destPath -Recurse -Force
    }
  } else {
    Copy-Item -LiteralPath $source -Destination $destPath -Force
  }
}

Write-Host "Preparation de la demo Space : $Dest"

# Deploiement Gradio + Docker
Copier (Join-Path $PSScriptRoot "Dockerfile")             (Join-Path $Dest "Dockerfile")
Copier (Join-Path $PSScriptRoot "entrypoint-demo.sh")     (Join-Path $Dest "entrypoint.sh")
Copier (Join-Path $PSScriptRoot "demo_app.py")            (Join-Path $Dest "demo_app.py")
Copier (Join-Path $PSScriptRoot "requirements-demo.txt")  (Join-Path $Dest "requirements-demo.txt")
Copier (Join-Path $PSScriptRoot "README.md")              (Join-Path $Dest "README.md")
Copier (Join-Path $Root "requirements-server.txt")        (Join-Path $Dest "requirements-server.txt")

# Code
Copier $Src    (Join-Path $Dest "src")
Copier $Server (Join-Path $Dest "server")

# Donnees RAG (index FAISS, consultations, corpus)
$DataDest = Join-Path $Dest "data\processed"
New-Item -ItemType Directory -Force -Path $DataDest | Out-Null
foreach ($item in @("faiss", "consultations.db", "corpus_chunks.json")) {
  $s = Join-Path $Data $item
  if (Test-Path -LiteralPath $s) {
    Copy-Item -LiteralPath $s -Destination $DataDest -Recurse -Force
  } else {
    Write-Warning ("Donnee absente : " + $s + " (a verifier avant de pousser)")
  }
}

# .gitignore pour le Space
$gitignore = @"
__pycache__/
"@
Set-Content -LiteralPath (Join-Path $Dest ".gitignore") -Value $gitignore -Encoding utf8

Write-Host ""
Write-Host ("Demo pret : " + $Dest)
Write-Host ""
Write-Host "Pour deployer :"
Write-Host "1. Crer le Space sur huggingface.co/new-space (SDK = Docker, CPU gratuit)"
Write-Host "2. Onglet Files -> Upload files : glisser le CONTENU de $Dest"
Write-Host "   (OU pousser via git, cf. README.md)"
Write-Host "3. Aucun secret requis ; le build prend ~15-20 min"
Write-Host "4. URL publique :  https://<USER>-ao-btp-copilot-demo.hf.space"