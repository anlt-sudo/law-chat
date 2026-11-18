<#
.SYNOPSIS
  Lệnh dev cho Windows PowerShell – tương đương Makefile.
.EXAMPLE
  ./scripts/dev.ps1 up-deps
  ./scripts/dev.ps1 migrate
  ./scripts/dev.ps1 test
#>
param(
    [Parameter(Position = 0)]
    [ValidateSet("help", "up", "up-deps", "down", "logs", "ps", "migrate", "seed",
                 "test", "test-unit", "test-int", "lint", "fmt", "typecheck", "check", "api", "worker")]
    [string]$Task = "help"
)

$ErrorActionPreference = "Stop"
# Console Windows có thể dùng bảng mã cũ (cp932, cp1252…) → ép Python dùng UTF-8 cho tiếng Việt
$env:PYTHONUTF8 = "1"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$Root = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Root "backend"

function Invoke-Backend([string[]]$Commands) {
    Push-Location $Backend
    try {
        foreach ($c in $Commands) {
            Invoke-Expression $c
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        }
    } finally { Pop-Location }
}

function Invoke-Compose([string]$CommandArgs) {
    Push-Location $Root
    try {
        Invoke-Expression "docker compose $CommandArgs"
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    } finally { Pop-Location }
}

switch ($Task) {
    "help" {
        @"
up         dựng toàn bộ (kho dữ liệu + backend + worker trong Docker)
up-deps    chỉ dựng Neo4j, PostgreSQL, Elasticsearch
down       dừng (giữ dữ liệu)
logs | ps
migrate    alembic upgrade head
seed       tạo 3 API key dev
api        chạy API local (uvicorn --reload, cổng 8000)
worker     chạy worker local
test | test-unit | test-int
lint | fmt | typecheck | check
"@
    }
    "up"        { Invoke-Compose "up -d --build" }
    "up-deps"   { Invoke-Compose "up -d --build neo4j postgres elasticsearch" }
    "down"      { Invoke-Compose "down" }
    "logs"      { Invoke-Compose "logs -f --tail=100" }
    "ps"        { Invoke-Compose "ps" }
    "migrate"   { Invoke-Backend @("uv run alembic upgrade head") }
    "seed"      { Invoke-Backend @("uv run python -m scripts.seed_api_keys") }
    "api"       { Invoke-Backend @("uv run uvicorn app.main:app --reload --port 8000") }
    "worker"    { Invoke-Backend @("uv run python -m app.worker") }
    "test"      { Invoke-Backend @("uv run pytest") }
    "test-unit" { Invoke-Backend @("uv run pytest tests/unit") }
    "test-int"  { Invoke-Backend @("uv run pytest tests/integration") }
    "lint"      { Invoke-Backend @("uv run ruff check .", "uv run ruff format --check .") }
    "fmt"       { Invoke-Backend @("uv run ruff format .", "uv run ruff check --fix .") }
    "typecheck" { Invoke-Backend @("uv run mypy app scripts") }
    "check"     { Invoke-Backend @("uv run ruff check .", "uv run ruff format --check .",
                                   "uv run mypy app scripts", "uv run pytest") }
}
