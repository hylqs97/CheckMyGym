Param(
  [string]$PythonExe = "python",
  [string]$AppPath = "app.py",
  [string]$TaskName = "CheckMyGym",
  [int]$DelaySeconds = 10
)

$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Resolve-Path (Join-Path $Here "..")
$AppFullPath = Resolve-Path (Join-Path $Root $AppPath)

$Action = New-ScheduledTaskAction -Execute $PythonExe -Argument "`"$AppFullPath`"" -WorkingDirectory $Root
$Trigger = New-ScheduledTaskTrigger -AtLogOn
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

try {
  Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue | Out-Null
} catch {}

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings | Out-Null
Write-Output "Registered scheduled task '$TaskName' to run $PythonExe $AppFullPath at user logon."

