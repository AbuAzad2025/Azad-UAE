$ErrorActionPreference = "Stop"

# Configuration
$LocalDB = "garage_simple"
$LocalUser = "postgres"
$RemoteHost = "your-pythonanywhere-host"
$RemotePort = "5432"
$RemoteUser = "db_user"
$RemoteDB = "db_name"
$RemotePass = $env:REMOTE_DB_PASSWORD

Write-Host "--- Garage Manager Deployment Script ---" -ForegroundColor Cyan
Write-Host "This script will copy your LOCAL database ($LocalDB) to the REMOTE server ($RemoteDB)."
Write-Host "WARNING: All existing data in the REMOTE database ($RemoteDB) will be overwritten!" -ForegroundColor Red
# $confirmation = Read-Host "Are you sure you want to proceed? (y/n)"

# if ($confirmation -ne 'y') {
#    Write-Host "Operation cancelled."
#    exit
# }

# 1. Create a clean dump of the local database (Schema + Data)
$DumpFile = "deploy_dump.sql"
Write-Host "1. Exporting local database to $DumpFile..." -ForegroundColor Yellow

$env:PGPASSWORD = $env:LOCAL_DB_PASSWORD
& "C:\Program Files\PostgreSQL\18\bin\pg_dump.exe" -h localhost -U $LocalUser -d $LocalDB --no-owner --no-acl --clean --if-exists -f $DumpFile

if ($LASTEXITCODE -ne 0) {
    Write-Host "Error exporting database. Check if 'pg_dump' is in your PATH." -ForegroundColor Red
    exit
}

# 2. Upload to Remote Server
Write-Host "2. Uploading to PythonAnywhere ($RemoteHost)..." -ForegroundColor Yellow
$env:PGPASSWORD = $RemotePass

# We use psql to connect to remote and execute the dump file
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -h $RemoteHost -p $RemotePort -U $RemoteUser -d $RemoteDB -f $DumpFile

if ($LASTEXITCODE -eq 0) {
    Write-Host "----------------------------------------" -ForegroundColor Green
    Write-Host "SUCCESS! Database deployed successfully." -ForegroundColor Green
    Write-Host "----------------------------------------" -ForegroundColor Green
    Write-Host "Next Steps:"
    Write-Host "1. Go to PythonAnywhere Console."
    Write-Host "2. Run: git pull"
    Write-Host "3. Update your .env file with the content from env.pythonanywhere"
} else {
    Write-Host "Error uploading to remote server." -ForegroundColor Red
}

# Cleanup
Remove-Item $DumpFile -ErrorAction SilentlyContinue
$env:PGPASSWORD = $null
