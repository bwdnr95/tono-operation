# scan_tono.ps1
# TONO OPERATION inventory scan (backend + frontend)
# Usage: powershell -ExecutionPolicy Bypass -File .\scan_tono.ps1

$ErrorActionPreference = "Stop"

# ---- Config (TONO default) ----
$BackendDirCandidates = @("backend", "app", "server")
$FrontendDirCandidates = @("src", "frontend", "web")

# Find best-matching directories
function Find-FirstExistingDir($candidates) {
  foreach ($c in $candidates) {
    if (Test-Path -Path $c -PathType Container) { return $c }
  }
  return $null
}

$backendDir = Find-FirstExistingDir $BackendDirCandidates
$frontendDir = Find-FirstExistingDir $FrontendDirCandidates

if (-not $backendDir) {
  Write-Host "[WARN] backend directory not found among: $($BackendDirCandidates -join ', ')"
} else {
  Write-Host "[OK] backend dir: $backendDir"
}

if (-not $frontendDir) {
  Write-Host "[WARN] frontend directory not found among: $($FrontendDirCandidates -join ', ')"
} else {
  Write-Host "[OK] frontend dir: $frontendDir"
}

# Output dir
$outDir = "_scan"
if (Test-Path $outDir) { Remove-Item -Recurse -Force $outDir }
New-Item -ItemType Directory -Path $outDir | Out-Null

# Ensure ripgrep installed
$rg = Get-Command rg -ErrorAction SilentlyContinue
if (-not $rg) {
  Write-Host "[ERROR] ripgrep(rg) not found. Install: winget install BurntSushi.ripgrep.MSVC"
  exit 1
}

# Helper: run rg and write file (even if no matches)
function Run-RgToFile($pattern, $dir, $outFile, $extraArgs=@()) {
  if (-not $dir) { return }
  $path = Join-Path $outDir $outFile
  $args = @("--no-heading", "--line-number", "--hidden", "--glob", "!.venv/**", "--glob", "!**/node_modules/**", "--glob", "!**/.git/**") + $extraArgs + @($pattern, $dir)

  # rg returns exit code 1 when no matches; treat as ok.
  $output = & rg @args 2>$null
  if ($LASTEXITCODE -eq 0 -or $LASTEXITCODE -eq 1) {
    $output | Out-File -Encoding utf8 $path
    Write-Host "  wrote $path"
  } else {
    Write-Host "[WARN] rg error ($LASTEXITCODE) for pattern: $pattern"
  }
}

# ---- Backend scans ----
if ($backendDir) {
  Write-Host "`n[SCAN] Backend: endpoints / routers / services / models"

  # Router inclusion points
  Run-RgToFile "include_router\(" $backendDir "backend_include_router.txt"

  # FastAPI endpoint decorators (router.*)
  Run-RgToFile "@router\.(get|post|put|patch|delete)\(" $backendDir "backend_endpoints_router_decorators.txt" @("--pcre2")

  # FastAPI app decorators (app.*) - sometimes used directly
  Run-RgToFile "@app\.(get|post|put|patch|delete)\(" $backendDir "backend_endpoints_app_decorators.txt" @("--pcre2")

  # APIRouter declarations
  Run-RgToFile "APIRouter\(" $backendDir "backend_apirouter_defs.txt"

  # Common route prefixes / tags (helpful to map feature modules)
  Run-RgToFile "prefix\s*=\s*['""]" $backendDir "backend_router_prefixes.txt"
  Run-RgToFile "tags\s*=\s*\[" $backendDir "backend_router_tags.txt"

  # Services / UseCases / Managers
  Run-RgToFile "class\s+\w+(Service|UseCase|Manager)\b" $backendDir "backend_services_classes.txt" @("--pcre2")
  Run-RgToFile "def\s+\w+_(service|usecase|handler)\b" $backendDir "backend_services_funcs.txt" @("--pcre2")
  Run-RgToFile "services\/|usecases\/|handlers\/" $backendDir "backend_layer_paths.txt"

  # SQLAlchemy models
  Run-RgToFile "__tablename__\s*=" $backendDir "backend_models_tablename.txt"
  Run-RgToFile "Mapped\[" $backendDir "backend_models_mapped.txt"
  Run-RgToFile "relationship\(" $backendDir "backend_models_relationships.txt"

  # DB usage hotspots
  Run-RgToFile "select\(|insert\(|update\(|delete\(" $backendDir "backend_db_queries.txt" @("--pcre2")
  Run-RgToFile "session\.execute|db\.execute" $backendDir "backend_db_execute_calls.txt"
}

# ---- Frontend scans ----
if ($frontendDir) {
  Write-Host "`n[SCAN] Frontend: routes / api calls / bulk send surfaces"

  # Routes (React Router, Next, etc.)
  Run-RgToFile "createBrowserRouter|<Route\b|Routes\b|route\s*:" $frontendDir "frontend_routes.txt" @("--pcre2")

  # API calls
  Run-RgToFile "axios\.|fetch\(|/api/|previewSend|sendConversation|bulkPreview|bulkSend" $frontendDir "frontend_api_calls.txt" @("--pcre2")

  # Components/pages likely involved in BulkSend / Conversation
  Run-RgToFile "BulkSend|Conversation|Draft|Preview" $frontendDir "frontend_feature_surfaces.txt" @("--pcre2")

  # Unused imports smell (basic)
  Run-RgToFile "import\s+.*from\s+['""][^'""]+['""]\s*;?" $frontendDir "frontend_imports_all.txt" @("--pcre2")
}

# ---- Summary ----
Write-Host "`n[DONE] Scan completed. Output folder: $outDir"
Write-Host "Next: zip the _scan folder or paste key files (backend_endpoints_router_decorators.txt, backend_models_tablename.txt, frontend_routes.txt, frontend_api_calls.txt)."
