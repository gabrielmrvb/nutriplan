# Sobe o PostgreSQL local.
#
# O Postgres foi instalado como binários portáteis (sem privilégio de
# administrador), então ele NÃO roda como serviço do Windows: depois de
# reiniciar a máquina é preciso subir de novo com este script.
#
#   .\scripts\start_db.ps1

$PG_BIN = "C:\Users\biel-\pgsql\bin"
$PG_DATA = "C:\Users\biel-\pgdata\nutriplan"
$PG_LOG = "C:\Users\biel-\pgdata\nutriplan.log"

& "$PG_BIN\pg_isready.exe" -h 127.0.0.1 -p 5432 -q
if ($LASTEXITCODE -eq 0) {
    Write-Host "PostgreSQL ja esta rodando na porta 5432."
    exit 0
}

& "$PG_BIN\pg_ctl.exe" -D $PG_DATA -l $PG_LOG -o "-p 5432" start
Start-Sleep -Seconds 2
& "$PG_BIN\pg_isready.exe" -h 127.0.0.1 -p 5432
