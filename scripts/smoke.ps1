# PowerShell Smoke Test Script for ASHA Diary API
# Starts the API, polls /api/health, runs a conversation via /api/turn,
# checks persistence via /api/entries, and terminates the server.

[CmdletBinding()]
param(
    [int]$Port = 8000,
    [int]$TimeoutSeconds = 30
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = (Resolve-Path "$ScriptDir/..").Path
$ApiDir = Join-Path $RepoRoot "apps/api"

Write-Host "=== ASHA Diary API Smoke Test (PowerShell) ==="
Write-Host "Repository root: $RepoRoot"

# Find python executable
$VenvPython = Join-Path $ApiDir ".venv/Scripts/python.exe"
if (Test-Path $VenvPython) {
    $PythonExe = $VenvPython
} else {
    $PythonExe = (Get-Command python).Source
}
Write-Host "Using Python: $PythonExe"

# Use a clean temporary SQLite database for this smoke test
$TempDbPath = [System.IO.Path]::Combine([System.IO.Path]::GetTempPath(), "asha_smoke_$([System.Guid]::NewGuid().ToString('N')).db")
$TempDbUrl = "sqlite:///" + $TempDbPath.Replace("\", "/")
Write-Host "Temporary DB: $TempDbPath"

$ServerProc = $null

try {
    Write-Host "Starting API server on port $Port..."
    $StartInfo = New-Object System.Diagnostics.ProcessStartInfo
    $StartInfo.FileName = $PythonExe
    $StartInfo.Arguments = "-m uvicorn app.main:app --host 127.0.0.1 --port $Port"
    $StartInfo.WorkingDirectory = $ApiDir
    $StartInfo.EnvironmentVariables["DATABASE_URL"] = $TempDbUrl
    $StartInfo.EnvironmentVariables["RATE_LIMIT_PER_MINUTE"] = "1000"
    $StartInfo.UseShellExecute = $false
    $StartInfo.CreateNoWindow = $true

    $ServerProc = [System.Diagnostics.Process]::Start($StartInfo)
    Write-Host "Server PID: $($ServerProc.Id)"

    # Wait for /api/health
    $HealthUrl = "http://127.0.0.1:$Port/api/health"
    $TurnUrl = "http://127.0.0.1:$Port/api/turn"
    $EntriesUrl = "http://127.0.0.1:$Port/api/entries"

    Write-Host "Waiting for server to become healthy at $HealthUrl..."
    $Started = Get-Date
    $Healthy = $false
    while (((Get-Date) - $Started).TotalSeconds -lt $TimeoutSeconds) {
        if ($ServerProc.HasExited) {
            throw "Server process exited prematurely with code $($ServerProc.ExitCode)"
        }
        try {
            $resp = Invoke-RestMethod -Uri $HealthUrl -Method Get -TimeoutSec 2 -ErrorAction SilentlyContinue
            if ($resp -and $resp.status -eq "ok") {
                $Healthy = $true
                break
            }
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }

    if (-not $Healthy) {
        throw "Server failed to respond to $HealthUrl within $TimeoutSeconds seconds."
    }
    Write-Host "[OK] Server is healthy."

    $SessionId = "smoke_" + ([System.Guid]::NewGuid().ToString('N').Substring(0, 8))
    $Headers = @{ "Content-Type" = "application/json" }

    # Turn 1: Report entry (missing count -> ask_field)
    Write-Host "`n--- Turn 1: Report initial entry ---"
    $Body1 = @{
        session_id = $SessionId
        text = "aaj Rina ANC visit korlam"
    } | ConvertTo-Json
    Write-Host "POST /api/turn: aaj Rina ANC visit korlam"
    $Turn1 = Invoke-RestMethod -Uri $TurnUrl -Method Post -Headers $Headers -Body $Body1
    Write-Host "Response ui_hint: $($Turn1.ui_hint)"
    Write-Host "Response text:    $($Turn1.response_text)"
    if ($Turn1.ui_hint -ne "ask_field") {
        throw "Expected ui_hint 'ask_field' on Turn 1, got '$($Turn1.ui_hint)'"
    }
    Write-Host "[OK] Turn 1 prompted for missing count."

    # Turn 2: Provide count (-> confirm)
    Write-Host "`n--- Turn 2: Provide count ---"
    $Body2 = @{
        session_id = $SessionId
        text = "2 jon"
    } | ConvertTo-Json
    Write-Host "POST /api/turn: 2 jon"
    $Turn2 = Invoke-RestMethod -Uri $TurnUrl -Method Post -Headers $Headers -Body $Body2
    Write-Host "Response ui_hint: $($Turn2.ui_hint)"
    Write-Host "Response text:    $($Turn2.response_text)"
    if ($Turn2.ui_hint -ne "confirm") {
        throw "Expected ui_hint 'confirm' on Turn 2, got '$($Turn2.ui_hint)'"
    }
    Write-Host "[OK] Turn 2 prompted for confirmation."

    # Turn 3: Confirm (-> saved)
    Write-Host "`n--- Turn 3: Confirm entry ---"
    $Body3 = @{
        session_id = $SessionId
        text = "hyan"
    } | ConvertTo-Json
    Write-Host "POST /api/turn: hyan"
    $Turn3 = Invoke-RestMethod -Uri $TurnUrl -Method Post -Headers $Headers -Body $Body3
    Write-Host "Response ui_hint: $($Turn3.ui_hint)"
    Write-Host "Response text:    $($Turn3.response_text)"
    if ($Turn3.ui_hint -ne "saved") {
        throw "Expected ui_hint 'saved' on Turn 3, got '$($Turn3.ui_hint)'"
    }
    Write-Host "[OK] Turn 3 saved the entry."

    # Verification: GET /api/entries
    Write-Host "`n--- Verifying persistence via GET /api/entries ---"
    $Entries = Invoke-RestMethod -Uri $EntriesUrl -Method Get
    Write-Host "Total entries returned: $($Entries.Count)"
    $Saved = $Entries | Where-Object { $_.task_type -eq "antenatal_visit" -and $_.count -eq 2 -and $_.beneficiary_ref -eq "R" }

    if (-not $Saved) {
        throw "Saved entry not found in GET /api/entries."
    }
    Write-Host "Found entry: ID=$($Saved.id), task_type=$($Saved.task_type), count=$($Saved.count), ref=$($Saved.beneficiary_ref), status=$($Saved.status)"
    if ($Saved.status -ne "confirmed") {
        throw "Expected saved entry status 'confirmed', got '$($Saved.status)'"
    }
    Write-Host "[OK] Entry confirmed and verified in database!"

    Write-Host "`n=========================================="
    Write-Host "=== SMOKE TEST PASSED SUCCESSFULLY ==="
    Write-Host "=========================================="
}
finally {
    if ($ServerProc -and -not $ServerProc.HasExited) {
        Write-Host "Stopping API server process (PID $($ServerProc.Id))..."
        try {
            Stop-Process -Id $ServerProc.Id -Force -ErrorAction SilentlyContinue
            Write-Host "Server stopped."
        } catch {
            Write-Warning "Could not stop server: $_"
        }
    }
    if (Test-Path $TempDbPath) {
        Remove-Item -Force $TempDbPath -ErrorAction SilentlyContinue
        Write-Host "Cleaned up temporary database."
    }
}
