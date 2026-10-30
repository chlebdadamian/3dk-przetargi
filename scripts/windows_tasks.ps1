# Rejestruje automat w Harmonogramie zadań Windows (folder \3dk-przetargi\).
#
#   powershell -ExecutionPolicy Bypass -File scripts\windows_tasks.ps1           # utwórz / zaktualizuj
#   powershell -ExecutionPolicy Bypass -File scripts\windows_tasks.ps1 -Remove   # usuń wszystkie
#
# Zadania działają, gdy jesteś zalogowany, bez okna konsoli; wyjście w data\<komenda>.log.
# Uruchomienie przegapione przy wyłączonym komputerze startuje zaraz po jego włączeniu.

param([switch]$Remove)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Folder = "\3dk-przetargi\"

if ($Remove) {
    Get-ScheduledTask -TaskPath $Folder -ErrorAction SilentlyContinue | Unregister-ScheduledTask -Confirm:$false
    Write-Output "Usunięto zadania z $Folder"
    return
}

# prawdziwy interpreter (alias z WindowsApps nie nadaje się do Harmonogramu), wersja bez konsoli
$PythonExe = (& python -c "import sys; print(sys.executable)").Trim()
$Python = Join-Path (Split-Path $PythonExe) "pythonw.exe"
if (-not (Test-Path $Python)) { throw "Brak $Python" }
$Script = Join-Path $Root "scripts\scheduled.py"

function Add-Task([string]$Name, [string]$Arguments, $Triggers, [int]$Hours = 1) {
    $Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -ExecutionTimeLimit (New-TimeSpan -Hours $Hours) -MultipleInstances IgnoreNew
    $Action = New-ScheduledTaskAction -Execute $Python -Argument "`"$Script`" $Arguments" -WorkingDirectory $Root
    Register-ScheduledTask -TaskPath $Folder -TaskName $Name -Action $Action -Trigger $Triggers -Settings $Settings `
        -Description "3dk-przetargi: $Arguments" -Force | Out-Null
    Write-Output "  $Name -> $Arguments"
}

$Weekdays = @("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")

# platformazakupowa.pl: 15 min między zapytaniami (robots.txt), więc osobno i wcześnie rano
Add-Task "pz" "fetch --source pz" (New-ScheduledTaskTrigger -Weekly -DaysOfWeek $Weekdays -At "05:30") -Hours 2

# BIP, Baza Konkurencyjności, SARP, BZP + Jev + Telegram/WhatsApp: rano i po południu (BZP publikuje w ciągu dnia)
Add-Task "daily" "daily" -Hours 2 -Triggers @((New-ScheduledTaskTrigger -Weekly -DaysOfWeek $Weekdays -At "07:30"),
    (New-ScheduledTaskTrigger -Weekly -DaysOfWeek $Weekdays -At "15:30"))

Write-Output "Gotowe. Logi: $Root\data\<komenda>.log"
