# Assembles the Hugging Face Space folder (code + real RAG data)
# Usage:
#   powershell -ExecutionPolicy Bypass -File preparer_space.ps1 [-Dest <path>]
# Result: a folder ready to be pushed as a Docker Space (see README.md).

param(
  [string]$Dest = (Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) "hf-space")
)

$Root   = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)   # repo root
$Src    = Join-Path $Root "src"
$Server = Join-Path $Root "server"
$Web    = Join-Path $Root "web"
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

Write-Host "Preparation du Space : $Dest"

# Docker / entrypoint / docs
Copier (Join-Path $PSScriptRoot "..\HF-Dockerfile") (Join-Path $Dest "Dockerfile")
Copier (Join-Path $PSScriptRoot "entrypoint.sh")    (Join-Path $Dest "entrypoint.sh")
Copier (Join-Path $PSScriptRoot "README.md")        (Join-Path $Dest "README.md")
Copier (Join-Path $Root "requirements-server.txt")  (Join-Path $Dest "requirements-server.txt")

# App code
Copier $Src    (Join-Path $Dest "src")
Copier $Server (Join-Path $Dest "server")
Copier (Join-Path $Root "app.py") (Join-Path $Dest "app.py")

# Frontend (skip node_modules and dist)
$WebDest = Join-Path $Dest "web"
New-Item -ItemType Directory -Force -Path $WebDest | Out-Null
Get-ChildItem -LiteralPath $Web -Recurse | Where-Object {
  $_.FullName -notmatch "\\node_modules(\\|$)" -and $_.FullName -notmatch "\\dist(\\|$)"
} | ForEach-Object {
  $rel = $_.FullName.Substring($Web.Length).TrimStart("\")
  $dst = Join-Path $WebDest $rel
  if ($_.PSIsContainer) { New-Item -ItemType Directory -Force -Path $dst | Out-Null }
  else { Copy-Item -LiteralPath $_.FullName -Destination $dst -Force }
}

# RAG data (faiss index, consultations, corpus chunks)
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

# .gitignore for the Space
$gitignore = @"
node_modules/
web/node_modules/
web/dist/
__pycache__/
"@
Set-Content -LiteralPath (Join-Path $Dest ".gitignore") -Value $gitignore -Encoding utf8

Write-Host ""
Write-Host ("Space pret : " + $Dest)
Write-Host ""
Write-Host "Etapes suivantes (voir README.md) :"
Write-Host "1. Creer l'espace sur huggingface.co/new-space (SDK = Docker, CPU gratuit)"
Write-Host ("2. cd `"$Dest`"")
Write-Host "   git init && git add -A && git commit -m `"Deploiement initial AO-BTP Copilot`""
Write-Host "   git remote add origin https://huggingface.co/spaces/<USER>/<SPACE>"
Write-Host "   git push --set-upstream origin main"
Write-Host "3. Secret obligatoire (Settings -> Variables and secrets) :  JWT_SECRET=<secret long>"
Write-Host "4. URL publique :  https://<USER>-<SPACE>.hf.space"